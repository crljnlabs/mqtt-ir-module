import json
import logging
import threading
from typing import Any, Dict, Optional

from jmqtt import MQTTBuilderV3, MQTTConnectionV3, QualityOfService as QoS
from jmqtt import client_identity as mqtt_client_identity

from .mqtt_connection_model import MQTTConnectionModel, ConnectionRole


class MqttHandler:
    def __init__(self, role: ConnectionRole) -> None:
        self._role = role
        self._lock = threading.Lock()
        self._logger = logging.getLogger("mqtt_handler")
        self._connection: Optional[MQTTConnectionV3] = None
        self._active_model: Optional[MQTTConnectionModel] = None
        self._active_client_id: Optional[str] = None
        self._last_error: Optional[str] = None

    def start(self, model: MQTTConnectionModel) -> None:
        if not model.is_mqtt_configured:
            self.stop()
            with self._lock:
                self._active_model = model
                self._active_client_id = None
                self._last_error = None
            return

        with self._lock:
            current_model = self._active_model
            current_connection = self._connection
            already_connected = self._is_connected(current_connection)
            unchanged = current_model == model and already_connected
        if unchanged:
            return

        self.stop()
        try:
            self._logger.info(
                f"Connecting MQTT role={self._role} host={model.host} port={model.port} "
                f"app_name={model.app_name} node_id={model.node_id} base_topic={model.base_topic}"
            )
            connection = self._connect(model)
            with self._lock:
                self._connection = connection
                self._active_model = model
                self._active_client_id = str(connection.client_id or "")
                self._last_error = None
            self._logger.info(f"MQTT connected role={self._role} client_id={connection.client_id}")
        except Exception as exc:
            with self._lock:
                self._active_model = model
                self._active_client_id = None
                self._last_error = str(exc)
            self._logger.warning(f"MQTT start failed: {exc}")
            raise

    def stop(self) -> None:
        with self._lock:
            connection = self._connection
            self._connection = None
            self._active_client_id = None
        if connection is None:
            return
        try:
            connection.close()
        except Exception as exc:
            self._logger.warning(f"Failed to close MQTT connection cleanly: {exc}")

    def reload(self, model: MQTTConnectionModel) -> None:
        self.start(model)

    def mark_error(self, message: str) -> None:
        with self._lock:
            self._last_error = str(message)
            if self._active_model is None:
                self._active_model = self._fallback_model()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            model = self._active_model
            connection = self._connection
            active_client_id = self._active_client_id
            last_error = self._last_error

        if model is None:
            model = self._fallback_model()

        base_topic = model.base_topic
        node_id = model.node_id
        app_name = model.app_name
        configured = model.is_mqtt_configured

        client_id = ""
        if connection is not None:
            client_id = str(connection.client_id or "")
        if not client_id:
            client_id = str(active_client_id or "")

        return {
            "configured": configured,
            "connected": self._is_connected(connection),
            "role": self._role,
            "node_id": node_id,
            "base_topic": base_topic,
            "app_name": app_name,
            "client_id": client_id,
            "last_error": last_error,
        }

    def connection(self) -> Optional[MQTTConnectionV3]:
        with self._lock:
            return self._connection

    def client_id(self) -> str:
        with self._lock:
            connection = self._connection
            active_client_id = self._active_client_id
        if connection is not None and connection.client_id:
            return str(connection.client_id)
        return str(active_client_id or "")

    def topic(self, relative_topic: str) -> str:
        relative = self._normalize_topic_part(relative_topic)
        with self._lock:
            model = self._active_model
        if model is None:
            model = self._fallback_model()
        base_topic = model.base_topic
        if not relative:
            return base_topic
        return f"{base_topic}/{relative}"

    def publish(
        self,
        relative_topic: str,
        payload: Any,
        qos: QoS = QoS.AtLeastOnce,
        retain: bool = False,
        wait_for_publish: bool = False,
    ):
        topic = self.topic(relative_topic)
        with self._lock:
            connection = self._connection
        if connection is None or not self._is_connected(connection):
            raise RuntimeError("mqtt_not_connected")
        return connection.publish(topic, payload, qos=qos, retain=retain, wait_for_publish=wait_for_publish)

    def publish_json(
        self,
        relative_topic: str,
        payload: Dict[str, Any],
        qos: QoS = QoS.AtLeastOnce,
        retain: bool = False,
        wait_for_publish: bool = False,
    ):
        text = json.dumps(payload, separators=(",", ":"))
        return self.publish(
            relative_topic=relative_topic,
            payload=text,
            qos=qos,
            retain=retain,
            wait_for_publish=wait_for_publish,
        )

    def _connect(self, model: MQTTConnectionModel) -> MQTTConnectionV3:
        builder = MQTTBuilderV3(host=model.host, app_name=model.app_name)
        if model.role == "hub" and model.node_id:
            builder.instance_id(model.node_id.replace("_", "-"))
        builder.port(model.port)
        builder.keep_alive(60)
        builder.auto_reconnect(min_delay=1, max_delay=30)
        if model.username:
            builder.login(model.username, model.password)
        builder.availability(topic=model.availability_topic)
        connection = builder.build()
        connection.connect()
        return connection

    def _is_connected(self, connection: Optional[MQTTConnectionV3]) -> bool:
        return connection is not None and bool(connection.is_connected)

    def _normalize_topic_part(self, value: str) -> str:
        return str(value or "").strip().strip("/")

    def _default_node_id(self) -> str:
        app_name = MQTTConnectionModel.technical_name_for_role(self._role)
        try:
            return mqtt_client_identity.client_id.build_auto_client_id(app_name)
        except Exception:
            return f"{app_name}-node"

    def _fallback_model(self) -> MQTTConnectionModel:
        return MQTTConnectionModel(
            role=self._role,
            host="",
            port=1883,
            username="",
            password="",
            node_id=self._default_node_id(),
            readable_name=MQTTConnectionModel.readable_name_for_role(self._role),
        )
