import logging
import time
from typing import Any, Callable, Dict, Optional


DispatchFn = Callable[[str, Dict[str, Any]], None]
AgentIdResolver = Callable[[], str]


class AgentLogReporter:
    _LEVEL_ORDER = {
        "debug": 10,
        "info": 20,
        "warn": 30,
        "error": 40,
    }
    _PYTHON_LEVEL = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "error": logging.ERROR,
    }

    def __init__(
        self,
        agent_id_resolver: AgentIdResolver,
        logger_name: str,
        dispatch: Optional[DispatchFn] = None,
        min_dispatch_level: str = "info",
    ) -> None:
        self._agent_id_resolver = agent_id_resolver
        self._logger = logging.getLogger(logger_name)
        self._dispatch = dispatch
        self._min_dispatch_level = self._normalize_level(min_dispatch_level)

    def set_min_dispatch_level(self, level: str) -> None:
        self._min_dispatch_level = self._normalize_level(level)

    def emit(
        self,
        level: str,
        category: str,
        message: str,
        request_id: Optional[str] = None,
        error_code: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        normalized_level = self._normalize_level(level)
        event = self._build_event(
            level=normalized_level,
            category=category,
            message=message,
            request_id=request_id,
            error_code=error_code,
            meta=meta,
        )
        self._log_python(event)
        if not self._dispatch:
            return
        if not self._should_dispatch(normalized_level):
            return
        agent_id = str(self._agent_id_resolver() or "").strip()
        if not agent_id:
            return
        try:
            self._dispatch(agent_id, event)
        except Exception as exc:
            self._logger.warning(f"Failed to dispatch agent log event: {exc}")

    def debug(self, category: str, message: str, meta: Optional[Dict[str, Any]] = None) -> None:
        self.emit(level="debug", category=category, message=message, meta=meta)

    def info(
        self,
        category: str,
        message: str,
        request_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.emit(level="info", category=category, message=message, request_id=request_id, meta=meta)

    def warn(
        self,
        category: str,
        message: str,
        request_id: Optional[str] = None,
        error_code: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.emit(
            level="warn",
            category=category,
            message=message,
            request_id=request_id,
            error_code=error_code,
            meta=meta,
        )

    def error(
        self,
        category: str,
        message: str,
        request_id: Optional[str] = None,
        error_code: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.emit(
            level="error",
            category=category,
            message=message,
            request_id=request_id,
            error_code=error_code,
            meta=meta,
        )

    def _build_event(
        self,
        level: str,
        category: str,
        message: str,
        request_id: Optional[str],
        error_code: Optional[str],
        meta: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        event: Dict[str, Any] = {
            "ts": float(time.time()),
            "level": level,
            "category": self._safe_text(category, max_length=40, fallback="runtime"),
            "message": self._safe_text(message, max_length=300, fallback="event"),
        }
        normalized_request_id = self._safe_text(request_id, max_length=80, fallback="")
        if normalized_request_id:
            event["request_id"] = normalized_request_id
        normalized_error_code = self._safe_text(error_code, max_length=80, fallback="")
        if normalized_error_code:
            event["error_code"] = normalized_error_code
        if isinstance(meta, dict) and meta:
            event["meta"] = self._sanitize_meta(meta, depth=0)
        return event

    def _log_python(self, event: Dict[str, Any]) -> None:
        level = str(event.get("level") or "info")
        category = str(event.get("category") or "runtime")
        message = str(event.get("message") or "event")
        request_id = str(event.get("request_id") or "").strip()
        error_code = str(event.get("error_code") or "").strip()
        suffix_parts = []
        if request_id:
            suffix_parts.append(f"request_id={request_id}")
        if error_code:
            suffix_parts.append(f"error_code={error_code}")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        python_level = self._PYTHON_LEVEL.get(level, logging.INFO)
        self._logger.log(python_level, f"[agent:{category}] {message}{suffix}")

    def _should_dispatch(self, level: str) -> bool:
        current = self._LEVEL_ORDER.get(level, 20)
        minimum = self._LEVEL_ORDER.get(self._min_dispatch_level, 20)
        return current >= minimum

    def _normalize_level(self, level: str) -> str:
        normalized = str(level or "").strip().lower()
        if normalized in self._LEVEL_ORDER:
            return normalized
        if normalized == "warning":
            return "warn"
        return "info"

    def _safe_text(self, value: Any, max_length: int, fallback: str) -> str:
        text = str(value or "").strip()
        if not text:
            return fallback
        if len(text) <= max_length:
            return text
        return f"{text[:max_length - 3]}..."

    def _sanitize_meta(self, value: Dict[str, Any], depth: int) -> Dict[str, Any]:
        if depth > 3:
            return {"truncated": True}
        result: Dict[str, Any] = {}
        items = list(value.items())
        for index, (raw_key, raw_item) in enumerate(items):
            if index >= 16:
                result["truncated"] = True
                break
            key = self._safe_text(raw_key, max_length=40, fallback="key")
            result[key] = self._sanitize_meta_value(raw_item, depth + 1)
        return result

    def _sanitize_meta_value(self, value: Any, depth: int) -> Any:
        if depth > 3:
            return "..."
        if value is None:
            return None
        if isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return self._safe_text(value, max_length=240, fallback="")
        if isinstance(value, dict):
            return self._sanitize_meta(value, depth)
        if isinstance(value, (list, tuple)):
            items = []
            for index, item in enumerate(value):
                if index >= 12:
                    items.append("...")
                    break
                items.append(self._sanitize_meta_value(item, depth + 1))
            return items
        return self._safe_text(str(value), max_length=240, fallback="")
