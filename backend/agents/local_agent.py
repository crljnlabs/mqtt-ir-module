import threading
from typing import Any, Dict, Optional

from .local_transport import LocalTransport


class LocalAgent:
    def __init__(
        self,
        transport: LocalTransport,
        agent_id: str = "local",
        name: str = "Local Agent",
        log_reporter: Optional[Any] = None,
    ) -> None:
        self._transport = transport
        self._agent_id = agent_id
        self._name = name
        self._log_reporter = log_reporter
        self._learning_active = False
        self._lock = threading.Lock()
        self._capabilities = {
            "canLearn": True,
            "formatRaw": True,
            "maxPayloadBytes": 65536,
        }

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def transport(self) -> str:
        return "local"

    @property
    def capabilities(self) -> Dict[str, Any]:
        return dict(self._capabilities)

    def set_log_reporter(self, log_reporter: Optional[Any]) -> None:
        with self._lock:
            self._log_reporter = log_reporter

    def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            learning_active = self._learning_active
        if learning_active:
            self._log(
                level="warn",
                category="send",
                message="Send rejected because learning is active",
                error_code="learning_active",
            )
            raise RuntimeError("Cannot send while learning is active")
        mode = str(payload.get("mode") or "press").strip().lower() or "press"
        hold_ms = int(payload.get("hold_ms") or 0)
        button_id = int(payload.get("button_id") or 0)
        self._log(
            level="info",
            category="send",
            message="Send started",
            meta={"mode": mode, "hold_ms": hold_ms, "button_id": button_id},
        )
        try:
            result = self._transport.send(payload)
            self._log(
                level="info",
                category="send",
                message="Send finished",
                meta={"mode": mode, "hold_ms": hold_ms, "button_id": button_id},
            )
            return result
        except Exception as exc:
            self._log(
                level="error",
                category="send",
                message=f"Send failed: {exc}",
                error_code="send_failed",
                meta={"mode": mode, "hold_ms": hold_ms, "button_id": button_id},
            )
            raise

    def learn_start(self, session: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._learning_active = True
        self._log(level="info", category="learn", message="Learn session started")
        return {"ok": True}

    def learn_stop(self, session: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._learning_active = False
        self._log(level="info", category="learn", message="Learn session stopped")
        return {"ok": True}

    def learn_capture(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        timeout_ms = int(payload.get("timeout_ms") or 0)
        if timeout_ms <= 0:
            self._log(
                level="warn",
                category="learn",
                message="Learn capture rejected because timeout_ms is invalid",
                error_code="validation_error",
            )
            raise ValueError("timeout_ms must be > 0")
        mode = str(payload.get("mode") or "").strip().lower() or "unknown"
        with self._lock:
            learning_active = self._learning_active
        if not learning_active:
            self._log(
                level="warn",
                category="learn",
                message="Learn capture rejected because session is not active",
                error_code="learning_not_running",
                meta={"mode": mode, "timeout_ms": timeout_ms},
            )
            raise RuntimeError("Learning session is not running")
        self._log(
            level="info",
            category="learn",
            message="Learn capture started",
            meta={"mode": mode, "timeout_ms": timeout_ms},
        )
        try:
            result = self._transport.learn_capture(timeout_ms)
            raw = str(result.get("raw") or "")
            self._log(
                level="info",
                category="learn",
                message="Learn capture finished",
                meta={"mode": mode, "timeout_ms": timeout_ms, "raw_length": len(raw)},
            )
            return result
        except TimeoutError as exc:
            self._log(
                level="warn",
                category="learn",
                message=f"Learn capture timed out: {exc}",
                error_code="timeout",
                meta={"mode": mode, "timeout_ms": timeout_ms},
            )
            raise
        except Exception as exc:
            self._log(
                level="error",
                category="learn",
                message=f"Learn capture failed: {exc}",
                error_code="capture_failed",
                meta={"mode": mode, "timeout_ms": timeout_ms},
            )
            raise

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            learning_active = self._learning_active
        return {
            "agent_id": self._agent_id,
            "name": self._name,
            "transport": self.transport,
            "status": "online",
            "busy": {"learning": learning_active, "sending": False},
            "capabilities": self.capabilities,
        }

    def _log(
        self,
        level: str,
        category: str,
        message: str,
        error_code: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            reporter = self._log_reporter
        if reporter is None:
            return
        reporter.emit(level=level, category=category, message=message, error_code=error_code, meta=meta)
