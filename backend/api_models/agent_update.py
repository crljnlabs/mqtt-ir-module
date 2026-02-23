from typing import Optional

from pydantic import BaseModel, Field


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255, description="Agent display name")
    icon: Optional[str] = Field(default=None, max_length=128, description="Optional MDI icon key for the agent")
    configuration_url: Optional[str] = Field(
        default=None,
        max_length=1024,
        description="Optional Home Assistant configuration URL for this agent device",
    )
