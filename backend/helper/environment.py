import os
from typing import Optional


class Environment:
    def __init__(self) -> None:
        self.api_key = os.getenv("API_KEY", "").strip()
        self.ir_rx_device = os.getenv("IR_RX_DEVICE", "/dev/lirc0").strip()
        self.ir_tx_device = os.getenv("IR_TX_DEVICE", "/dev/lirc1").strip()
        self.data_folder = os.getenv("DATA_DIR", "/data").strip()
        self.firmware_dir = os.getenv("FIRMWARE_DIR", os.path.join(self.data_folder, "firmware")).strip()
        self.mqtt_host = os.getenv("MQTT_HOST", "").strip()
        self.mqtt_port = self._read_optional_int("MQTT_PORT", min_value=1, max_value=65535)
        self.mqtt_username = os.getenv("MQTT_USERNAME", "").strip()
        self.mqtt_password = os.getenv("MQTT_PASSWORD", "").strip()

        # Public base url for reverse-proxy sub-path hosting (e.g. /mqtt-ir-module/)
        self.public_base_url = self._normalize_base_url(os.getenv("PUBLIC_BASE_URL", "/"))

        # Optional: if set, the backend will inject it into the frontend runtime config.
        # WARNING: This exposes the key to any browser that can access the UI.
        self.public_api_key = os.getenv("PUBLIC_API_KEY", "").strip()

        self.debug = self._read_bool("DEBUG", default=False)

        # Master key for encrypting sensitive settings values at rest (e.g., MQTT password).
        self.settings_master_key = os.getenv("SETTINGS_MASTER_KEY", "").strip()

        # Optional: force-enable/disable the local agent when running the hub.
        self.local_agent_enabled = self._read_optional_bool("LOCAL_AGENT_ENABLED")
        self.agent_pairing_reset = self._read_bool("AGENT_PAIRING_RESET", default=False)

        # ir-ctl receiver options
        self.ir_wideband = self._read_bool("IR_WIDEBAND", default=False)

        # Learning defaults live in app settings (see database.settings).

    def _read_bool(self, name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        value = raw.strip().lower()
        if value in ("1", "true", "yes", "y", "on"):
            return True
        if value in ("0", "false", "no", "n", "off"):
            return False
        return default

    def _read_optional_bool(self, name: str) -> Optional[bool]:
        raw = os.getenv(name)
        if raw is None:
            return None
        value = raw.strip().lower()
        if value in ("1", "true", "yes", "y", "on"):
            return True
        if value in ("0", "false", "no", "n", "off"):
            return False
        return None

    def _read_optional_int(self, name: str, min_value: Optional[int] = None, max_value: Optional[int] = None) -> Optional[int]:
        raw = os.getenv(name)
        if raw is None:
            return None
        try:
            value = int(raw.strip())
        except Exception:
            return None
        if min_value is not None and value < min_value:
            return None
        if max_value is not None and value > max_value:
            return None
        return value

    def _read_int(self, name: str, default: int, min_value: Optional[int] = None, max_value: Optional[int] = None) -> int:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            value = int(raw.strip())
        except Exception:
            return default
        if min_value is not None and value < min_value:
            return default
        if max_value is not None and value > max_value:
            return default
        return value

    def _read_float(
        self,
        name: str,
        default: float,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> float:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            value = float(raw.strip())
        except Exception:
            return default
        if min_value is not None and value < min_value:
            return default
        if max_value is not None and value > max_value:
            return default
        return value

    def _normalize_base_url(self, raw: Optional[str]) -> str:
        value = (raw or "/").strip()
        if not value:
            return "/"
        if not value.startswith("/"):
            value = "/" + value
        if not value.endswith("/"):
            value += "/"
        # Collapse accidental double slash root
        if value == "//":
            return "/"
        return value
