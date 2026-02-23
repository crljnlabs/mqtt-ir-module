from typing import Any, Dict

from .errors import AgentRoutingError


class MqttTransport:
    def __init__(self, command_client: Any, agent_id: str) -> None:
        self._command_client = command_client
        self._agent_id = str(agent_id or "").strip()

    def learn_capture(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        timeout_seconds = 20.0
        try:
            timeout_ms = int(payload.get("timeout_ms") or 0)
            if timeout_ms > 0:
                timeout_seconds = max(5.0, (timeout_ms / 1000.0) + 5.0)
        except Exception:
            timeout_seconds = 20.0
        try:
            return self._command_client.learn_capture(
                agent_id=self._agent_id,
                payload=payload,
                timeout_seconds=timeout_seconds,
            )
        except AgentRoutingError as exc:
            if str(exc.code or "").strip() == "timeout":
                raise TimeoutError(exc.message) from exc
            raise

    def learn_start(self, session: Dict[str, Any]) -> Dict[str, Any]:
        return self._command_client.learn_start(agent_id=self._agent_id, session=session)

    def learn_stop(self, session: Dict[str, Any]) -> Dict[str, Any]:
        return self._command_client.learn_stop(agent_id=self._agent_id, session=session)

    def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        timeout_seconds = 12.0
        try:
            mode = str(payload.get("mode") or "").strip().lower()
            hold_ms = int(payload.get("hold_ms") or 0)
            if mode == "hold" and hold_ms > 0:
                timeout_seconds = max(12.0, (hold_ms / 1000.0) + 5.0)
        except Exception:
            timeout_seconds = 12.0
        return self._command_client.send(
            agent_id=self._agent_id,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
