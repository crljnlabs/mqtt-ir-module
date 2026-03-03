from typing import Protocol, Dict, Any


class Agent(Protocol):
    @property
    def agent_id(self) -> str:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def transport(self) -> str:
        ...

    @property
    def capabilities(self) -> Dict[str, Any]:
        ...

    def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def learn_start(self, session: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def learn_stop(self, session: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def learn_capture(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def learn_hold_capture(self, session: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def get_status(self) -> Dict[str, Any]:
        ...
