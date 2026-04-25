import logging
import threading
import time
from typing import Any, Dict, Literal, Optional

from jmqtt import client_identity as mqtt_client_identity

from database.schemas.settings import Settings
from helper.environment import Environment
from helper.settings_cipher import SettingsCipher

from .homeassistant_connection_model import HomeAssistantConnectionModel
from .homeassistant_handler import HomeAssistantHandler
from .mqtt_connection_model import MQTTConnectionModel
from .mqtt_handler import MqttHandler


ConnectionRole = Literal["hub", "agent"]

# Exponential backoff delays in seconds: 10s → 1min → 10min → 1h
_RETRY_DELAYS = [10, 60, 600, 3600]


class RuntimeLoader:
    def __init__(
        self,
        settings_store: Optional[Settings],
        settings_cipher: Optional[SettingsCipher],
        role: ConnectionRole,
        environment: Environment,
        database=None,
        ha_device_manager=None,
    ) -> None:
        self._settings_store = settings_store
        self._settings_cipher = settings_cipher
        self._role = role
        self._environment = environment
        self._database = database
        self._ha_device_manager = ha_device_manager
        self._mqtt_handler = MqttHandler(role=role)
        self._homeassistant_handler = HomeAssistantHandler()
        self._logger = logging.getLogger("connections.runtime_loader")
        self._retry_stop_event = threading.Event()
        self._retry_thread: Optional[threading.Thread] = None

    @property
    def technical_name(self) -> str:
        return MQTTConnectionModel.technical_name_for_role(self._role)

    @property
    def readable_name(self) -> str:
        return MQTTConnectionModel.readable_name_for_role(self._role)

    def start(self) -> None:
        self.setup()
        self.connect()

    def stop(self) -> None:
        self._cancel_retry()
        self._homeassistant_handler.stop()
        self._mqtt_handler.stop()

    def setup(self) -> None:
        """Build the MQTT connection object and configure HA without connecting.

        Call connect() separately after all subscribers have registered their
        add_on_connect callbacks so the first _on_connect fires for everyone.
        """
        self._cancel_retry()
        try:
            runtime_settings = self._load_runtime_settings()
            mqtt_model = self._build_mqtt_model(runtime_settings)
            homeassistant_model = self._build_homeassistant_model(runtime_settings)
            self._mqtt_handler.setup(mqtt_model)
            self._homeassistant_handler.configure(homeassistant_model, self._mqtt_handler.connection(), device_manager=self._ha_device_manager)
        except Exception as exc:
            self._mqtt_handler.stop()
            self._homeassistant_handler.stop()
            self._mqtt_handler.mark_error(str(exc))
            self._start_retry_loop()

    def connect(self) -> None:
        """Initiate TCP connect and start HA after all subscribers are ready."""
        try:
            self._mqtt_handler.connect()
            self._homeassistant_handler.start()
        except Exception as exc:
            self._mqtt_handler.stop()
            self._homeassistant_handler.stop()
            self._mqtt_handler.mark_error(str(exc))
            self._start_retry_loop()

    def cleanup_homeassistant_discovery(self) -> None:
        """Clear retained HA discovery topics. Caller is responsible for invoking this
        BEFORE stopping the MQTT connection (otherwise no broker to publish to)."""
        self._homeassistant_handler.cleanup_discovery()

    def reload(self) -> None:
        # Cancel any running retry before attempting a fresh connect.
        self._cancel_retry()
        try:
            runtime_settings = self._load_runtime_settings()
            mqtt_model = self._build_mqtt_model(runtime_settings)
            homeassistant_model = self._build_homeassistant_model(runtime_settings)
            self._mqtt_handler.reload(mqtt_model)
            self._homeassistant_handler.configure(homeassistant_model, self._mqtt_handler.connection(), device_manager=self._ha_device_manager)
            self._homeassistant_handler.start()
        except Exception as exc:
            self._mqtt_handler.stop()
            self._homeassistant_handler.stop()
            self._mqtt_handler.mark_error(str(exc))
            self._start_retry_loop()

    def _load_runtime_settings(self) -> Dict[str, Any]:
        if self._settings_store is None or self._settings_cipher is None:
            return {}
        return self._settings_store.get_runtime_settings(settings_cipher=self._settings_cipher)

    def status(self) -> Dict[str, Any]:
        mqtt_status = self._mqtt_handler.status()
        mqtt_status.update(self._homeassistant_handler.status())
        return mqtt_status

    def mqtt_connection(self):
        return self._mqtt_handler.connection()

    def mqtt_client_id(self) -> str:
        return self._mqtt_handler.client_id()

    def topic(self, relative_topic: str) -> str:
        return self._mqtt_handler.topic(relative_topic)

    def publish(
        self,
        relative_topic: str,
        payload: Any,
        qos=None,
        retain: bool = False,
        wait_for_publish: bool = False,
    ):
        if qos is None:
            return self._mqtt_handler.publish(
                relative_topic=relative_topic,
                payload=payload,
                retain=retain,
                wait_for_publish=wait_for_publish,
            )
        return self._mqtt_handler.publish(
            relative_topic=relative_topic,
            payload=payload,
            qos=qos,
            retain=retain,
            wait_for_publish=wait_for_publish,
        )

    def publish_json(
        self,
        relative_topic: str,
        payload: Dict[str, Any],
        qos=None,
        retain: bool = False,
        wait_for_publish: bool = False,
    ):
        if qos is None:
            return self._mqtt_handler.publish_json(
                relative_topic=relative_topic,
                payload=payload,
                retain=retain,
                wait_for_publish=wait_for_publish,
            )
        return self._mqtt_handler.publish_json(
            relative_topic=relative_topic,
            payload=payload,
            qos=qos,
            retain=retain,
            wait_for_publish=wait_for_publish,
        )

    def _cancel_retry(self) -> None:
        self._retry_stop_event.set()
        thread = self._retry_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1)
        self._retry_stop_event.clear()
        self._retry_thread = None

    def _start_retry_loop(self) -> None:
        thread = threading.Thread(
            target=self._retry_loop,
            daemon=True,
            name="mqtt-retry",
        )
        self._retry_thread = thread
        thread.start()

    def _retry_loop(self) -> None:
        total = len(_RETRY_DELAYS)
        for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
            next_delay_msg = f" Next retry in {delay}s." if attempt < total else ""
            self._log_hub_event(
                "warn", "mqtt",
                f"MQTT connection failed, retrying in {delay}s (attempt {attempt}/{total}).",
            )
            self._logger.warning(f"MQTT retry {attempt}/{total} scheduled in {delay}s")

            if self._retry_stop_event.wait(delay):
                # Cancelled by stop() or a manual reload()
                return

            self._log_hub_event(
                "info", "mqtt",
                f"MQTT reconnect attempt {attempt}/{total}.",
            )
            self._logger.info(f"MQTT reconnect attempt {attempt}/{total}")
            try:
                runtime_settings = self._load_runtime_settings()
                mqtt_model = self._build_mqtt_model(runtime_settings)
                homeassistant_model = self._build_homeassistant_model(runtime_settings)
                self._mqtt_handler.start(mqtt_model)
                self._homeassistant_handler.configure(homeassistant_model, self._mqtt_handler.connection(), device_manager=self._ha_device_manager)
                self._homeassistant_handler.start()
                self._log_hub_event(
                    "info", "mqtt",
                    f"MQTT reconnected successfully after {attempt} attempt(s).",
                )
                self._logger.info(f"MQTT reconnected on retry {attempt}/{total}")
                return
            except Exception as exc:
                self._mqtt_handler.mark_error(str(exc))
                self._log_hub_event(
                    "warn", "mqtt",
                    f"MQTT retry {attempt}/{total} failed: {exc}",
                )
                self._logger.warning(f"MQTT retry {attempt}/{total} failed: {exc}")

        self._log_hub_event(
            "error", "mqtt",
            "MQTT connection failed after all retry attempts — use the manual retry button.",
        )
        self._logger.error("MQTT connection failed after all retry attempts")

    def _log_hub_event(self, level: str, category: str, message: str, meta: Optional[Dict[str, Any]] = None) -> None:
        if self._database is None:
            return
        try:
            event: Dict[str, Any] = {
                "ts": time.time(),
                "level": level,
                "category": category,
                "message": message,
            }
            if meta:
                event["meta"] = meta
            self._database.logs.insert(source_type="hub", source_id="hub", event=event)
        except Exception as exc:
            self._logger.warning(f"Failed to write hub log event: {exc}")

    def _build_mqtt_model(self, runtime: Dict[str, Any]) -> MQTTConnectionModel:
        host = str(runtime.get("mqtt_host") or "").strip()
        port = int(runtime.get("mqtt_port") or 1883)
        username = str(runtime.get("mqtt_username") or "").strip()
        password = str(runtime.get("mqtt_password") or "")
        mqtt_instance = self._normalize_topic_part(str(runtime.get("mqtt_instance") or ""))

        if self._role == "agent":
            if self._environment.mqtt_host:
                host = self._environment.mqtt_host
            if self._environment.mqtt_port is not None:
                port = self._environment.mqtt_port
            if self._environment.mqtt_username:
                username = self._environment.mqtt_username
            if self._environment.mqtt_password:
                password = self._environment.mqtt_password

        node_id = self._resolve_node_id(mqtt_instance)
        return MQTTConnectionModel(
            role=self._role,
            host=host,
            port=port,
            username=username,
            password=password,
            node_id=node_id,
            readable_name=MQTTConnectionModel.readable_name_for_role(self._role),
        )

    def _build_homeassistant_model(self, runtime: Dict[str, Any]) -> HomeAssistantConnectionModel:
        enabled = bool(runtime.get("homeassistant_enabled", False))
        if self._role != "hub":
            enabled = False
        hub_public_url = str(runtime.get("hub_public_url") or "").strip()
        return HomeAssistantConnectionModel(
            role=self._role,
            enabled=enabled,
            origin_name=self.readable_name,
            hub_public_url=hub_public_url,
            schedule_resolution=1.0,
            publish_timeout=5.0,
        )

    def _normalize_topic_part(self, value: str) -> str:
        return str(value or "").strip().strip("/")

    def _resolve_node_id(self, mqtt_instance: str) -> str:
        if self._role == "hub":
            return mqtt_instance or "main"

        app_name = MQTTConnectionModel.technical_name_for_role(self._role)
        instance_id = None
        try:
            return mqtt_client_identity.client_id.build_auto_client_id(app_name, instance_id)
        except Exception:
            return f"{app_name}-node"
