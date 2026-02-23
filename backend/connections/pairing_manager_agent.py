import json
import logging
import threading
import time
from typing import Any, Dict, Optional

from jmqtt import MQTTMessage, QualityOfService as QoS

from .agent_runtime_state_store import AgentRuntimeStateStore
from .agent_log_reporter import AgentLogReporter
from .runtime_loader import RuntimeLoader


class PairingManagerAgent:
    PAIRING_OPEN_TOPIC = "ir/pairing/open"
    PAIRING_OFFER_TOPIC_PREFIX = "ir/pairing/offer"
    PAIRING_ACCEPT_TOPIC_PREFIX = "ir/pairing/accept"
    PAIRING_UNPAIR_TOPIC_PREFIX = "ir/pairing/unpair"
    PAIRING_UNPAIR_ACK_TOPIC_PREFIX = "ir/pairing/unpair_ack"

    def __init__(
        self,
        runtime_loader: RuntimeLoader,
        binding_store: AgentRuntimeStateStore,
        readable_name: str,
        sw_version: str,
        can_send: bool,
        can_learn: bool,
        agent_type: str = "",
        protocol_version: str = "",
        ota_supported: bool = False,
        reset_binding: bool = False,
        log_reporter: Optional[AgentLogReporter] = None,
    ) -> None:
        self._runtime_loader = runtime_loader
        self._binding_store = binding_store
        self._readable_name = str(readable_name or "").strip()
        self._sw_version = str(sw_version or "").strip()
        self._can_send = bool(can_send)
        self._can_learn = bool(can_learn)
        self._agent_type = str(agent_type or "").strip().lower()
        self._protocol_version = str(protocol_version or "").strip()
        self._ota_supported = bool(ota_supported)
        self._reset_binding = bool(reset_binding)

        self._logger = logging.getLogger("pairing_manager_agent")
        self._log_reporter = log_reporter or AgentLogReporter(
            agent_id_resolver=self._agent_uid,
            logger_name="pairing_manager_agent_events",
            dispatch=None,
            min_dispatch_level="info",
        )
        self._lock = threading.Lock()
        self._running = False
        self._subscribed_open = False
        self._subscribed_accept = False
        self._subscribed_unpair = False
        self._active_session_id = ""
        self._active_nonce = ""
        self._active_expires_at = 0.0

    def start(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        if connection is None:
            self._log_reporter.warn(
                category="pairing",
                message="Pairing manager start skipped because MQTT is not connected",
                error_code="mqtt_not_connected",
            )
            return

        if self._reset_binding:
            self._clear_binding()

        with self._lock:
            if self._running:
                return
            self._running = True

        connection.subscribe(self._unpair_topic_wildcard(), self._on_unpair_command, qos=QoS.AtLeastOnce)
        with self._lock:
            self._subscribed_unpair = True

        if self._is_bound():
            self._log_reporter.info(category="pairing", message="Agent is already paired; pairing listeners are paused")
            return

        self._start_pairing_listeners(connection)
        self._log_reporter.info(category="pairing", message="Pairing listeners started")

    def stop(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        with self._lock:
            self._running = False
            subscribed_open = self._subscribed_open
            subscribed_accept = self._subscribed_accept
            subscribed_unpair = self._subscribed_unpair
            self._subscribed_open = False
            self._subscribed_accept = False
            self._subscribed_unpair = False
            self._clear_open_context_locked()

        if connection is None:
            return

        try:
            if subscribed_open:
                connection.unsubscribe(self.PAIRING_OPEN_TOPIC)
            if subscribed_accept:
                connection.unsubscribe(self._accept_topic_wildcard())
            if subscribed_unpair:
                connection.unsubscribe(self._unpair_topic_wildcard())
            self._log_reporter.info(category="pairing", message="Pairing manager stopped")
        except Exception as exc:
            self._log_reporter.warn(
                category="pairing",
                message=f"Failed to unsubscribe pairing topics: {exc}",
                error_code="unsubscribe_failed",
            )
            self._logger.warning(f"Failed to unsubscribe agent pairing topics: {exc}")

    def status(self) -> Dict[str, Any]:
        binding = self._binding_data()
        with self._lock:
            running = self._running
            listening = self._subscribed_open or self._subscribed_accept

        return {
            "running": running,
            "paired": bool(binding.get("pairing_hub_id")),
            "listening": listening,
            **binding,
        }

    def _on_pairing_open(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        if self._is_bound():
            return

        payload = self._parse_payload(message)
        if payload is None:
            return

        session_id = str(payload.get("session_id") or "").strip()
        nonce = str(payload.get("nonce") or "").strip()
        if not session_id or not nonce:
            return
        self._log_reporter.debug(
            category="pairing",
            message="Pairing window received",
            meta={"session_id": session_id},
        )

        expires_at = float(payload.get("expires_at") or 0.0)
        if expires_at <= 0 or time.time() >= expires_at:
            return

        hub_sw_version = str(payload.get("sw_version") or "").strip()
        if not self._is_compatible(hub_sw_version):
            return

        agent_uid = self._agent_uid()
        if not agent_uid:
            return

        with self._lock:
            self._active_session_id = session_id
            self._active_nonce = nonce
            self._active_expires_at = expires_at

        runtime_status = self._runtime_loader.status()
        offer_payload = {
            "session_id": session_id,
            "nonce": nonce,
            "agent_uid": agent_uid,
            "readable_name": self._agent_name(agent_uid),
            "base_topic": runtime_status.get("base_topic"),
            "sw_version": self._sw_version,
            "can_send": self._can_send,
            "can_learn": self._can_learn,
            "offered_at": time.time(),
        }
        if self._agent_type:
            offer_payload["agent_type"] = self._agent_type
        if self._protocol_version:
            offer_payload["protocol_version"] = self._protocol_version
        offer_payload["ota_supported"] = self._ota_supported
        offer_topic = f"{self.PAIRING_OFFER_TOPIC_PREFIX}/{session_id}/{agent_uid}"
        connection.publish(
            offer_topic,
            json.dumps(offer_payload, separators=(",", ":")),
            qos=QoS.AtLeastOnce,
            retain=False,
        )
        self._log_reporter.info(
            category="pairing",
            message="Pairing offer published",
            meta={"session_id": session_id},
        )

    def _on_pairing_accept(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        if self._is_bound():
            return

        expected_agent_uid = self._agent_uid()
        session_id_from_topic, agent_uid_from_topic = self._parse_accept_topic(message.topic)
        if not session_id_from_topic or not expected_agent_uid or agent_uid_from_topic != expected_agent_uid:
            return

        payload = self._parse_payload(message)
        if payload is None:
            return

        payload_session = str(payload.get("session_id") or "").strip()
        payload_nonce = str(payload.get("nonce") or "").strip()
        if payload_session and payload_session != session_id_from_topic:
            return
        if not payload_nonce:
            return

        with self._lock:
            active_session_id = self._active_session_id
            active_nonce = self._active_nonce
            active_expires_at = self._active_expires_at

        if not active_session_id or active_session_id != session_id_from_topic:
            return
        if not active_nonce or payload_nonce != active_nonce:
            return
        if active_expires_at > 0 and time.time() >= active_expires_at:
            return

        self._binding_store.set_binding(
            hub_id=str(payload.get("hub_id") or ""),
            hub_topic=str(payload.get("hub_topic") or ""),
            hub_name=str(payload.get("hub_name") or ""),
            session_id=session_id_from_topic,
            nonce=payload_nonce,
            accepted_at=payload.get("accepted_at"),
        )
        self._log_reporter.info(
            category="pairing",
            message="Pairing accepted",
            meta={"session_id": session_id_from_topic},
        )

        self._stop_pairing_listeners(connection)

    def _on_unpair_command(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        expected_agent_uid = self._agent_uid()
        agent_uid_from_topic = self._parse_unpair_topic(message.topic)
        if not expected_agent_uid or not agent_uid_from_topic or agent_uid_from_topic != expected_agent_uid:
            return

        payload = self._parse_payload(message)
        if payload is None:
            return
        command_id = str(payload.get("command_id") or "").strip()
        if not command_id:
            return
        self._log_reporter.warn(
            category="pairing",
            message="Unpair command received",
            error_code="unpair_requested",
            meta={"command_id": command_id},
        )

        self._clear_binding()
        with self._lock:
            self._clear_open_context_locked()
            running = self._running

        if running:
            self._start_pairing_listeners(connection)

        ack_payload = {
            "agent_uid": expected_agent_uid,
            "command_id": command_id,
            "acked_at": time.time(),
        }
        ack_topic = f"{self.PAIRING_UNPAIR_ACK_TOPIC_PREFIX}/{expected_agent_uid}"
        command_topic = f"{self.PAIRING_UNPAIR_TOPIC_PREFIX}/{expected_agent_uid}"

        try:
            connection.publish(
                ack_topic,
                json.dumps(ack_payload, separators=(",", ":")),
                qos=QoS.AtLeastOnce,
                retain=False,
            )
            # Clear retained unpair command after ack to avoid stale replay.
            connection.publish(command_topic, "", qos=QoS.AtLeastOnce, retain=True)
            self._log_reporter.info(
                category="pairing",
                message="Unpair acknowledged",
                meta={"command_id": command_id},
            )
        except Exception as exc:
            self._log_reporter.error(
                category="pairing",
                message=f"Failed to acknowledge unpair command: {exc}",
                error_code="unpair_ack_failed",
                meta={"command_id": command_id},
            )
            self._logger.warning(f"Failed to acknowledge unpair command: {exc}")

    def _start_pairing_listeners(self, connection: Any) -> None:
        with self._lock:
            if self._subscribed_open and self._subscribed_accept:
                return
            subscribed_open = self._subscribed_open
            subscribed_accept = self._subscribed_accept

        try:
            if not subscribed_open:
                connection.subscribe(self.PAIRING_OPEN_TOPIC, self._on_pairing_open, qos=QoS.AtLeastOnce)
            if not subscribed_accept:
                connection.subscribe(self._accept_topic_wildcard(), self._on_pairing_accept, qos=QoS.AtLeastOnce)
            with self._lock:
                self._subscribed_open = True
                self._subscribed_accept = True
        except Exception as exc:
            self._log_reporter.warn(
                category="pairing",
                message=f"Failed to subscribe pairing listeners: {exc}",
                error_code="subscribe_failed",
            )
            self._logger.warning(f"Failed to subscribe to pairing listeners: {exc}")

    def _stop_pairing_listeners(self, connection: Any) -> None:
        with self._lock:
            subscribed_open = self._subscribed_open
            subscribed_accept = self._subscribed_accept
            self._subscribed_open = False
            self._subscribed_accept = False
            self._clear_open_context_locked()

        try:
            if subscribed_open:
                connection.unsubscribe(self.PAIRING_OPEN_TOPIC)
            if subscribed_accept:
                connection.unsubscribe(self._accept_topic_wildcard())
        except Exception as exc:
            self._logger.warning(f"Failed to stop pairing listeners: {exc}")

    def _accept_topic_wildcard(self) -> str:
        agent_uid = self._agent_uid()
        if not agent_uid:
            return f"{self.PAIRING_ACCEPT_TOPIC_PREFIX}/+/unknown"
        return f"{self.PAIRING_ACCEPT_TOPIC_PREFIX}/+/{agent_uid}"

    def _unpair_topic_wildcard(self) -> str:
        return f"{self.PAIRING_UNPAIR_TOPIC_PREFIX}/+"

    def _parse_accept_topic(self, topic: str) -> tuple[str, str]:
        parts = str(topic or "").split("/")
        if len(parts) != 5:
            return "", ""
        if parts[0] != "ir" or parts[1] != "pairing" or parts[2] != "accept":
            return "", ""
        return parts[3].strip(), parts[4].strip()

    def _parse_unpair_topic(self, topic: str) -> str:
        parts = str(topic or "").split("/")
        if len(parts) != 4:
            return ""
        if parts[0] != "ir" or parts[1] != "pairing" or parts[2] != "unpair":
            return ""
        return parts[3].strip()

    def _is_bound(self) -> bool:
        return self._binding_store.is_bound()

    def _clear_binding(self) -> None:
        self._binding_store.clear_binding()

    def _clear_open_context_locked(self) -> None:
        self._active_session_id = ""
        self._active_nonce = ""
        self._active_expires_at = 0.0

    def _binding_data(self) -> Dict[str, Any]:
        return self._binding_store.binding_data()

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

    def _is_compatible(self, hub_sw_version: str) -> bool:
        hub_major = self._major_version(hub_sw_version)
        agent_major = self._major_version(self._sw_version)
        if not hub_major or not agent_major:
            return True
        return hub_major == agent_major

    def _major_version(self, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            return ""
        return normalized.split(".", maxsplit=1)[0]

    def _agent_uid(self) -> str:
        client_id = str(self._runtime_loader.mqtt_client_id() or "").strip()
        if client_id:
            return client_id
        runtime_status = self._runtime_loader.status()
        fallback = str(runtime_status.get("client_id") or runtime_status.get("node_id") or "").strip()
        return fallback

    def _agent_name(self, agent_uid: str) -> str:
        readable = str(self._readable_name or "").strip()
        if readable:
            return readable
        return agent_uid
