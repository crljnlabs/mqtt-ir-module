
import os
import subprocess
import tempfile
from typing import List, Optional, Tuple


class IrCtlEngine:
    def __init__(self, ir_rx_device: str, ir_tx_device: str, wideband_default: bool = False) -> None:
        self._ir_rx_device = ir_rx_device
        self._ir_tx_device = ir_tx_device
        self._wideband_default = wideband_default

    def receive_one_message(self, timeout_ms: int, wideband: Optional[bool] = None) -> Tuple[str, str, str]:
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be > 0")

        use_wideband = self._wideband_default if wideband is None else bool(wideband)

        with tempfile.NamedTemporaryFile(prefix="ir_rx_", delete=False) as tmp:
            path = tmp.name

        cmd: List[str] = [
            "ir-ctl",
            "-d",
            self._ir_rx_device,
            f"--receive={path}",
            "--one-shot",
        ]
        if use_wideband:
            cmd.append("--wideband")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(timeout_ms / 1000.0, 0.1),
            )
        except subprocess.TimeoutExpired:
            self._safe_remove(path)
            raise TimeoutError("No IR message received within timeout") from None

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        raw = ""
        try:
            raw = self._read_all_text(path)
        finally:
            self._safe_remove(path)

        if proc.returncode != 0:
            raise ValueError(f"ir-ctl receive failed (code={proc.returncode}): {stderr or stdout}")

        if not raw:
            raise TimeoutError("No IR message received")

        return raw, stdout, stderr


    def send_protocol(
        self,
        ir_ctl_protocol: str,
        scancode: int,
        emitters: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Send an IR signal using a decoded protocol via ir-ctl --protocol/--scancode."""
        # Use combined --scancode=protocol:hex format (supported since v4l-utils 1.18,
        # including Debian Bookworm 1.22.1). The split --protocol/--scancode flags
        # were introduced in a later version and are not universally available.
        cmd: List[str] = [
            "ir-ctl",
            "-d", self._ir_tx_device,
            f"--scancode={ir_ctl_protocol}:{hex(scancode)}",
        ]
        if emitters:
            cmd.append(f"--emitters={emitters}")

        proc = subprocess.run(cmd, capture_output=True, text=True)
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        if proc.returncode != 0:
            raise RuntimeError(
                f"ir-ctl protocol send failed (code={proc.returncode}): {stderr or stdout}"
            )

        return stdout, stderr

    def send_pulse_space_files(
        self,
        file_paths: List[str],
        gap_us: Optional[int] = None,
        carrier_hz: Optional[int] = None,
        duty_cycle: Optional[int] = None,
        emitters: Optional[str] = None,
    ) -> Tuple[str, str]:
        if not file_paths:
            raise ValueError("file_paths must not be empty")

        cmd: List[str] = ["ir-ctl", "-d", self._ir_tx_device]

        if gap_us is not None and gap_us > 0:
            cmd.append(f"--gap={int(gap_us)}")
        if carrier_hz is not None and carrier_hz > 0:
            cmd.append(f"--carrier={int(carrier_hz)}")
        if duty_cycle is not None and duty_cycle > 0:
            cmd.append(f"--duty-cycle={int(duty_cycle)}")
        if emitters:
            cmd.append(f"--emitters={emitters}")

        for p in file_paths:
            cmd.append(f"--send={p}")

        proc = subprocess.run(cmd, capture_output=True, text=True)
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        if proc.returncode != 0:
            raise RuntimeError(f"ir-ctl send failed (code={proc.returncode}): {stderr or stdout}")

        return stdout, stderr

    def _read_all_text(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except FileNotFoundError:
            return ""
        return (content or "").strip()

    def _safe_remove(self, path: str) -> None:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        
