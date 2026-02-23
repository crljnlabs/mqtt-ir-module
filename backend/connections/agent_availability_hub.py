import logging
import threading
import time
from typing import Any

from jmqtt import MQTTMessage, QualityOfService as QoS

from agents.agent_registry import AgentRegistry
from .runtime_loader import RuntimeLoader


class AgentAvailabilityHub:
    STATUS_TOPIC_WILDCARD = "ir/agents/+/status"

    def __init__(self, runtime_loader: RuntimeLoader, agent_registry: AgentRegistry) -> None:
        self._runtime_loader = runtime_loader
        self._agent_registry = agent_registry
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
        try:
            connection.subscribe(self.STATUS_TOPIC_WILDCARD, self._on_status, qos=QoS.AtLeastOnce)
        except Exception as exc:
            self._logger.warning(f"Failed to subscribe availability topic {self.STATUS_TOPIC_WILDCARD}: {exc}")
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
            return
        if status == "offline":
            self._agent_registry.set_agent_offline(agent_id=agent_id, last_seen=seen_at)

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
