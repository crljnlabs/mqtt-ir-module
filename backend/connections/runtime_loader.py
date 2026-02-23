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


class RuntimeLoader:
    def __init__(
        self,
        settings_store: Optional[Settings],
        settings_cipher: Optional[SettingsCipher],
        role: ConnectionRole,
        environment: Environment,
    ) -> None:
        self._settings_store = settings_store
        self._settings_cipher = settings_cipher
        self._role = role
        self._environment = environment
        self._mqtt_handler = MqttHandler(role=role)
        self._homeassistant_handler = HomeAssistantHandler()

    @property
    def technical_name(self) -> str:
        return MQTTConnectionModel.technical_name_for_role(self._role)

    @property
    def readable_name(self) -> str:
        return MQTTConnectionModel.readable_name_for_role(self._role)

    def start(self) -> None:
        self.reload()

    def stop(self) -> None:
        self._homeassistant_handler.stop()
        self._mqtt_handler.stop()

    def reload(self) -> None:
        try:
            runtime_settings = self._load_runtime_settings()
            mqtt_model = self._build_mqtt_model(runtime_settings)
            homeassistant_model = self._build_homeassistant_model(runtime_settings)
            self._mqtt_handler.reload(mqtt_model)
            self._homeassistant_handler.configure(homeassistant_model, self._mqtt_handler.connection())
            self._homeassistant_handler.start()
        except Exception as exc:
            self._mqtt_handler.stop()
            self._homeassistant_handler.stop()
            self._mqtt_handler.mark_error(str(exc))

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
        return HomeAssistantConnectionModel(
            role=self._role,
            enabled=enabled,
            origin_name=self.readable_name,
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
