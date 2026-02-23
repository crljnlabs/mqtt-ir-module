import sqlite3
import time
from typing import Any, Dict, Optional

from database.database_base import DatabaseBase
from helper.settings_cipher import SettingsCipher


class Settings(DatabaseBase):
    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )

    def get(self, key: str, default: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> Optional[str]:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return default

        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT value FROM app_settings WHERE key = ?", (normalized_key,)).fetchone()
            if not row:
                return default
            return str(row["value"])
        finally:
            if close:
                c.close()

    def set(self, key: str, value: str, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ValueError("key must not be empty")

        c, close = self._use_conn(conn)
        try:
            now = time.time()
            c.execute(
                "INSERT OR REPLACE INTO app_settings(key, value, updated_at) VALUES(?, ?, ?)",
                (normalized_key, str(value), now),
            )
            c.commit()
            row = c.execute(
                "SELECT key, value, updated_at FROM app_settings WHERE key = ?",
                (normalized_key,),
            ).fetchone()
            if not row:
                raise ValueError("Failed to set setting")
            return dict(row)
        finally:
            if close:
                c.close()

    def get_learning_defaults(self) -> Dict[str, Any]:
        return {
            "press_takes_default": 5,
            "capture_timeout_ms_default": 3000,
            "hold_idle_timeout_ms": 300,
            "aggregate_round_to_us": 10,
            "aggregate_min_match_ratio": 0.6,
        }

    def get_learning_settings(self, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        
        learning_defaults = self.get_learning_defaults()
        return {
            "press_takes_default": self._read_int_setting(
                "press_takes_default",
                default=learning_defaults["press_takes_default"],
                min_value=1,
                max_value=50,
                conn=conn,
            ),
            "capture_timeout_ms_default": self._read_int_setting(
                "capture_timeout_ms_default",
                default=learning_defaults["capture_timeout_ms_default"],
                min_value=100,
                max_value=60000,
                conn=conn,
            ),
            "hold_idle_timeout_ms": self._read_int_setting(
                "hold_idle_timeout_ms",
                default=learning_defaults["hold_idle_timeout_ms"],
                min_value=50,
                max_value=2000,
                conn=conn,
            ),
            "aggregate_round_to_us": self._read_int_setting(
                "aggregate_round_to_us",
                default=learning_defaults["aggregate_round_to_us"],
                min_value=1,
                max_value=1000,
                conn=conn,
            ),
            "aggregate_min_match_ratio": self._read_float_setting(
                "aggregate_min_match_ratio",
                default=learning_defaults["aggregate_min_match_ratio"],
                min_value=0.1,
                max_value=1.0,
                conn=conn,
            ),
        }

    def get_mqtt_settings(self, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        mqtt_instance = self._read_text_setting("mqtt_instance", default="", conn=conn)
        return {
            "mqtt_host": self._read_text_setting("mqtt_host", default="", conn=conn),
            "mqtt_port": self._read_int_setting(
                "mqtt_port",
                default=1883,
                min_value=1,
                max_value=65535,
                conn=conn,
            ),
            "mqtt_username": self._read_text_setting("mqtt_username", default="", conn=conn),
            "mqtt_instance": mqtt_instance,
            "mqtt_base_topic": self._build_mqtt_base_topic(mqtt_instance),
            "mqtt_password_set": self._has_mqtt_password(conn=conn),
        }

    def get_ui_settings(self, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        settings = {
            "theme": self._read_text_setting("theme", default="system", conn=conn),
            "language": self._read_text_setting("language", default="en", conn=conn),
            "hub_is_agent": self._read_bool_setting("hub_is_agent", default=True, conn=conn),
            "homeassistant_enabled": self._read_bool_setting("homeassistant_enabled", default=False, conn=conn),
        }
        settings.update(self.get_mqtt_settings(conn=conn))
        settings.update(self.get_learning_settings(conn=conn))
        return settings

    def get_runtime_settings(self, settings_cipher: SettingsCipher, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        settings = self.get_ui_settings(conn=conn)
        password = ""

        if settings["mqtt_password_set"]:
            if not settings_cipher.is_configured:
                raise ValueError("settings_master_key_missing")

            ciphertext = self.get("mqtt_password_ciphertext", default="", conn=conn) or ""
            nonce = self.get("mqtt_password_nonce", default="", conn=conn) or ""
            if not ciphertext or not nonce:
                raise ValueError("mqtt_password_decrypt_failed")
            try:
                password = settings_cipher.decrypt(ciphertext, nonce)
            except Exception as exc:
                raise ValueError("mqtt_password_decrypt_failed") from exc

        return {
            **settings,
            "mqtt_password": password,
        }

    def update_ui_settings(
        self,
        theme: Optional[str] = None,
        language: Optional[str] = None,
        press_takes_default: Optional[int] = None,
        capture_timeout_ms_default: Optional[int] = None,
        hold_idle_timeout_ms: Optional[int] = None,
        aggregate_round_to_us: Optional[int] = None,
        aggregate_min_match_ratio: Optional[float] = None,
        hub_is_agent: Optional[bool] = None,
        homeassistant_enabled: Optional[bool] = None,
        mqtt_host: Optional[str] = None,
        mqtt_port: Optional[int] = None,
        mqtt_username: Optional[str] = None,
        mqtt_password: Optional[str] = None,
        mqtt_instance: Optional[str] = None,
        settings_cipher: Optional[SettingsCipher] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        c, close = self._use_conn(conn)
        try:
            if theme is not None:
                self.set("theme", str(theme), conn=c)
            if language is not None:
                self.set("language", str(language), conn=c)
            if hub_is_agent is not None:
                self.set("hub_is_agent", str(bool(hub_is_agent)).lower(), conn=c)
            if homeassistant_enabled is not None:
                self.set("homeassistant_enabled", str(bool(homeassistant_enabled)).lower(), conn=c)

            if press_takes_default is not None:
                self.set("press_takes_default", str(press_takes_default), conn=c)
            if capture_timeout_ms_default is not None:
                self.set("capture_timeout_ms_default", str(capture_timeout_ms_default), conn=c)
            if hold_idle_timeout_ms is not None:
                self.set("hold_idle_timeout_ms", str(hold_idle_timeout_ms), conn=c)
            if aggregate_round_to_us is not None:
                self.set("aggregate_round_to_us", str(aggregate_round_to_us), conn=c)
            if aggregate_min_match_ratio is not None:
                self.set("aggregate_min_match_ratio", str(aggregate_min_match_ratio), conn=c)

            if mqtt_host is not None:
                self.set("mqtt_host", str(mqtt_host).strip(), conn=c)
            if mqtt_port is not None:
                self.set("mqtt_port", str(mqtt_port), conn=c)
            if mqtt_username is not None:
                self.set("mqtt_username", str(mqtt_username).strip(), conn=c)
            if mqtt_instance is not None:
                self.set("mqtt_instance", str(mqtt_instance).strip(), conn=c)
            if mqtt_password is not None:
                self._update_mqtt_password(
                    mqtt_password=str(mqtt_password),
                    settings_cipher=settings_cipher,
                    conn=c,
                )

            return self.get_ui_settings(conn=c)
        finally:
            if close:
                c.close()

    def _read_int_setting(
        self,
        key: str,
        default: int,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        raw = self.get(key, default=None, conn=conn)
        if raw is None:
            return default
        try:
            value = int(str(raw).strip())
        except Exception:
            return default
        if min_value is not None and value < min_value:
            return default
        if max_value is not None and value > max_value:
            return default
        return value

    def _read_bool_setting(
        self,
        key: str,
        default: bool,
        conn: Optional[sqlite3.Connection] = None,
    ) -> bool:
        raw = self.get(key, default=None, conn=conn)
        if raw is None:
            return default
        value = str(raw).strip().lower()
        if value in ("1", "true", "yes", "y", "on"):
            return True
        if value in ("0", "false", "no", "n", "off"):
            return False
        return default

    def _read_text_setting(
        self,
        key: str,
        default: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> str:
        raw = self.get(key, default=None, conn=conn)
        if raw is None:
            return default
        value = str(raw).strip()
        if not value:
            return default
        return value

    def _read_float_setting(
        self,
        key: str,
        default: float,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> float:
        raw = self.get(key, default=None, conn=conn)
        if raw is None:
            return default
        try:
            value = float(str(raw).strip())
        except Exception:
            return default
        if min_value is not None and value < min_value:
            return default
        if max_value is not None and value > max_value:
            return default
        return value

    def _has_mqtt_password(self, conn: Optional[sqlite3.Connection] = None) -> bool:
        ciphertext = self.get("mqtt_password_ciphertext", default="", conn=conn) or ""
        nonce = self.get("mqtt_password_nonce", default="", conn=conn) or ""
        return bool(ciphertext and nonce)

    def _update_mqtt_password(
        self,
        mqtt_password: str,
        settings_cipher: Optional[SettingsCipher],
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        if mqtt_password == "":
            self.set("mqtt_password_ciphertext", "", conn=conn)
            self.set("mqtt_password_nonce", "", conn=conn)
            return

        if settings_cipher is None or not settings_cipher.is_configured:
            raise ValueError("settings_master_key_missing")

        ciphertext, nonce = settings_cipher.encrypt(mqtt_password)
        self.set("mqtt_password_ciphertext", ciphertext, conn=conn)
        self.set("mqtt_password_nonce", nonce, conn=conn)

    def _build_mqtt_base_topic(self, instance: str) -> str:
        normalized_instance = str(instance or "").strip().strip("/")
        hub_id = normalized_instance or "main"
        return f"ir/hubs/{hub_id}"
