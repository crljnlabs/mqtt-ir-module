import json
import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

from jmqtt import MQTTMessage, QualityOfService as QoS

from agents.errors import AgentError
from .runtime_loader import RuntimeLoader


class AgentCommandClientHub:
    COMMAND_TOPIC_PREFIX = "ir/agents"
    RESPONSE_TOPIC_PREFIX = "ir/hubs"

    def __init__(
        self,
        runtime_loader: RuntimeLoader,
        on_agent_timeout: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._runtime_loader = runtime_loader
        self._on_agent_timeout = on_agent_timeout
        self._logger = logging.getLogger("agent_command_client_hub")
        self._lock = threading.Lock()
        self._running = False
        self._subscribed_topic = ""
        self._pending: Dict[str, Dict[str, Any]] = {}

    def start(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        if connection is None:
            return

        hub_id = self._hub_id()
        topic = f"{self.RESPONSE_TOPIC_PREFIX}/{hub_id}/agents/+/resp/+"
        connection.add_on_connect(self._on_mqtt_connect)
        connection.subscribe(topic, self._on_response, qos=QoS.AtLeastOnce)
        with self._lock:
            self._running = True
            self._subscribed_topic = topic

    def _on_mqtt_connect(self, connection: Any, _client: Any, _userdata: Any, _flags: Any) -> None:
        with self._lock:
            if not self._running:
                return
            topic = self._subscribed_topic
        if not topic:
            return
        try:
            connection.subscribe(topic, self._on_response, qos=QoS.AtLeastOnce)
        except Exception as exc:
            self._logger.warning(f"Failed to resubscribe response topic {topic}: {exc}")

    def stop(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        with self._lock:
            topic = self._subscribed_topic
            self._subscribed_topic = ""
            self._running = False

            pending_values = list(self._pending.values())
            self._pending.clear()
        for state in pending_values:
            event = state.get("event")
            if isinstance(event, threading.Event):
                event.set()

        if connection is None or not topic:
            return
        try:
            connection.unsubscribe(topic)
        except Exception as exc:
            self._logger.warning(f"Failed to unsubscribe response topic {topic}: {exc}")

    def send(self, agent_id: str, payload: Dict[str, Any], timeout_seconds: float = 12.0) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="send",
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    def learn_start(self, agent_id: str, session: Dict[str, Any], timeout_seconds: float = 8.0) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="learn/start",
            payload={"session": session},
            timeout_seconds=timeout_seconds,
        )

    def learn_capture(self, agent_id: str, payload: Dict[str, Any], timeout_seconds: float = 20.0) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="learn/capture",
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    def learn_stop(self, agent_id: str, session: Dict[str, Any], timeout_seconds: float = 8.0) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="learn/stop",
            payload={"session": session},
            timeout_seconds=timeout_seconds,
        )

    def learn_hold_capture(self, agent_id: str, session: Dict[str, Any], timeout_seconds: float = 30.0) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="learn/hold_capture",
            payload=dict(session or {}),
            timeout_seconds=timeout_seconds,
        )

    def runtime_debug_get(self, agent_id: str, timeout_seconds: float = 8.0) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="runtime/debug/get",
            payload={},
            timeout_seconds=timeout_seconds,
        )

    def runtime_debug_set(self, agent_id: str, debug: bool, timeout_seconds: float = 8.0) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="runtime/debug/set",
            payload={"debug": bool(debug)},
            timeout_seconds=timeout_seconds,
        )

    def runtime_config_get(self, agent_id: str, timeout_seconds: float = 8.0) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="runtime/config/get",
            payload={},
            timeout_seconds=timeout_seconds,
        )

    def runtime_config_set(
        self,
        agent_id: str,
        payload: Dict[str, Any],
        timeout_seconds: float = 8.0,
    ) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="runtime/config/set",
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    def runtime_reboot(self, agent_id: str, timeout_seconds: float = 8.0) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="runtime/reboot",
            payload={},
            timeout_seconds=timeout_seconds,
        )

    def runtime_ota_start(
        self,
        agent_id: str,
        payload: Dict[str, Any],
        timeout_seconds: float = 120.0,
    ) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="runtime/ota/start",
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    def runtime_ota_cancel(
        self,
        agent_id: str,
        timeout_seconds: float = 8.0,
    ) -> Dict[str, Any]:
        return self._request(
            agent_id=agent_id,
            command="runtime/ota/cancel",
            payload={},
            timeout_seconds=timeout_seconds,
        )

    def _request(self, agent_id: str, command: str, payload: Dict[str, Any], timeout_seconds: float) -> Dict[str, Any]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            raise AgentError(code="agent_required", message="agent_id is required", status_code=400)

        connection = self._runtime_loader.mqtt_connection()
        if connection is None:
            raise AgentError(code="mqtt_not_connected", message="MQTT is not connected", status_code=503)

        request_id = uuid.uuid4().hex
        hub_id = self._hub_id()
        timeout = max(0.5, float(timeout_seconds))
        request_payload = dict(payload or {})
        request_payload["request_id"] = request_id
        request_payload["hub_id"] = hub_id
        request_payload["requested_at"] = time.time()

        event = threading.Event()
        with self._lock:
            self._pending[request_id] = {
                "agent_id": normalized_agent_id,
                "event": event,
                "completed": False,
                "ok": False,
                "result": {},
                "error": None,
            }

        topic = f"{self.COMMAND_TOPIC_PREFIX}/{normalized_agent_id}/cmd/{command}"
        try:
            connection.publish(
                topic,
                json.dumps(request_payload, separators=(",", ":")),
                qos=QoS.AtLeastOnce,
                retain=False,
            )
        except Exception as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise AgentError(
                code="mqtt_publish_failed",
                message=f"Failed to publish agent command: {exc}",
                status_code=503,
            ) from exc

        event.wait(timeout)
        with self._lock:
            state = self._pending.pop(request_id, None)

        if not state or not bool(state.get("completed")):
            if self._on_agent_timeout is not None:
                try:
                    self._on_agent_timeout(normalized_agent_id)
                except Exception as exc:
                    self._logger.warning(f"Failed to handle agent timeout fallback for {normalized_agent_id}: {exc}")
            raise AgentError(
                code="agent_timeout",
                message=f"Agent {normalized_agent_id} did not respond in time",
                status_code=504,
            )

        if bool(state.get("ok")):
            result = state.get("result")
            if isinstance(result, dict):
                return result
            return {"value": result}

        error = state.get("error")
        if not isinstance(error, dict):
            raise AgentError(
                code="agent_error",
                message=f"Agent {normalized_agent_id} returned an unknown error",
                status_code=400,
            )

        code = str(error.get("code") or "agent_error")
        message = str(error.get("message") or f"Agent {normalized_agent_id} returned an error")
        try:
            status_code = int(error.get("status_code") or 400)
        except Exception:
            status_code = 400
        raise AgentError(code=code, message=message, status_code=status_code)

    def _on_response(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        agent_id, request_id = self._parse_response_topic(message.topic)
        if not agent_id or not request_id:
            return

        payload = self._parse_payload(message)
        if payload is None:
            return

        with self._lock:
            state = self._pending.get(request_id)
            if not state:
                return
            expected_agent_id = str(state.get("agent_id") or "").strip()
            if not expected_agent_id or expected_agent_id != agent_id:
                return

            payload_request_id = str(payload.get("request_id") or "").strip()
            if payload_request_id and payload_request_id != request_id:
                return

            ok = bool(payload.get("ok"))
            state["completed"] = True
            state["ok"] = ok
            if ok:
                state["result"] = payload.get("result")
                state["error"] = None
            else:
                error_value = payload.get("error")
                if isinstance(error_value, dict):
                    state["error"] = error_value
                else:
                    state["error"] = {
                        "code": "agent_error",
                        "message": "Agent returned an invalid error payload",
                        "status_code": 400,
                    }
            event = state.get("event")

        if isinstance(event, threading.Event):
            event.set()

    def _parse_response_topic(self, topic: str) -> tuple[str, str]:
        parts = str(topic or "").split("/")
        if len(parts) != 7:
            return "", ""
        if parts[0] != "ir" or parts[1] != "hubs" or parts[3] != "agents" or parts[5] != "resp":
            return "", ""
        return parts[4].strip(), parts[6].strip()

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

    def _hub_id(self) -> str:
        status = self._runtime_loader.status()
        return str(status.get("node_id") or "").strip() or self._runtime_loader.technical_name
