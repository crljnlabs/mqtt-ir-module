import logging
import threading
from typing import TYPE_CHECKING, Any, Dict, Optional

from jhomeassistant import HomeAssistantConnection
from jmqtt import MQTTConnectionV3

from .homeassistant_connection_model import HomeAssistantConnectionModel

if TYPE_CHECKING:
    from .homeassistant_device_manager import HomeAssistantDeviceManager


class HomeAssistantHandler:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._logger = logging.getLogger("homeassistant_handler")
        self._connection_model: Optional[HomeAssistantConnectionModel] = None
        self._ha_connection: Optional[HomeAssistantConnection] = None
        self._ha_thread: Optional[threading.Thread] = None
        self._device_manager: Optional["HomeAssistantDeviceManager"] = None

    def configure(
        self,
        model: HomeAssistantConnectionModel,
        mqtt_connection: Optional[MQTTConnectionV3],
        device_manager: Optional["HomeAssistantDeviceManager"] = None,
    ) -> None:
        # Always tear down the previous runtime first so a stale thread from a
        # past enable/disable cycle can never block start() (its is_alive() check
        # would otherwise short-circuit the next start and leave HA without devices).
        self._shutdown_runtime()

        with self._lock:
            self._connection_model = model
            self._device_manager = device_manager
            if not model.is_homeassistant_configured or mqtt_connection is None:
                self._ha_connection = None
                return
            self._ha_connection = HomeAssistantConnection(mqtt_connection)

        # configure() runs in the setup phase, before the TCP connect — registering the
        # device manager's on-connect hook here guarantees it fires on the first connect
        # and on every reconnect (initial entity states + log bridge resubscription).
        if device_manager is not None:
            device_manager.register_mqtt_connect_hook(mqtt_connection)

    def start(self) -> None:
        with self._lock:
            model = self._connection_model
            ha_connection = self._ha_connection
            existing = self._ha_thread
            if model is None or not model.is_homeassistant_configured:
                return
            if ha_connection is None:
                return
            if existing is not None and existing.is_alive():
                return
            thread = threading.Thread(
                target=self._thread_main,
                args=(ha_connection,),
                daemon=True,
                name="homeassistant_runtime",
            )
            self._ha_thread = thread
        thread.start()

    def stop(self) -> None:
        self._shutdown_runtime()
        with self._lock:
            self._connection_model = None
            self._device_manager = None

    def _shutdown_runtime(self, timeout: float = 2.0) -> None:
        """Stop the HA runtime thread cleanly and drop the connection reference.

        Uses HomeAssistantConnection.stop() to signal the runtime loop to exit, then
        joins the thread. Safe to call when nothing is running (idempotent).
        """
        with self._lock:
            ha_connection = self._ha_connection
            thread = self._ha_thread
            self._ha_connection = None
            self._ha_thread = None

        if ha_connection is not None:
            try:
                ha_connection.stop(timeout=timeout)
            except Exception as exc:
                self._logger.warning(f"HA runtime stop failed: {exc}")

        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
            if thread.is_alive():
                self._logger.warning("HA runtime thread did not exit within timeout")

    def cleanup_discovery(self) -> None:
        """Clear all retained HA discovery topics via the active connection.
        Called when HA gets disabled, before the MQTT connection itself is stopped.
        Idempotent — no-op if no active connection or device manager.
        """
        with self._lock:
            device_manager = self._device_manager
        if device_manager is None:
            return
        try:
            device_manager.teardown()
        except Exception as exc:
            self._logger.warning(f"HA cleanup_discovery failed: {exc}")

    def status(self) -> Dict[str, Any]:
        with self._lock:
            model = self._connection_model
            thread = self._ha_thread
        enabled = bool(model and model.is_homeassistant_configured)
        thread_running = thread is not None and thread.is_alive()
        return {
            "homeassistant_enabled": enabled,
            "homeassistant_thread_running": thread_running,
        }

    def _thread_main(self, ha_connection: HomeAssistantConnection) -> None:
        with self._lock:
            model = self._connection_model
            device_manager = self._device_manager
        if model is None:
            return
        if device_manager is not None:
            try:
                device_manager.setup(ha_connection, origin_name=model.origin_name)
            except Exception as exc:
                self._logger.warning(f"Device manager setup failed: {exc}")
        try:
            ha_connection.run(
                schedule_resolution=model.schedule_resolution,
                publish_timeout=model.publish_timeout,
            )
        except Exception as exc:
            self._logger.warning(f"Home Assistant runtime stopped: {exc}")
        finally:
            with self._lock:
                if threading.current_thread() is self._ha_thread:
                    self._ha_thread = None
