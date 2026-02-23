import json
import logging
import threading
import time
from typing import Any, Dict, Optional

from jmqtt import MQTTMessage, QualityOfService as QoS

from database import Database
from .runtime_loader import RuntimeLoader


class AgentRuntimeStateHub:
    STATE_TOPIC_WILDCARD = "ir/agents/+/state"

    def __init__(self, runtime_loader: RuntimeLoader, database: Database) -> None:
        self._runtime_loader = runtime_loader
        self._database = database
        self._logger = logging.getLogger("agent_runtime_state_hub")
        self._lock = threading.Lock()
        self._running = False
        self._subscribed = False
        self._states: Dict[str, Dict[str, Any]] = {}

    def start(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        if connection is None:
            return
        with self._lock:
            if self._running and self._subscribed:
                return
        try:
            connection.subscribe(self.STATE_TOPIC_WILDCARD, self._on_state, qos=QoS.AtLeastOnce)
        except Exception as exc:
            self._logger.warning(f"Failed to subscribe runtime state topic {self.STATE_TOPIC_WILDCARD}: {exc}")
            return
        with self._lock:
            self._running = True
            self._subscribed = True

    def stop(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        with self._lock:
            subscribed = self._subscribed
            self._running = False
            self._subscribed = False
        if connection is None or not subscribed:
            return
        try:
            connection.unsubscribe(self.STATE_TOPIC_WILDCARD)
        except Exception as exc:
            self._logger.warning(f"Failed to unsubscribe runtime state topic {self.STATE_TOPIC_WILDCARD}: {exc}")

    def get_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return None
        with self._lock:
            state = self._states.get(normalized_agent_id)
        if not state:
            return None
        return dict(state)

    def clear_state(self, agent_id: str) -> None:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return
        with self._lock:
            self._states.pop(normalized_agent_id, None)

    def _on_state(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        del connection
        del client
        del userdata
        agent_id = self._parse_agent_id(message.topic)
        if not agent_id:
            return
        payload = self._parse_payload(message)
        if payload is None:
            return
        normalized = self._normalize_state(payload)
        if not normalized:
            return
        with self._lock:
            self._states[agent_id] = normalized
        self._sync_agent_capabilities(agent_id, normalized)

    def _sync_agent_capabilities(self, agent_id: str, state: Dict[str, Any]) -> None:
        agent = self._database.agents.get(agent_id)
        if not agent:
            return
        can_send = self._parse_bool(state.get("can_send"), default=bool(agent.get("can_send")))
        can_learn = self._parse_bool(state.get("can_learn"), default=bool(agent.get("can_learn")))
        sw_version = str(state.get("sw_version") or "").strip() or str(agent.get("sw_version") or "")
        try:
            self._database.agents.upsert(
                agent_id=agent_id,
                name=agent.get("name"),
                icon=agent.get("icon"),
                transport=str(agent.get("transport") or "mqtt"),
                status=str(agent.get("status") or "online"),
                can_send=can_send,
                can_learn=can_learn,
                sw_version=sw_version or None,
                agent_topic=agent.get("agent_topic"),
                configuration_url=agent.get("configuration_url"),
                pending=bool(agent.get("pending")),
                pairing_session_id=agent.get("pairing_session_id"),
                last_seen=agent.get("last_seen"),
            )
        except Exception as exc:
            self._logger.warning(f"Failed to sync runtime state into agent cache for {agent_id}: {exc}")

    def _parse_agent_id(self, topic: str) -> str:
        parts = str(topic or "").split("/")
        if len(parts) != 4:
            return ""
        if parts[0] != "ir" or parts[1] != "agents" or parts[3] != "state":
            return ""
        return parts[2].strip()

    def _parse_payload(self, message: MQTTMessage) -> Optional[Dict[str, Any]]:
        value = message.json_value
        if isinstance(value, dict):
            return value
        if not message.text:
            return None
        try:
            parsed = json.loads(message.text)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    def _normalize_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}

        normalized["pairing_hub_id"] = str(payload.get("pairing_hub_id") or "").strip()
        normalized["debug"] = self._parse_bool(payload.get("debug"), default=False)
        normalized["agent_type"] = str(payload.get("agent_type") or "").strip().lower()
        normalized["protocol_version"] = str(payload.get("protocol_version") or "").strip()
        normalized["sw_version"] = str(payload.get("sw_version") or "").strip()
        normalized["can_send"] = self._parse_bool(payload.get("can_send"), default=True)
        normalized["can_learn"] = self._parse_bool(payload.get("can_learn"), default=False)
        normalized["ota_supported"] = self._parse_bool(payload.get("ota_supported"), default=False)
        normalized["reboot_required"] = self._parse_bool(payload.get("reboot_required"), default=False)
        normalized["power_mode"] = str(payload.get("power_mode") or "").strip().lower()
        normalized["ir_rx_pin"] = self._parse_int(payload.get("ir_rx_pin"))
        normalized["ir_tx_pin"] = self._parse_int(payload.get("ir_tx_pin"))
        normalized["updated_at"] = self._parse_float(payload.get("updated_at"), default=time.time())
        normalized["state_seen_at"] = time.time()

        commands = payload.get("runtime_commands")
        if isinstance(commands, list):
            normalized["runtime_commands"] = [
                str(item).strip() for item in commands if str(item or "").strip()
            ]
        else:
            normalized["runtime_commands"] = []
        return normalized

    def _parse_bool(self, value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value or "").strip().lower()
        if text in ("1", "true", "yes", "y", "on"):
            return True
        if text in ("0", "false", "no", "n", "off"):
            return False
        return default

    def _parse_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    def _parse_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)
