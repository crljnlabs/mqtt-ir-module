import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from jmqtt import MQTTMessage, QualityOfService as QoS

from .runtime_loader import RuntimeLoader


DebugChangeHandler = Callable[[bool], None]


class AgentRuntimeStateStore:
    STATE_TOPIC_PREFIX = "ir/agents"

    # Fields routed to state/version (stored in _extra_state with these keys)
    VERSION_FIELDS = {"sw_version", "system_version", "send_version", "learn_version"}
    # Fields routed to state/agent
    AGENT_FIELDS = {"agent_type", "can_send", "can_learn", "can_learn_hold_batch", "ota_supported"}
    # Fields routed to state/runtime (debug is handled separately)
    RUNTIME_EXTRA_FIELDS = {"reboot_required", "ir_rx_pin", "ir_tx_pin"}
    # Fields routed to state/diagnostics (not retained)
    DIAGNOSTICS_FIELDS = {"free_heap", "last_reset_reason", "last_reset_code", "last_reset_crash"}

    # Reserved keys never stored in _extra_state
    RESERVED_KEYS = {"pairing_hub_id", "debug", "updated_at"}

    def __init__(
        self,
        runtime_loader: RuntimeLoader,
        agent_id_resolver: Callable[[], str],
        static_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._runtime_loader = runtime_loader
        self._agent_id_resolver = agent_id_resolver
        self._logger = logging.getLogger("agent_runtime_state_store")
        self._lock = threading.Lock()
        self._running = False
        self._subscribed_hub_topic = ""
        self._subscribed_runtime_topic = ""
        self._pairing_hub_id = ""
        self._debug = False
        self._extra_state: Dict[str, Any] = {}
        self._state_loaded_event: Optional[threading.Event] = None
        self._debug_change_handler: Optional[DebugChangeHandler] = None
        self._extra_state = self._normalize_extra_state(static_state or {})

    def set_debug_change_handler(self, handler: Optional[DebugChangeHandler]) -> None:
        with self._lock:
            self._debug_change_handler = handler

    def start(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        if connection is None:
            return

        agent_id = self._agent_id()
        if not agent_id:
            return

        prefix = f"{self.STATE_TOPIC_PREFIX}/{agent_id}/state"
        hub_topic = f"{prefix}/hub"
        runtime_topic = f"{prefix}/runtime"
        state_loaded = threading.Event()

        for topic, handler in [
            (hub_topic, self._on_hub_state),
            (runtime_topic, self._on_runtime_state),
        ]:
            try:
                connection.subscribe(topic, handler, qos=QoS.AtLeastOnce)
            except Exception as exc:
                self._logger.warning(f"Failed to subscribe state topic {topic}: {exc}")
                return

        with self._lock:
            self._running = True
            self._subscribed_hub_topic = hub_topic
            self._subscribed_runtime_topic = runtime_topic
            self._state_loaded_event = state_loaded

        # Allow broker to deliver retained state before publishing fresh state.
        state_loaded.wait(1.0)
        self._publish_state()
        # Publish availability after state so hub sees a fully populated agent.
        self._publish_availability("online")

    def stop(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        with self._lock:
            hub_topic = self._subscribed_hub_topic
            runtime_topic = self._subscribed_runtime_topic
            self._subscribed_hub_topic = ""
            self._subscribed_runtime_topic = ""
            self._running = False
            self._state_loaded_event = None
        self._publish_availability("offline")
        if connection is None:
            return
        for topic in [hub_topic, runtime_topic]:
            if not topic:
                continue
            try:
                connection.unsubscribe(topic)
            except Exception as exc:
                self._logger.warning(f"Failed to unsubscribe state topic {topic}: {exc}")

    def is_bound(self) -> bool:
        return bool(self.hub_id())

    def hub_id(self) -> str:
        with self._lock:
            return self._pairing_hub_id

    def hub_topic(self) -> str:
        return ""

    def clear_binding(self) -> None:
        self._apply_state({"pairing_hub_id": ""}, publish=True)

    def set_binding(
        self,
        hub_id: str,
        hub_topic: str,
        hub_name: str,
        session_id: str,
        nonce: str,
        accepted_at: Any,
    ) -> None:
        del hub_topic
        del hub_name
        del session_id
        del nonce
        del accepted_at
        self._apply_state({"pairing_hub_id": str(hub_id or "").strip()}, publish=True)

    def binding_data(self) -> Dict[str, Any]:
        with self._lock:
            pairing_hub_id = self._pairing_hub_id
            debug = self._debug
        return {
            "pairing_hub_id": pairing_hub_id,
            "debug": debug,
        }

    def runtime_state(self) -> Dict[str, Any]:
        with self._lock:
            payload = {
                "pairing_hub_id": self._pairing_hub_id,
                "debug": self._debug,
                **self._extra_state,
            }
        return payload

    def update_runtime_state(self, changes: Dict[str, Any], publish: bool = True) -> Dict[str, Any]:
        if not isinstance(changes, dict):
            return self.runtime_state()
        self._apply_state(changes, publish=publish)
        return self.runtime_state()

    def debug_enabled(self) -> bool:
        with self._lock:
            return self._debug

    def set_debug(self, enabled: bool) -> bool:
        self._apply_state({"debug": bool(enabled)}, publish=True)
        return self.debug_enabled()

    def _on_hub_state(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        del connection, client, userdata
        payload = self._parse_payload(message)
        if payload is None:
            return
        hub_id = str(payload.get("id") or "").strip()
        with self._lock:
            self._pairing_hub_id = hub_id
            event = self._state_loaded_event
        if isinstance(event, threading.Event):
            event.set()

    def _on_runtime_state(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        del connection, client, userdata
        payload = self._parse_payload(message)
        if payload is None:
            return
        # Only restore the fields that belong to runtime state on reconnect.
        filtered = {
            k: v for k, v in payload.items()
            if k in self.RUNTIME_EXTRA_FIELDS or k == "debug"
        }
        self._apply_state(filtered, publish=False)
        with self._lock:
            event = self._state_loaded_event
        if isinstance(event, threading.Event):
            event.set()

    def _apply_state(self, payload: Dict[str, Any], publish: bool) -> None:
        debug_handler: Optional[DebugChangeHandler] = None
        debug_changed = False

        with self._lock:
            previous_debug = self._debug
            if "pairing_hub_id" in payload:
                self._pairing_hub_id = str(payload.get("pairing_hub_id") or "").strip()
            if "debug" in payload:
                self._debug = self._parse_bool(payload.get("debug"), default=self._debug)
            for key, value in payload.items():
                if key in self.RESERVED_KEYS:
                    continue
                normalized_key = str(key or "").strip()
                if not normalized_key:
                    continue
                normalized_value = self._sanitize_runtime_value(value)
                if normalized_value is None:
                    self._extra_state.pop(normalized_key, None)
                else:
                    self._extra_state[normalized_key] = normalized_value
            debug_changed = previous_debug != self._debug
            debug_handler = self._debug_change_handler

        if publish:
            self._publish_state()
        if debug_changed and debug_handler:
            try:
                debug_handler(self.debug_enabled())
            except Exception as exc:
                self._logger.warning(f"Failed to run debug change handler: {exc}")

    def _publish_state(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        prefix = self._state_prefix()
        if connection is None or not prefix:
            return

        with self._lock:
            pairing_hub_id = self._pairing_hub_id
            debug = self._debug
            extra = dict(self._extra_state)

        # state/hub — binding state (retained)
        self._publish_subtopic(
            connection,
            f"{prefix}/hub",
            {"id": pairing_hub_id},
            retain=True,
        )

        # state/version — all version integers + sw_version (retained)
        self._publish_subtopic(
            connection,
            f"{prefix}/version",
            {
                "sw_version": str(extra.get("sw_version") or ""),
                "system": int(extra.get("system_version") or 0),
                "send": int(extra.get("send_version") or 0),
                "learn": int(extra.get("learn_version") or 0),
            },
            retain=True,
        )

        # state/agent — static capabilities (retained)
        agent_payload = {k: v for k, v in extra.items() if k in self.AGENT_FIELDS}
        if agent_payload:
            self._publish_subtopic(connection, f"{prefix}/agent", agent_payload, retain=True)

        # state/runtime — mutable operational state (retained)
        runtime_payload: Dict[str, Any] = {"debug": debug}
        runtime_payload.update({k: v for k, v in extra.items() if k in self.RUNTIME_EXTRA_FIELDS})
        self._publish_subtopic(connection, f"{prefix}/runtime", runtime_payload, retain=True)

        # state/diagnostics — point-in-time data, not retained
        diag_payload = {k: v for k, v in extra.items() if k in self.DIAGNOSTICS_FIELDS}
        if diag_payload:
            self._publish_subtopic(connection, f"{prefix}/diagnostics", diag_payload, retain=False)

    def _publish_availability(self, status: str) -> None:
        connection = self._runtime_loader.mqtt_connection()
        prefix = self._state_prefix()
        if connection is None or not prefix:
            return
        try:
            connection.publish(
                f"{prefix}/availability",
                status,
                qos=QoS.AtLeastOnce,
                retain=True,
            )
        except Exception as exc:
            self._logger.warning(f"Failed to publish availability to {prefix}/availability: {exc}")

    def _publish_subtopic(self, connection: Any, topic: str, payload: Dict[str, Any], retain: bool) -> None:
        try:
            connection.publish(
                topic,
                json.dumps(payload, separators=(",", ":")),
                qos=QoS.AtLeastOnce,
                retain=retain,
            )
        except Exception as exc:
            self._logger.warning(f"Failed to publish state subtopic {topic}: {exc}")

    def _state_prefix(self) -> str:
        with self._lock:
            if self._subscribed_hub_topic:
                # Derive prefix from subscribed hub topic: ".../state/hub" → ".../state"
                return "/".join(self._subscribed_hub_topic.split("/")[:-1])
        agent_id = self._agent_id()
        if not agent_id:
            return ""
        return f"{self.STATE_TOPIC_PREFIX}/{agent_id}/state"

    def _agent_id(self) -> str:
        return str(self._agent_id_resolver() or "").strip()

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

    def _normalize_extra_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in payload.items():
            normalized_key = str(key or "").strip()
            if not normalized_key or normalized_key in self.RESERVED_KEYS:
                continue
            normalized_value = self._sanitize_runtime_value(value)
            if normalized_value is None:
                continue
            normalized[normalized_key] = normalized_value
        return normalized

    def _sanitize_runtime_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return str(value)
        if isinstance(value, dict):
            result: Dict[str, Any] = {}
            for key, item in value.items():
                normalized_key = str(key or "").strip()
                if not normalized_key:
                    continue
                normalized_item = self._sanitize_runtime_value(item)
                if normalized_item is None:
                    continue
                result[normalized_key] = normalized_item
            return result
        if isinstance(value, (list, tuple)):
            result_list: List[Any] = []
            for item in value:
                normalized_item = self._sanitize_runtime_value(item)
                if normalized_item is None:
                    continue
                result_list.append(normalized_item)
            return result_list
        return str(value)
