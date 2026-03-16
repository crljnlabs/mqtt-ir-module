import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from jmqtt import MQTTMessage, QualityOfService as QoS

from .runtime_loader import RuntimeLoader


class AgentInstallationStateHub:
    STATE_TOPIC_WILDCARD = "ir/agents/+/installation/state"
    AVAILABILITY_TOPIC_WILDCARD = "ir/agents/+/state/availability"
    IN_PROGRESS_STATUSES = {"started", "downloading", "installing"}
    TERMINAL_CLEAR_STATUSES = {"finished", "cancelled"}
    FINISH_CLEAR_DELAY_SECONDS = 20.0
    STALE_PROGRESS_TIMEOUT_SECONDS = 120.0
    # How long the device may stay offline during active OTA before declaring failure.
    OFFLINE_FAILURE_TIMEOUT_SECONDS = 15.0
    # Delay after "online" before querying version; gives device time to publish its state topics.
    ONLINE_VERSION_CHECK_DELAY_SECONDS = 3.0

    def __init__(
        self,
        runtime_loader: RuntimeLoader,
        version_provider: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._runtime_loader = runtime_loader
        self._version_provider = version_provider
        self._logger = logging.getLogger("agent_installation_state_hub")
        self._lock = threading.Lock()
        self._running = False
        self._subscribed = False
        self._states: Dict[str, Dict[str, Any]] = {}
        self._clear_timers: Dict[str, threading.Timer] = {}
        # Tracks agents whose OTA was declared failure because they went offline.
        # Maps agent_id → target_version so we can correct to "finished" if they return
        # on the right firmware version.
        self._offline_failed: Dict[str, str] = {}
        self._offline_timers: Dict[str, threading.Timer] = {}

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
            self._logger.warning(f"Failed to subscribe installation state topic {self.STATE_TOPIC_WILDCARD}: {exc}")
        try:
            connection.subscribe(self.AVAILABILITY_TOPIC_WILDCARD, self._on_availability, qos=QoS.AtLeastOnce)
        except Exception as exc:
            self._logger.warning(f"Failed to subscribe availability topic {self.AVAILABILITY_TOPIC_WILDCARD}: {exc}")

    def stop(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        with self._lock:
            subscribed = self._subscribed
            self._running = False
            self._subscribed = False
            self._states.clear()
            self._offline_failed.clear()
            timers = list(self._clear_timers.values()) + list(self._offline_timers.values())
            self._clear_timers.clear()
            self._offline_timers.clear()
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
        try:
            connection.unsubscribe(self.AVAILABILITY_TOPIC_WILDCARD)
        except Exception as exc:
            self._logger.warning(f"Failed to unsubscribe availability topic {self.AVAILABILITY_TOPIC_WILDCARD}: {exc}")

    def get_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return None
        self._recover_stale_state(normalized_agent_id)
        with self._lock:
            state = self._states.get(normalized_agent_id)
        if not state:
            return None
        return self._public_payload(state)

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

    def reset_state(self, agent_id: str) -> bool:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return False
        self._cancel_clear_timer(normalized_agent_id)
        with self._lock:
            existed = normalized_agent_id in self._states
            self._states.pop(normalized_agent_id, None)
        self._clear_retained(normalized_agent_id)
        return existed

    def reconcile_with_runtime_version(self, agent_id: str, current_version: str) -> Optional[Dict[str, Any]]:
        normalized_agent_id = str(agent_id or "").strip()
        normalized_version = str(current_version or "").strip()
        if not normalized_agent_id or not normalized_version:
            return None
        should_publish = False
        should_schedule_clear = False
        payload: Optional[Dict[str, Any]] = None
        now = time.time()
        with self._lock:
            state = self._states.get(normalized_agent_id)
            if not state:
                return None
            updated = dict(state)
            changed = False
            reported_current_version = str(updated.get("current_version") or "").strip()

            if reported_current_version != normalized_version:
                updated["current_version"] = normalized_version
                updated["_state_seen_at"] = now
                changed = True

            if bool(updated.get("in_progress")):
                target_version = str(updated.get("target_version") or "").strip()
                if (
                    target_version
                    and target_version == normalized_version
                    and reported_current_version
                    and reported_current_version != normalized_version
                ):
                    updated["status"] = "finished"
                    updated["in_progress"] = False
                    updated["progress_pct"] = 100
                    updated["message"] = "OTA update completed"
                    updated["error_code"] = ""
                    updated["updated_at"] = now
                    updated["_state_seen_at"] = now
                    changed = True
                    should_publish = True
                    should_schedule_clear = True

            if not changed:
                return self._public_payload(state)

            self._states[normalized_agent_id] = updated
            payload = self._public_payload(updated)

        if should_schedule_clear:
            self._schedule_finished_clear(normalized_agent_id)
        if should_publish and payload is not None:
            self._publish_retained_state(normalized_agent_id, payload)
        return payload

    def _on_availability(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        del connection
        del client
        del userdata
        agent_id = self._parse_availability_agent_id(message.topic)
        if not agent_id:
            return
        status = str(message.text or "").strip().lower()
        if status == "offline":
            if self.is_in_progress(agent_id):
                self._start_offline_timer(agent_id)
        elif status == "online":
            self._cancel_offline_timer(agent_id)
            with self._lock:
                has_offline_failed = agent_id in self._offline_failed
            if has_offline_failed:
                # Device came back after failure was declared — check version after a short
                # delay so the device has time to publish its state/runtime topic.
                timer = threading.Timer(
                    self.ONLINE_VERSION_CHECK_DELAY_SECONDS,
                    self._try_version_reconcile_after_offline,
                    args=(agent_id,),
                )
                timer.daemon = True
                timer.start()

    def _start_offline_timer(self, agent_id: str) -> None:
        self._cancel_offline_timer(agent_id)
        timer = threading.Timer(
            self.OFFLINE_FAILURE_TIMEOUT_SECONDS,
            self._on_offline_timer,
            args=(agent_id,),
        )
        timer.daemon = True
        with self._lock:
            self._offline_timers[agent_id] = timer
        timer.start()

    def _cancel_offline_timer(self, agent_id: str) -> None:
        with self._lock:
            timer = self._offline_timers.pop(agent_id, None)
        if timer is None:
            return
        try:
            timer.cancel()
        except Exception:
            pass

    def _on_offline_timer(self, agent_id: str) -> None:
        recovered_payload: Optional[Dict[str, Any]] = None
        target_version = ""
        now = time.time()
        with self._lock:
            self._offline_timers.pop(agent_id, None)
            state = self._states.get(agent_id)
            if isinstance(state, dict) and bool(state.get("in_progress")):
                target_version = str(state.get("target_version") or "")
                recovered = dict(state)
                recovered["status"] = "failure"
                recovered["in_progress"] = False
                recovered["message"] = f"Device went offline for more than {self.OFFLINE_FAILURE_TIMEOUT_SECONDS:.0f}s during OTA"
                recovered["error_code"] = "ota_device_offline"
                recovered["updated_at"] = now
                recovered["_state_seen_at"] = now
                self._states[agent_id] = recovered
                recovered_payload = self._public_payload(recovered)
            if target_version:
                self._offline_failed[agent_id] = target_version
        if recovered_payload is None:
            return
        self._logger.warning(
            f"OTA failure for {agent_id}: device went offline and did not recover within "
            f"{self.OFFLINE_FAILURE_TIMEOUT_SECONDS:.0f}s"
        )
        self._publish_retained_state(agent_id, recovered_payload)

    def _try_version_reconcile_after_offline(self, agent_id: str) -> None:
        """Called after device comes back online following an offline-triggered OTA failure.
        Corrects state to 'finished' if the device is now on the target version."""
        with self._lock:
            target_version = self._offline_failed.pop(agent_id, "")
        if not target_version or not self._version_provider:
            return
        current_version = self._version_provider(agent_id)
        if not current_version or current_version != target_version:
            return
        # Version matches — OTA actually succeeded despite the offline event.
        now = time.time()
        payload: Optional[Dict[str, Any]] = None
        with self._lock:
            state = self._states.get(agent_id)
            if not isinstance(state, dict):
                return
            updated = dict(state)
            updated["status"] = "finished"
            updated["in_progress"] = False
            updated["progress_pct"] = 100
            updated["current_version"] = current_version
            updated["message"] = "OTA update completed"
            updated["error_code"] = ""
            updated["updated_at"] = now
            updated["_state_seen_at"] = now
            self._states[agent_id] = updated
            payload = self._public_payload(updated)
        if payload is None:
            return
        self._logger.info(f"OTA for {agent_id} corrected to finished after device returned on target version {target_version}")
        self._schedule_finished_clear(agent_id)
        self._publish_retained_state(agent_id, payload)

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
        if str(normalized.get("status") or "") in self.TERMINAL_CLEAR_STATUSES:
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
            status = str(state.get("status") or "") if isinstance(state, dict) else ""
            if status in self.TERMINAL_CLEAR_STATUSES:
                self._states.pop(agent_id, None)
                should_clear = True
        if should_clear:
            self._clear_retained(agent_id)

    def _recover_stale_state(self, agent_id: str) -> None:
        now = time.time()
        recovered_payload: Optional[Dict[str, Any]] = None
        with self._lock:
            state = self._states.get(agent_id)
            if not isinstance(state, dict):
                return
            if not bool(state.get("in_progress")):
                return
            seen_at = self._parse_float(state.get("_state_seen_at"), default=now)
            if (now - seen_at) < self.STALE_PROGRESS_TIMEOUT_SECONDS:
                return

            recovered = dict(state)
            recovered["status"] = "failure"
            recovered["in_progress"] = False
            recovered["message"] = "Installation status timed out"
            recovered["error_code"] = "ota_status_timeout"
            recovered["updated_at"] = now
            recovered["_state_seen_at"] = now
            self._states[agent_id] = recovered
            recovered_payload = self._public_payload(recovered)

        self._cancel_clear_timer(agent_id)
        if recovered_payload is None:
            return
        self._logger.warning(f"Recovered stale OTA installation state for {agent_id} as failure")
        self._publish_retained_state(agent_id, recovered_payload)

    def _clear_retained(self, agent_id: str) -> None:
        connection = self._runtime_loader.mqtt_connection()
        if connection is None:
            return
        topic = f"ir/agents/{agent_id}/installation/state"
        try:
            connection.publish(topic, "", qos=QoS.AtLeastOnce, retain=True)
        except Exception as exc:
            self._logger.warning(f"Failed to clear retained installation state topic {topic}: {exc}")

    def _publish_retained_state(self, agent_id: str, payload: Dict[str, Any]) -> None:
        connection = self._runtime_loader.mqtt_connection()
        if connection is None:
            return
        topic = f"ir/agents/{agent_id}/installation/state"
        try:
            connection.publish(
                topic,
                json.dumps(payload, separators=(",", ":")),
                qos=QoS.AtLeastOnce,
                retain=True,
            )
        except Exception as exc:
            self._logger.warning(f"Failed to publish recovered installation state topic {topic}: {exc}")

    def _parse_agent_id(self, topic: str) -> str:
        parts = str(topic or "").split("/")
        if len(parts) != 5:
            return ""
        if parts[0] != "ir" or parts[1] != "agents" or parts[3] != "installation" or parts[4] != "state":
            return ""
        return parts[2].strip()

    def _parse_availability_agent_id(self, topic: str) -> str:
        parts = str(topic or "").split("/")
        if len(parts) != 5:
            return ""
        if parts[0] != "ir" or parts[1] != "agents" or parts[3] != "state" or parts[4] != "availability":
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
            "_state_seen_at": time.time(),
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

    def _public_payload(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in state.items() if not str(k).startswith("_")}
