from typing import Literal, Optional
from pydantic import BaseModel, Field


Theme = Literal["system", "light", "dark"]


class SettingsUpdate(BaseModel):
    theme: Optional[Theme] = Field(default=None, description="UI theme")
    language: Optional[str] = Field(default=None, min_length=2, max_length=16, description="UI language code (e.g. en, de, pt-PT)")
    hub_is_agent: Optional[bool] = Field(default=None, description="Whether the Hub should register a local agent")
    homeassistant_enabled: Optional[bool] = Field(default=None, description="Enable Home Assistant discovery runtime")
    mqtt_host: Optional[str] = Field(default=None, max_length=255, description="MQTT broker host")
    mqtt_port: Optional[int] = Field(default=None, ge=1, le=65535, description="MQTT broker port")
    mqtt_username: Optional[str] = Field(default=None, max_length=255, description="MQTT broker username")
    mqtt_password: Optional[str] = Field(default=None, max_length=4096, description="MQTT broker password (stored encrypted at rest)")
    mqtt_instance: Optional[str] = Field(
        default=None,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]*$",
        description="Optional hub instance segment used in base topic ir/hubs/<instance_or_main>",
    )
    press_takes_default: Optional[int] = Field(default=None, ge=1, le=50, description="Default number of press takes")
    capture_timeout_ms_default: Optional[int] = Field(default=None, ge=100, le=60000, description="Default capture timeout in ms")
    hold_idle_timeout_ms: Optional[int] = Field(default=None, ge=50, le=2000, description="Hold idle timeout in ms")
    aggregate_round_to_us: Optional[int] = Field(default=None, ge=1, le=1000, description="Aggregation rounding step in microseconds")
    aggregate_min_match_ratio: Optional[float] = Field(default=None, ge=0.1, le=1.0, description="Aggregation minimum match ratio")
