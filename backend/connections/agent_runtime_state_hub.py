import json
import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Set, Tuple

from jmqtt import MQTTMessage, QualityOfService as QoS

from database import Database
from .runtime_loader import RuntimeLoader

if TYPE_CHECKING:
    from .pairing_manager_hub import PairingManagerHub


class AgentRuntimeStateHub:
    # Wildcard covers all state subtopics: state/hub, state/version, state/agent,
    # state/runtime, state/diagnostics
    STATE_TOPIC_WILDCARD = "ir/agents/+/state/+"

    def __init__(
        self,
        runtime_loader: RuntimeLoader,
        database: Database,
        pairing_manager: "Optional[PairingManagerHub]" = None,
    ) -> None:
        self._runtime_loader = runtime_loader
        self._database = database
        self._pairing_manager = pairing_manager
        self._logger = logging.getLogger("agent_runtime_state_hub")
        self._lock = threading.Lock()
        self._running = False
        self._subscribed = False
        self._states: Dict[str, Dict[str, Any]] = {}
        self._reclaim_sent: Set[str] = set()

    def start(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        if connection is None:
            return
        with self._lock:
            if self._running and self._subscribed:
                return
        connection.add_on_connect(self._on_mqtt_connect)
        self._subscribe(connection)
        with self._lock:
            self._running = True
            self._subscribed = True

    def _on_mqtt_connect(self, connection: Any, _client: Any, _userdata: Any, _flags: Any) -> None:
        with self._lock:
            if not self._running:
                return
        self._subscribe(connection)

    def _subscribe(self, connection: Any) -> None:
        try:
            connection.subscribe(self.STATE_TOPIC_WILDCARD, self._on_state, qos=QoS.AtLeastOnce)
        except Exception as exc:
            self._logger.warning(f"Failed to subscribe runtime state topic {self.STATE_TOPIC_WILDCARD}: {exc}")

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
            self._reclaim_sent.discard(normalized_agent_id)

    def _on_state(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        del connection
        del client
        del userdata
        agent_id, subtopic = self._parse_agent_id_and_subtopic(message.topic)
        if not agent_id or not subtopic:
            return
        payload = self._parse_payload(message)
        if payload is None:
            return
        state = self._apply_subtopic(agent_id, subtopic, payload)
        if state is None:
            return
        self._sync_agent_capabilities(agent_id, state)
        self._maybe_reclaim_agent(agent_id, state)

    def _apply_subtopic(self, agent_id: str, subtopic: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            current = dict(self._states.get(agent_id, {}))

        if subtopic == "hub":
            current["pairing_hub_id"] = str(payload.get("id") or "").strip()
        elif subtopic == "version":
            current["sw_version"] = str(payload.get("sw_version") or "").strip()
            current["system_version"] = self._parse_int(payload.get("system")) or 0
            current["send_version"] = self._parse_int(payload.get("send")) or 0
            current["learn_version"] = self._parse_int(payload.get("learn")) or 0
        elif subtopic == "agent":
            current["agent_type"] = str(payload.get("agent_type") or "").strip().lower()
            current["can_send"] = self._parse_bool(payload.get("can_send"), default=True)
            current["can_learn"] = self._parse_bool(payload.get("can_learn"), default=False)
            current["ota_supported"] = self._parse_bool(payload.get("ota_supported"), default=False)
            if "can_learn_hold_batch" in payload:
                current["can_learn_hold_batch"] = self._parse_bool(payload.get("can_learn_hold_batch"), default=False)
        elif subtopic == "runtime":
            current["debug"] = self._parse_bool(payload.get("debug"), default=False)
            current["reboot_required"] = self._parse_bool(payload.get("reboot_required"), default=False)
            if "ir_rx_pin" in payload:
                current["ir_rx_pin"] = self._parse_int(payload.get("ir_rx_pin"))
            if "ir_tx_pin" in payload:
                current["ir_tx_pin"] = self._parse_int(payload.get("ir_tx_pin"))
        elif subtopic == "diagnostics":
            current["free_heap"] = self._parse_int(payload.get("free_heap"))
            current["last_reset_reason"] = str(payload.get("last_reset_reason") or "").strip().lower()
            current["last_reset_code"] = self._parse_int(payload.get("last_reset_code"))
            current["last_reset_crash"] = self._parse_bool(payload.get("last_reset_crash"), default=False)
        else:
            return None  # Unknown subtopic — ignore

        current["state_seen_at"] = time.time()
        with self._lock:
            self._states[agent_id] = current
        return current

    def _sync_agent_capabilities(self, agent_id: str, state: Dict[str, Any]) -> None:
        agent = self._database.agents.get(agent_id)
        if not agent:
            # Create a stub entry for agents recovered via reclaim after hub data loss.
            with self._lock:
                was_reclaimed = agent_id in self._reclaim_sent
            if not was_reclaimed:
                return
            try:
                agent = self._database.agents.upsert(
                    agent_id=agent_id,
                    name=agent_id,
                    icon=None,
                    transport="mqtt",
                    status="online",
                    can_send=self._parse_bool(state.get("can_send"), default=True),
                    can_learn=self._parse_bool(state.get("can_learn"), default=False),
                    sw_version=str(state.get("sw_version") or "") or None,
                    agent_topic=None,
                    last_seen=state.get("state_seen_at"),
                    pending=False,
                )
                self._logger.info(f"Created stub DB entry for reclaim-recovered agent {agent_id}")
            except Exception as exc:
                self._logger.warning(f"Failed to create recovered agent entry for {agent_id}: {exc}")
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

    def _maybe_reclaim_agent(self, agent_id: str, state: Dict[str, Any]) -> None:
        if self._pairing_manager is None:
            return
        pairing_hub_id = str(state.get("pairing_hub_id") or "").strip()
        if pairing_hub_id:
            # Agent is bound to this hub but not in DB → hub lost its data, reclaim to recover.
            if pairing_hub_id == self._hub_id():
                agent = self._database.agents.get(agent_id)
                if not agent:
                    with self._lock:
                        if agent_id in self._reclaim_sent:
                            return
                        self._reclaim_sent.add(agent_id)
                    try:
                        self._pairing_manager.reclaim_agent(agent_id)
                    except Exception as exc:
                        self._logger.warning(f"Failed to reclaim orphaned agent {agent_id}: {exc}")
                        with self._lock:
                            self._reclaim_sent.discard(agent_id)
                    return
            with self._lock:
                self._reclaim_sent.discard(agent_id)
            return
        # Agent lost its binding → reclaim if known in DB.
        with self._lock:
            if agent_id in self._reclaim_sent:
                return
        agent = self._database.agents.get(agent_id)
        if not agent or bool(agent.get("pending")):
            return
        with self._lock:
            self._reclaim_sent.add(agent_id)
        try:
            self._pairing_manager.reclaim_agent(agent_id)
        except Exception as exc:
            self._logger.warning(f"Failed to reclaim agent {agent_id}: {exc}")
            with self._lock:
                self._reclaim_sent.discard(agent_id)

    def _hub_id(self) -> str:
        mqtt_status = self._runtime_loader.status()
        return str(mqtt_status.get("node_id") or "").strip() or str(self._runtime_loader.technical_name or "").strip()

    def _parse_agent_id_and_subtopic(self, topic: str) -> Tuple[str, str]:
        # Topic pattern: ir/agents/{id}/state/{subtopic}
        parts = str(topic or "").split("/")
        if len(parts) != 5:
            return "", ""
        if parts[0] != "ir" or parts[1] != "agents" or parts[3] != "state":
            return "", ""
        return parts[2].strip(), parts[4].strip()

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
