import math
import tempfile
from typing import Any, Dict, Optional

from .ir_ctl_engine import IrCtlEngine
from .ir_signal_parser import IrSignalParser


class IrSenderService:
    def __init__(self, engine: IrCtlEngine, parser: IrSignalParser) -> None:
        self._engine = engine
        self._parser = parser

    def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        encoding = str(payload.get("encoding") or "raw").strip().lower()
        mode = str(payload.get("mode") or "").strip().lower()

        if mode not in ("press", "hold"):
            raise ValueError("mode must be 'press' or 'hold'")

        if encoding == "protocol":
            return self._send_protocol(payload)

        return self._send_raw(payload)

    # ------------------------------------------------------------------
    # Protocol path (NEC, Samsung32, RC5, etc.)
    # ------------------------------------------------------------------

    def _send_protocol(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        mode = str(payload.get("mode") or "press").strip().lower()
        protocol = str(payload.get("protocol") or "").strip()
        address = str(payload.get("address") or "").strip()
        command_hex = str(payload.get("command_hex") or "").strip()

        if not protocol or not address or not command_hex:
            raise ValueError("protocol, address, and command_hex are required for protocol signals")

        # Import here to avoid a hard dependency on the marketplace package
        # when the service is used without marketplace support.
        from marketplace.ir_protocol_utils import get_ir_ctl_args
        ir_ctl_protocol, scancode = get_ir_ctl_args(protocol, address, command_hex)

        stdout, stderr = self._engine.send_protocol(ir_ctl_protocol, scancode)

        return {
            "mode": mode,
            "carrier_hz": None,
            "duty_cycle": None,
            "gap_us": None,
            "repeats": 0,
            "stdout": stdout,
            "stderr": stderr,
        }

    # ------------------------------------------------------------------
    # Raw path (existing logic)
    # ------------------------------------------------------------------

    def _send_raw(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        mode = str(payload.get("mode") or "").strip().lower()

        hold_ms = payload.get("hold_ms")
        press_initial_text = str(payload.get("press_initial") or "").strip()
        if not press_initial_text:
            raise ValueError("No signals for button")

        carrier_hz = int(payload["carrier_hz"]) if payload.get("carrier_hz") else None
        duty_cycle = int(payload["duty_cycle"]) if payload.get("duty_cycle") else None

        with tempfile.TemporaryDirectory(prefix="ir_tx_") as tmpdir:
            if mode == "press":
                press_initial = self._parser.decode_pulses(press_initial_text)
                press_path = f"{tmpdir}/press_initial.txt"
                self._write_pulse_space_file(press_path, press_initial)

                stdout, stderr = self._engine.send_pulse_space_files(
                    [press_path],
                    carrier_hz=carrier_hz,
                    duty_cycle=duty_cycle,
                )

                return {
                    "mode": "press",
                    "carrier_hz": carrier_hz,
                    "duty_cycle": duty_cycle,
                    "gap_us": None,
                    "repeats": 0,
                    "stdout": stdout,
                    "stderr": stderr,
                }

            if hold_ms is None or int(hold_ms) <= 0:
                raise ValueError("hold_ms is required for mode=hold")

            hold_initial_text = str(payload.get("hold_initial") or "").strip()
            hold_repeat_text = str(payload.get("hold_repeat") or "").strip()
            if not hold_initial_text or not hold_repeat_text:
                raise ValueError("Hold signals are missing for this button")

            hold_gap_us = payload.get("hold_gap_us")
            if hold_gap_us is None or int(hold_gap_us) <= 0:
                raise ValueError("Hold gap is missing for this button; re-capture hold to compute it")
            hold_gap_us_value = int(hold_gap_us)

            hold_initial = self._parser.decode_pulses(hold_initial_text)
            hold_repeat = self._parser.decode_pulses(hold_repeat_text)

            initial_path = f"{tmpdir}/hold_initial.txt"
            repeat_path = f"{tmpdir}/hold_repeat.txt"
            self._write_pulse_space_file(initial_path, hold_initial)
            self._write_pulse_space_file(repeat_path, hold_repeat)

            repeat_count = self._estimate_repeat_count(
                hold_ms=int(hold_ms),
                initial_pulses=hold_initial,
                repeat_pulses=hold_repeat,
                gap_us=hold_gap_us_value,
            )

            file_paths = [initial_path] + [repeat_path] * repeat_count

            stdout, stderr = self._engine.send_pulse_space_files(
                file_paths,
                gap_us=hold_gap_us_value,
                carrier_hz=carrier_hz,
                duty_cycle=duty_cycle,
            )

            return {
                "mode": "hold",
                "hold_ms": int(hold_ms),
                "carrier_hz": carrier_hz,
                "duty_cycle": duty_cycle,
                "gap_us": hold_gap_us_value,
                "repeats": repeat_count,
                "stdout": stdout,
                "stderr": stderr,
            }

    def _write_pulse_space_file(self, path: str, pulses: list[int]) -> None:
        text = self._parser.to_pulse_space_text(pulses)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def _estimate_repeat_count(self, hold_ms: int, initial_pulses: list[int], repeat_pulses: list[int], gap_us: Optional[int]) -> int:
        target_us = int(hold_ms) * 1000

        initial_us = sum(abs(int(v)) for v in initial_pulses)
        repeat_us = sum(abs(int(v)) for v in repeat_pulses)

        repeat_period_us = repeat_us + (int(gap_us) if gap_us and gap_us > 0 else 0)

        remaining_us = max(0, target_us - initial_us)
        if repeat_period_us <= 0:
            return 1

        return max(1, int(math.ceil(remaining_us / float(repeat_period_us))))
