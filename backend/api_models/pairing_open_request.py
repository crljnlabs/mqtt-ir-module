from typing import Optional

from pydantic import BaseModel, Field


class PairingOpenRequest(BaseModel):
    duration_seconds: Optional[int] = Field(
        default=None,
        ge=10,
        le=3600,
        description="How long the hub keeps pairing open",
    )
