import logging
import threading
import time
from typing import Any, Optional

from jmqtt import MQTTMessage, QualityOfService as QoS

from agents.agent_registry import AgentRegistry
from .agent_log_hub import AgentLogHub
from .runtime_loader import RuntimeLoader


class AgentAvailabilityHub:
    STATUS_TOPIC_WILDCARD = "ir/agents/+/status"

    def __init__(
        self,
        runtime_loader: RuntimeLoader,
        agent_registry: AgentRegistry,
        agent_log_hub: Optional[AgentLogHub] = None,
    ) -> None:
        self._runtime_loader = runtime_loader
        self._agent_registry = agent_registry
        self._agent_log_hub = agent_log_hub
        self._logger = logging.getLogger("agent_availability_hub")
        self._lock = threading.Lock()
        self._running = False
        self._subscribed = False

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
            connection.subscribe(self.STATUS_TOPIC_WILDCARD, self._on_status, qos=QoS.AtLeastOnce)
        except Exception as exc:
            self._logger.warning(f"Failed to subscribe availability topic {self.STATUS_TOPIC_WILDCARD}: {exc}")

    def stop(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        with self._lock:
            subscribed = self._subscribed
            self._running = False
            self._subscribed = False
        if connection is None or not subscribed:
            return
        try:
            connection.unsubscribe(self.STATUS_TOPIC_WILDCARD)
        except Exception as exc:
            self._logger.warning(f"Failed to unsubscribe availability topic {self.STATUS_TOPIC_WILDCARD}: {exc}")

    def _on_status(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        del connection
        del client
        del userdata
        agent_id = self._parse_agent_id(message.topic)
        if not agent_id:
            return
        status = self._parse_status(message)
        if not status:
            return

        seen_at = time.time()
        if status == "online":
            self._agent_registry.set_agent_online(agent_id=agent_id, last_seen=seen_at)
            self._record_transition_log(
                agent_id=agent_id,
                seen_at=seen_at,
                status=status,
                level="info",
                message="MQTT availability online",
            )
            return
        if status == "offline":
            self._agent_registry.set_agent_offline(agent_id=agent_id, last_seen=seen_at)
            self._record_transition_log(
                agent_id=agent_id,
                seen_at=seen_at,
                status=status,
                level="warn",
                message="MQTT availability offline (LWT)",
                error_code="agent_offline_lwt",
            )

    def _parse_agent_id(self, topic: str) -> str:
        parts = str(topic or "").split("/")
        if len(parts) != 4:
            return ""
        if parts[0] != "ir" or parts[1] != "agents" or parts[3] != "status":
            return ""
        return parts[2].strip()

    def _parse_status(self, message: MQTTMessage) -> str:
        text = str(message.text or "").strip().lower()
        if text in ("online", "offline"):
            return text
        return ""

    def _record_transition_log(
        self,
        agent_id: str,
        seen_at: float,
        status: str,
        level: str,
        message: str,
        error_code: str = "",
    ) -> None:
        if self._agent_log_hub is None:
            return
        payload = {
            "ts": float(seen_at),
            "level": level,
            "category": "transport",
            "message": message,
            "meta": {
                "status": status,
                "source": "mqtt_availability",
            },
        }
        if error_code:
            payload["error_code"] = error_code
        self._agent_log_hub.record_system(agent_id=agent_id, event=payload)
