import logging
import threading
import time
from typing import Callable, List, Optional


class HomeAssistantSyncWorker:
    """Single writer thread for all Home Assistant tree updates.

    Every change notification — from API endpoints, MQTT callbacks, or HA commands —
    is queued here instead of mutating the HA tree on the caller's thread. This keeps
    the MQTT network thread free of blocking publish waits and coalesces bursts
    (e.g. a marketplace install creating dozens of buttons) into one reconcile pass.
    A periodic reconcile self-heals any missed notification.
    """

    DEBOUNCE_SECONDS = 1.0
    # A continuous stream of notifications must not starve the reconcile forever.
    MAX_COALESCE_SECONDS = 5.0
    RECONCILE_INTERVAL_SECONDS = 300.0

    def __init__(self, device_manager) -> None:
        self._device_manager = device_manager
        self._logger = logging.getLogger("homeassistant_sync_worker")
        self._cond = threading.Condition()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._change_pending = False
        self._first_change_ts = 0.0
        self._last_change_ts = 0.0
        self._connected_pending = False
        self._tasks: List[Callable[[], None]] = []
        self._next_periodic_ts = 0.0

    def start(self) -> None:
        with self._cond:
            if self._running:
                return
            self._running = True
            self._next_periodic_ts = time.time() + self.RECONCILE_INTERVAL_SECONDS
            thread = threading.Thread(target=self._loop, daemon=True, name="ha-sync-worker")
            self._thread = thread
        thread.start()

    def stop(self) -> None:
        with self._cond:
            if not self._running:
                return
            self._running = False
            thread = self._thread
            self._thread = None
            self._cond.notify_all()
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
            if thread.is_alive():
                self._logger.warning("HA sync worker did not exit within timeout")

    def notify_change(self) -> None:
        """Request a debounced reconcile of the HA tree against the database."""
        now = time.time()
        with self._cond:
            if not self._change_pending:
                self._change_pending = True
                self._first_change_ts = now
            self._last_change_ts = now
            self._cond.notify_all()

    def notify_connected(self) -> None:
        """Request initial-state publishing + log resubscription after an MQTT (re)connect."""
        with self._cond:
            self._connected_pending = True
            self._cond.notify_all()

    def run_task(self, task: Callable[[], None]) -> None:
        """Run a one-off action on the worker thread (serialized with reconciles)."""
        with self._cond:
            self._tasks.append(task)
            self._cond.notify_all()

    def _loop(self) -> None:
        while True:
            tasks: List[Callable[[], None]] = []
            run_connected = False
            run_reconcile = False

            with self._cond:
                while True:
                    if not self._running:
                        return
                    now = time.time()
                    change_ready = self._change_pending and (
                        now - self._last_change_ts >= self.DEBOUNCE_SECONDS
                        or now - self._first_change_ts >= self.MAX_COALESCE_SECONDS
                    )
                    periodic_ready = now >= self._next_periodic_ts
                    if self._tasks or self._connected_pending or change_ready or periodic_ready:
                        break
                    timeout = self._next_periodic_ts - now
                    if self._change_pending:
                        timeout = min(
                            timeout,
                            self._last_change_ts + self.DEBOUNCE_SECONDS - now,
                            self._first_change_ts + self.MAX_COALESCE_SECONDS - now,
                        )
                    self._cond.wait(timeout=max(0.05, timeout))

                tasks = self._tasks
                self._tasks = []
                run_connected = self._connected_pending
                self._connected_pending = False
                if change_ready or periodic_ready:
                    run_reconcile = True
                    self._change_pending = False
                if periodic_ready:
                    self._next_periodic_ts = time.time() + self.RECONCILE_INTERVAL_SECONDS

            for task in tasks:
                try:
                    task()
                except Exception as exc:
                    self._logger.warning(f"HA sync task failed: {exc}")

            if run_connected:
                try:
                    self._device_manager.handle_mqtt_connected()
                except Exception as exc:
                    self._logger.warning(f"HA connected handling failed: {exc}")
                # A reconnect may have happened while the tree drifted — align it.
                run_reconcile = True

            if run_reconcile:
                try:
                    self._device_manager.reconcile()
                except Exception as exc:
                    self._logger.warning(f"HA reconcile failed: {exc}")
