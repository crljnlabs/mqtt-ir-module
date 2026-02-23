from typing import Optional

from pydantic import BaseModel, Field


class AgentRuntimeConfigUpdate(BaseModel):
    ir_rx_pin: Optional[int] = Field(default=None, ge=0, le=39, description="ESP32 IR receiver GPIO")
    ir_tx_pin: Optional[int] = Field(default=None, ge=0, le=39, description="ESP32 IR transmitter GPIO")
