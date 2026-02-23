from dataclasses import dataclass
from typing import Literal


ConnectionRole = Literal["hub", "agent"]


@dataclass
class MQTTConnectionModel:
    role: ConnectionRole
    host: str
    port: int
    username: str
    password: str
    node_id: str
    readable_name: str

    @staticmethod
    def technical_name_for_role(role: ConnectionRole) -> str:
        return f"ir-{role}"

    @staticmethod
    def readable_name_for_role(role: ConnectionRole) -> str:
        return "IR Hub" if role == "hub" else "IR Agent"

    @property
    def technical_name(self) -> str:
        return self.technical_name_for_role(self.role)

    @property
    def app_name(self) -> str:
        return self.technical_name

    @property
    def base_topic(self) -> str:
        if self.role == "hub":
            return f"ir/hubs/{self.node_id}"
        return f"ir/agents/{self.node_id}"

    @property
    def availability_topic(self) -> str:
        return f"{self.base_topic}/status"

    @property
    def is_mqtt_configured(self) -> bool:
        return bool(self.host)
