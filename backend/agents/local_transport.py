import time
from typing import Any, Dict, List

from electronics.ir_ctl_engine import IrCtlEngine
from electronics.ir_sender_service import IrSenderService
from electronics.ir_signal_parser import IrSignalParser


class LocalTransport:
    def __init__(self, engine: IrCtlEngine, parser: IrSignalParser) -> None:
        self._engine = engine
        self._sender = IrSenderService(engine=engine, parser=parser)

    def learn_capture(self, timeout_ms: int) -> Dict[str, Any]:
        raw, stdout, stderr = self._engine.receive_one_message(timeout_ms=timeout_ms)
        return {"raw": raw, "stdout": stdout, "stderr": stderr}

    def learn_hold_capture(self, total_timeout_ms: int, idle_timeout_ms: int) -> Dict[str, Any]:
        """Capture all hold frames in one shot without external round-trips.

        Returns a list of frames with agent-side timestamps so the hub can
        compute hold_gap_us from accurate, latency-free timing.
        """
        deadline = time.time() + total_timeout_ms / 1000.0
        frames: List[Dict[str, Any]] = []

        # First frame (initial press)
        remaining_ms = int(max(0.0, (deadline - time.time()) * 1000.0))
        if remaining_ms <= 0:
            raise ValueError("total_timeout_ms too short")
        raw, _stdout, _stderr = self._engine.receive_one_message(timeout_ms=remaining_ms)
        captured_at_us = int(time.perf_counter() * 1_000_000)
        frames.append({"raw": raw, "captured_at_us": captured_at_us})

        # Subsequent frames until idle timeout or deadline
        while True:
            remaining_ms = int(max(0.0, (deadline - time.time()) * 1000.0))
            if remaining_ms <= 0:
                break
            per_call_ms = min(idle_timeout_ms, remaining_ms)
            try:
                raw, _stdout, _stderr = self._engine.receive_one_message(timeout_ms=per_call_ms)
            except TimeoutError:
                break
            captured_at_us = int(time.perf_counter() * 1_000_000)
            frames.append({"raw": raw, "captured_at_us": captured_at_us})

        return {"frames": frames}

    def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._sender.send(payload)
