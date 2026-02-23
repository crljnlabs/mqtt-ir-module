from typing import Dict, Any

from .mqtt_transport import MqttTransport


class MqttAgent:
    def __init__(self, transport: MqttTransport, agent_id: str, name: str, capabilities: Dict[str, Any]) -> None:
        self._transport = transport
        self._agent_id = agent_id
        self._name = name
        self._capabilities = dict(capabilities or {})

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def transport(self) -> str:
        return "mqtt"

    @property
    def capabilities(self) -> Dict[str, Any]:
        return dict(self._capabilities)

    def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._transport.send(payload)

    def learn_start(self, session: Dict[str, Any]) -> Dict[str, Any]:
        return self._transport.learn_start(session)

    def learn_stop(self, session: Dict[str, Any]) -> Dict[str, Any]:
        return self._transport.learn_stop(session)

    def learn_capture(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._transport.learn_capture(payload)

    def get_status(self) -> Dict[str, Any]:
        return {
            "agent_id": self._agent_id,
            "name": self._name,
            "transport": self.transport,
            "status": "online",
            "busy": {"learning": False, "sending": False},
            "capabilities": self.capabilities,
        }
