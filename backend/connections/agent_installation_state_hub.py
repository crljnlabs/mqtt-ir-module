import json
import logging
import threading
import time
from typing import Any, Dict, Optional

from jmqtt import MQTTMessage, QualityOfService as QoS

from .runtime_loader import RuntimeLoader


class AgentInstallationStateHub:
    STATE_TOPIC_WILDCARD = "ir/agents/+/installation/state"
    IN_PROGRESS_STATUSES = {"started", "downloading", "installing"}
    FINISH_CLEAR_DELAY_SECONDS = 20.0

    def __init__(self, runtime_loader: RuntimeLoader) -> None:
        self._runtime_loader = runtime_loader
        self._logger = logging.getLogger("agent_installation_state_hub")
        self._lock = threading.Lock()
        self._running = False
        self._subscribed = False
        self._states: Dict[str, Dict[str, Any]] = {}
        self._clear_timers: Dict[str, threading.Timer] = {}

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
            self._logger.warning(f"Failed to subscribe installation state topic {self.STATE_TOPIC_WILDCARD}: {exc}")
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
            self._states.clear()
            timers = list(self._clear_timers.values())
            self._clear_timers.clear()
        for timer in timers:
            try:
                timer.cancel()
            except Exception:
                pass
        if connection is None or not subscribed:
            return
        try:
            connection.unsubscribe(self.STATE_TOPIC_WILDCARD)
        except Exception as exc:
            self._logger.warning(f"Failed to unsubscribe installation state topic {self.STATE_TOPIC_WILDCARD}: {exc}")

    def get_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return None
        with self._lock:
            state = self._states.get(normalized_agent_id)
        if not state:
            return None
        payload = {k: v for k, v in state.items() if not str(k).startswith("_")}
        return payload

    def is_in_progress(self, agent_id: str) -> bool:
        state = self.get_state(agent_id)
        return bool(state and state.get("in_progress"))

    def clear_state(self, agent_id: str) -> None:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return
        self._cancel_clear_timer(normalized_agent_id)
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
            # Empty retained payload clears broker-side retained status.
            self.clear_state(agent_id)
            return

        normalized = self._normalize_state(payload)
        if not normalized:
            return

        with self._lock:
            self._states[agent_id] = normalized
        if str(normalized.get("status") or "") == "finished":
            self._schedule_finished_clear(agent_id)
        else:
            self._cancel_clear_timer(agent_id)

    def _schedule_finished_clear(self, agent_id: str) -> None:
        self._cancel_clear_timer(agent_id)
        timer = threading.Timer(self.FINISH_CLEAR_DELAY_SECONDS, self._on_clear_timer, args=(agent_id,))
        timer.daemon = True
        with self._lock:
            self._clear_timers[agent_id] = timer
        timer.start()

    def _cancel_clear_timer(self, agent_id: str) -> None:
        with self._lock:
            timer = self._clear_timers.pop(agent_id, None)
        if timer is None:
            return
        try:
            timer.cancel()
        except Exception:
            pass

    def _on_clear_timer(self, agent_id: str) -> None:
        should_clear = False
        with self._lock:
            self._clear_timers.pop(agent_id, None)
            state = self._states.get(agent_id)
            if isinstance(state, dict) and str(state.get("status") or "") == "finished":
                self._states.pop(agent_id, None)
                should_clear = True
        if should_clear:
            self._clear_retained(agent_id)

    def _clear_retained(self, agent_id: str) -> None:
        connection = self._runtime_loader.mqtt_connection()
        if connection is None:
            return
        topic = f"ir/agents/{agent_id}/installation/state"
        try:
            connection.publish(topic, "", qos=QoS.AtLeastOnce, retain=True)
        except Exception as exc:
            self._logger.warning(f"Failed to clear retained installation state topic {topic}: {exc}")

    def _parse_agent_id(self, topic: str) -> str:
        parts = str(topic or "").split("/")
        if len(parts) != 5:
            return ""
        if parts[0] != "ir" or parts[1] != "agents" or parts[3] != "installation" or parts[4] != "state":
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
        status = str(payload.get("status") or "").strip().lower()
        if not status:
            return {}

        progress = self._parse_optional_int(payload.get("progress_pct"))
        if progress is not None:
            progress = max(0, min(progress, 100))

        normalized: Dict[str, Any] = {
            "request_id": str(payload.get("request_id") or "").strip(),
            "status": status,
            "in_progress": status in self.IN_PROGRESS_STATUSES,
            "progress_pct": progress,
            "target_version": str(payload.get("target_version") or "").strip(),
            "current_version": str(payload.get("current_version") or "").strip(),
            "message": str(payload.get("message") or "").strip(),
            "error_code": str(payload.get("error_code") or "").strip(),
            "updated_at": self._parse_float(payload.get("updated_at"), default=time.time()),
        }

        return normalized

    def _parse_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    def _parse_optional_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None
