import asyncio
import json
import logging
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Set

from fastapi import WebSocket
from jmqtt import MQTTMessage, QualityOfService as QoS

from database import Database
from .runtime_loader import RuntimeLoader


class AgentLogHub:
    LOG_TOPIC_WILDCARD = "ir/agents/+/logs"
    MAX_LOGS_PER_AGENT = 100

    def __init__(self, runtime_loader: RuntimeLoader, database: Database, local_agent_id: str) -> None:
        self._runtime_loader = runtime_loader
        self._database = database
        self._local_agent_id = str(local_agent_id or "").strip()

        self._logger = logging.getLogger("agent_log_hub")
        self._lock = threading.Lock()
        self._running = False
        self._subscribed = False

        self._events: Dict[str, Deque[Dict[str, Any]]] = {}
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_lock: Optional[asyncio.Lock] = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()

    def start(self) -> None:
        connection = self._runtime_loader.mqtt_connection()
        if connection is None:
            return
        with self._lock:
            if self._running and self._subscribed:
                return
        try:
            connection.subscribe(self.LOG_TOPIC_WILDCARD, self._on_agent_log, qos=QoS.AtLeastOnce)
        except Exception as exc:
            self._logger.warning(f"Failed to subscribe agent log topic {self.LOG_TOPIC_WILDCARD}: {exc}")
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
        if not connection or not subscribed:
            return
        try:
            connection.unsubscribe(self.LOG_TOPIC_WILDCARD)
        except Exception as exc:
            self._logger.warning(f"Failed to unsubscribe agent log topic {self.LOG_TOPIC_WILDCARD}: {exc}")

    async def connect(self, agent_id: str, websocket: WebSocket) -> None:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        async with self._get_async_lock():
            connections = self._connections.setdefault(normalized_agent_id, set())
            connections.add(websocket)

    async def disconnect(self, agent_id: str, websocket: WebSocket) -> None:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return
        async with self._get_async_lock():
            connections = self._connections.get(normalized_agent_id)
            if not connections:
                return
            connections.discard(websocket)
            if not connections:
                self._connections.pop(normalized_agent_id, None)

    def can_stream_agent(self, agent_id: str) -> bool:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return False
        agent = self._database.agents.get(normalized_agent_id)
        if not agent:
            return False
        if bool(agent.get("pending")):
            return False
        transport = str(agent.get("transport") or "").strip()
        return transport in ("local", "mqtt")

    def snapshot(self, agent_id: str, limit: int = 100) -> list[Dict[str, Any]]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return []
        bounded_limit = max(1, min(int(limit or 0), self.MAX_LOGS_PER_AGENT))
        with self._lock:
            history = list(self._events.get(normalized_agent_id, deque()))
        if not history:
            return []
        return [dict(item) for item in history[-bounded_limit:]]

    def clear_agent_logs(self, agent_id: str) -> None:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return
        with self._lock:
            self._events.pop(normalized_agent_id, None)

    def record_local(self, agent_id: str, event: Dict[str, Any]) -> None:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return
        if not self._is_tracked_local_agent(normalized_agent_id):
            return
        normalized_event = self._normalize_event(event)
        if not normalized_event:
            return
        self._append_event(normalized_agent_id, normalized_event)

    def _on_agent_log(self, connection: Any, client: Any, userdata: Any, message: MQTTMessage) -> None:
        agent_id = self._parse_agent_id(message.topic)
        if not agent_id:
            return
        if not self._is_tracked_mqtt_agent(agent_id):
            return
        payload = self._parse_payload(message)
        if payload is None:
            return
        normalized_event = self._normalize_event(payload)
        if not normalized_event:
            return
        self._append_event(agent_id, normalized_event)

    def _append_event(self, agent_id: str, event: Dict[str, Any]) -> None:
        with self._lock:
            entries = self._events.get(agent_id)
            if entries is None:
                entries = deque(maxlen=self.MAX_LOGS_PER_AGENT)
                self._events[agent_id] = entries
            entries.append(event)
        self._broadcast(agent_id, event)

    def _broadcast(self, agent_id: str, payload: Dict[str, Any]) -> None:
        if not self._loop:
            return
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop and running_loop is self._loop:
            self._loop.create_task(self._broadcast_async(agent_id, payload))
        else:
            asyncio.run_coroutine_threadsafe(self._broadcast_async(agent_id, payload), self._loop)

    async def _broadcast_async(self, agent_id: str, payload: Dict[str, Any]) -> None:
        async with self._get_async_lock():
            connections = list(self._connections.get(agent_id) or [])
        if not connections:
            return

        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)

        if stale:
            async with self._get_async_lock():
                active = self._connections.get(agent_id)
                if not active:
                    return
                for websocket in stale:
                    active.discard(websocket)
                if not active:
                    self._connections.pop(agent_id, None)

    def _is_tracked_mqtt_agent(self, agent_id: str) -> bool:
        agent = self._database.agents.get(agent_id)
        if not agent:
            return False
        if bool(agent.get("pending")):
            return False
        transport = str(agent.get("transport") or "").strip()
        return transport == "mqtt"

    def _is_tracked_local_agent(self, agent_id: str) -> bool:
        if not self._local_agent_id or agent_id != self._local_agent_id:
            return False
        agent = self._database.agents.get(agent_id)
        if not agent:
            return False
        if bool(agent.get("pending")):
            return False
        transport = str(agent.get("transport") or "").strip()
        return transport == "local"

    def _parse_agent_id(self, topic: str) -> str:
        parts = str(topic or "").split("/")
        if len(parts) != 4:
            return ""
        if parts[0] != "ir" or parts[1] != "agents" or parts[3] != "logs":
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

    def _normalize_event(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        raw_message = payload.get("message")
        message = self._safe_text(raw_message, max_length=300, fallback="")
        if not message:
            return None
        event: Dict[str, Any] = {
            "ts": self._safe_ts(payload.get("ts")),
            "level": self._normalize_level(payload.get("level")),
            "category": self._safe_text(payload.get("category"), max_length=40, fallback="runtime"),
            "message": message,
        }
        request_id = self._safe_text(payload.get("request_id"), max_length=80, fallback="")
        if request_id:
            event["request_id"] = request_id
        error_code = self._safe_text(payload.get("error_code"), max_length=80, fallback="")
        if error_code:
            event["error_code"] = error_code
        meta = payload.get("meta")
        if isinstance(meta, dict) and meta:
            event["meta"] = self._sanitize_meta(meta, depth=0)
        return event

    def _safe_ts(self, value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return float(time.time())

    def _normalize_level(self, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in ("debug", "info", "warn", "error"):
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

    def _get_async_lock(self) -> asyncio.Lock:
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock
