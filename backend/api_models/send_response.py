from typing import Optional

from pydantic import BaseModel, Field


class SendResponse(BaseModel):
    mode: str = Field(..., description="Send mode (press/hold)")
    hold_ms: Optional[int] = Field(default=None, description="Requested hold duration in milliseconds")
    carrier_hz: Optional[int] = Field(default=None, description="Carrier frequency used for transmission")
    duty_cycle: Optional[int] = Field(default=None, description="Duty cycle used for transmission")
    gap_us: Optional[int] = Field(default=None, description="Inter-frame gap used for transmission")
    repeats: Optional[int] = Field(default=None, description="Number of repeat frames sent")
    stdout: Optional[str] = Field(default=None, description="ir-ctl stdout output")
    stderr: Optional[str] = Field(default=None, description="ir-ctl stderr output")
