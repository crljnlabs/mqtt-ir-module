import json
import logging
import threading
import time
from typing import Any, Dict, Optional

from jmqtt import MQTTMessage, QualityOfService as QoS

from agents.local_agent import LocalAgent
from .agent_runtime_state_store import AgentRuntimeStateStore
from .agent_log_reporter import AgentLogReporter
from .runtime_loader import RuntimeLoader


class AgentCommandHandler:
    COMMAND_TOPIC_PREFIX = "ir/agents"
    RESPONSE_TOPIC_PREFIX = "ir/hubs"

    def __init__(
        self,
        runtime_loader: RuntimeLoader,
        binding_store: AgentRuntimeStateStore,
        local_agent: LocalAgent,
        log_reporter: Optional[AgentLogReporter] = None,
    ) -> None:
        self._runtime_loader = runtime_loader
        self._binding_store = binding_store
        self._local_agent = local_agent
        self._logger = logging.getLogger("agent_command_handler")
        self._log_reporter = log_reporter or AgentLogReporter(
            agent_id_resolver=self._agent_uid,
            logger_name="agent_command_events",
            dispatch=None,
            min_dispatch_level="info",
        )
        self._lock = threading.Lock()
        self._running = False
        self._subscribed_topic = ""

    def start(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        if connection is None:
            return

        agent_uid = self._agent_uid()
        if not agent_uid:
            return

        topic = f"{self.COMMAND_TOPIC_PREFIX}/{agent_uid}/cmd/#"
        connection.subscribe(topic, self._on_command, qos=QoS.AtLeastOnce)
        with self._lock:
            self._running = True
            self._subscribed_topic = topic

    def stop(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        with self._lock:
            topic = self._subscribed_topic
            self._subscribed_topic = ""
            self._running = False

        if connection is None or not topic:
            return

        try:
            connection.unsubscribe(topic)
        except Exception as exc:
            self._logger.warning(f"Failed to unsubscribe command topic {topic}: {exc}")

    def _on_command(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        expected_agent_uid = self._agent_uid()
        agent_uid_from_topic, command = self._parse_command_topic(message.topic)
        if not expected_agent_uid or not agent_uid_from_topic or agent_uid_from_topic != expected_agent_uid:
            return
        if command not in (
            "send",
            "learn/start",
            "learn/capture",
            "learn/stop",
            "runtime/debug/get",
            "runtime/debug/set",
            "runtime/config/get",
            "runtime/config/set",
            "runtime/reboot",
            "runtime/ota/start",
        ):
            return

        payload = self._parse_payload(message)
        if payload is None:
            return

        request_id = str(payload.get("request_id") or "").strip()
        request_hub_id = str(payload.get("hub_id") or "").strip()
        if not request_id or not request_hub_id:
            return

        binding_hub_id = self._binding_store.hub_id()
        if not binding_hub_id or request_hub_id != binding_hub_id:
            return

        response_topic = f"{self.RESPONSE_TOPIC_PREFIX}/{request_hub_id}/agents/{expected_agent_uid}/resp/{request_id}"
        command_category = self._command_category(command)
        started_at = time.time()
        self._log_reporter.debug(
            category=command_category,
            message="Agent command received",
            meta={"command": command},
        )
        self._log_reporter.info(
            category=command_category,
            message="Agent command started",
            request_id=request_id,
            meta={"command": command},
        )

        try:
            result = self._execute_command(command=command, payload=payload)
            duration_ms = int((time.time() - started_at) * 1000)
            self._log_reporter.info(
                category=command_category,
                message="Agent command finished",
                request_id=request_id,
                meta={"command": command, "duration_ms": duration_ms},
            )
            response = {
                "request_id": request_id,
                "ok": True,
                "result": result,
                "responded_at": time.time(),
            }
        except TimeoutError as exc:
            duration_ms = int((time.time() - started_at) * 1000)
            self._log_reporter.warn(
                category=command_category,
                message=f"Agent command timed out: {exc}",
                request_id=request_id,
                error_code="timeout",
                meta={"command": command, "duration_ms": duration_ms},
            )
            response = self._error_response(
                request_id=request_id,
                code="timeout",
                message=str(exc),
                status_code=408,
            )
        except ValueError as exc:
            duration_ms = int((time.time() - started_at) * 1000)
            self._log_reporter.warn(
                category=command_category,
                message=f"Agent command validation failed: {exc}",
                request_id=request_id,
                error_code="validation_error",
                meta={"command": command, "duration_ms": duration_ms},
            )
            response = self._error_response(
                request_id=request_id,
                code="validation_error",
                message=str(exc),
                status_code=400,
            )
        except RuntimeError as exc:
            duration_ms = int((time.time() - started_at) * 1000)
            self._log_reporter.warn(
                category=command_category,
                message=f"Agent command rejected: {exc}",
                request_id=request_id,
                error_code="runtime_error",
                meta={"command": command, "duration_ms": duration_ms},
            )
            response = self._error_response(
                request_id=request_id,
                code="runtime_error",
                message=str(exc),
                status_code=409,
            )
        except Exception as exc:
            duration_ms = int((time.time() - started_at) * 1000)
            self._log_reporter.error(
                category=command_category,
                message=f"Agent command failed: {exc}",
                request_id=request_id,
                error_code="internal_error",
                meta={"command": command, "duration_ms": duration_ms},
            )
            response = self._error_response(
                request_id=request_id,
                code="internal_error",
                message=str(exc),
                status_code=500,
            )

        try:
            connection.publish(
                response_topic,
                json.dumps(response, separators=(",", ":")),
                qos=QoS.AtLeastOnce,
                retain=False,
            )
        except Exception as exc:
            self._log_reporter.warn(
                category=command_category,
                message=f"Failed to publish command response: {exc}",
                request_id=request_id,
                error_code="response_publish_failed",
                meta={"command": command},
            )
            self._logger.warning(f"Failed to publish command response topic={response_topic}: {exc}")

    def _execute_command(self, command: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if command == "send":
            return self._local_agent.send(payload)

        if command == "learn/start":
            session = payload.get("session")
            if session is None:
                session = {}
            if not isinstance(session, dict):
                raise ValueError("session must be an object")
            return self._local_agent.learn_start(session)

        if command == "learn/capture":
            return self._local_agent.learn_capture(payload)

        if command == "learn/stop":
            session = payload.get("session")
            if session is None:
                session = {}
            if not isinstance(session, dict):
                raise ValueError("session must be an object")
            return self._local_agent.learn_stop(session)

        if command == "runtime/debug/get":
            return {"debug": self._binding_store.debug_enabled()}

        if command == "runtime/debug/set":
            if "debug" not in payload:
                raise ValueError("debug is required")
            enabled = self._parse_debug_flag(payload.get("debug"))
            self._binding_store.set_debug(enabled)
            self._log_reporter.set_min_dispatch_level("debug" if enabled else "info")
            return {"debug": self._binding_store.debug_enabled()}

        if command == "runtime/config/get":
            state = self._binding_store.runtime_state()
            return {
                "ir_rx_pin": self._parse_optional_int(state.get("ir_rx_pin")),
                "ir_tx_pin": self._parse_optional_int(state.get("ir_tx_pin")),
                "reboot_required": bool(state.get("reboot_required")),
            }

        if command == "runtime/config/set":
            raise RuntimeError("runtime_config_not_supported")

        if command == "runtime/reboot":
            raise RuntimeError("runtime_reboot_not_supported")

        if command == "runtime/ota/start":
            raise RuntimeError("runtime_ota_not_supported")

        raise ValueError("Unknown command")

    def _parse_command_topic(self, topic: str) -> tuple[str, str]:
        parts = str(topic or "").split("/")
        if len(parts) < 5:
            return "", ""
        if parts[0] != "ir" or parts[1] != "agents" or parts[3] != "cmd":
            return "", ""
        agent_uid = parts[2].strip()
        command = "/".join(p.strip() for p in parts[4:] if p.strip())
        return agent_uid, command

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

    def _agent_uid(self) -> str:
        client_id = str(self._runtime_loader.mqtt_client_id() or "").strip()
        if client_id:
            return client_id
        runtime_status = self._runtime_loader.status()
        fallback = str(runtime_status.get("client_id") or runtime_status.get("node_id") or "").strip()
        return fallback

    def _error_response(self, request_id: str, code: str, message: str, status_code: int) -> Dict[str, Any]:
        return {
            "request_id": request_id,
            "ok": False,
            "error": {
                "code": str(code),
                "message": str(message),
                "status_code": int(status_code),
            },
            "responded_at": time.time(),
        }

    def _command_category(self, command: str) -> str:
        normalized = str(command or "").strip().lower()
        if normalized.startswith("learn/"):
            return "learn"
        if normalized == "send":
            return "send"
        return "runtime"

    def _parse_debug_flag(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        normalized = str(value or "").strip().lower()
        if normalized in ("1", "true", "yes", "y", "on"):
            return True
        if normalized in ("0", "false", "no", "n", "off"):
            return False
        raise ValueError("debug must be a boolean")

    def _parse_optional_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None
