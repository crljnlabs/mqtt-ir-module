from pydantic import BaseModel, Field


class AgentDebugUpdate(BaseModel):
    debug: bool = Field(..., description="Enable debug-level runtime logs on the remote MQTT agent")
