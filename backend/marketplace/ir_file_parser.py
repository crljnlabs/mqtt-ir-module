"""
Parser for Flipper-IRDB .ir file format.

File structure:
  Filetype: IR signals file
  Version: 1
  # optional comment
  name: <button_name>
  type: raw | parsed
  # raw fields:
  frequency: 38000
  duty_cycle: 0.330000
  data: <space-separated microsecond timings>
  # parsed fields:
  protocol: NEC
  address: 20 00 00 00
  command: 02 00 00 00
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def parse_ir_file(content: str) -> List[Dict[str, Any]]:
    """
    Parse a Flipper-IRDB .ir file and return a list of signal dicts.
    Malformed blocks are skipped with a warning.
    """
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = _split_blocks(content)
    results: List[Dict[str, Any]] = []
    for block in blocks:
        try:
            signal = _parse_block(block)
            if signal:
                results.append(signal)
        except Exception as exc:
            logger.debug(f"Skipping malformed IR block: {exc}")
    return results


def _split_blocks(content: str) -> List[str]:
    """Split file content into signal blocks using '#' lines as separators."""
    lines = content.split("\n")
    blocks: List[str] = []
    current: List[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or stripped == "":
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(stripped)

    if current:
        blocks.append("\n".join(current))

    return blocks


def _parse_block(block: str) -> Optional[Dict[str, Any]]:
    """Parse a single block into a signal dict. Returns None if not a valid signal."""
    kv: Dict[str, str] = {}
    for line in block.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            kv[key.strip()] = value.strip()

    name = kv.get("name", "").strip()
    signal_type = kv.get("type", "").strip().lower()

    if not name or signal_type not in ("raw", "parsed"):
        return None

    if signal_type == "raw":
        data = kv.get("data", "").strip()
        if not data:
            return None
        try:
            frequency = int(float(kv.get("frequency", "38000")))
        except ValueError:
            frequency = 38000
        try:
            duty_cycle = round(float(kv.get("duty_cycle", "0.33")) * 100)
        except ValueError:
            duty_cycle = 33
        return {
            "name": name,
            "type": "raw",
            "frequency": frequency,
            "duty_cycle": duty_cycle,
            "data": data,
        }

    if signal_type == "parsed":
        protocol = kv.get("protocol", "").strip()
        address = kv.get("address", "").strip()
        command = kv.get("command", "").strip()
        if not protocol or not address or not command:
            return None
        return {
            "name": name,
            "type": "parsed",
            "protocol": protocol,
            "address": address,
            "command": command,
        }

    return None
