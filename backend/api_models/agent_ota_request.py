from typing import Optional

from pydantic import BaseModel, Field


class AgentOtaRequest(BaseModel):
    version: Optional[str] = Field(
        default=None,
        pattern=r"^\d+\.\d+\.\d+$",
        description="Optional firmware version (x.y.z). If omitted, the latest installable version is used.",
    )
