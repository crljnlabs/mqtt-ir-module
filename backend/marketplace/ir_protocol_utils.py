"""
Utilities for mapping Flipper-IRDB protocol names to ir-ctl equivalents
and computing IR scancodes.

Scancode computation is per-protocol and assumes the address/command bytes
in Flipper-IRDB are stored most-significant byte first (big-endian).
This covers the most common use cases; edge cases may need adjustment.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple


def _parse_bytes(byte_str: str) -> List[int]:
    """Parse '20 00 00 00' into [0x20, 0x00, 0x00, 0x00]."""
    return [int(p, 16) for p in byte_str.strip().split() if p]


# Maps Flipper-IRDB protocol name → (ir-ctl protocol name, scancode function(addr_bytes, cmd_bytes) → int)
# Protocols not listed here are not yet supported for local ir-ctl sending.
_IR_CTL_MAP: Dict[str, Tuple[str, Callable[[List[int], List[int]], int]]] = {
    # Standard NEC: 8-bit address + 8-bit command
    "NEC": ("nec", lambda a, c: (a[0] << 8) | c[0]),
    # Extended NEC: 16-bit address (a[0]=high, a[1]=low) + 8-bit command
    "NECext": ("necx", lambda a, c: ((a[0] << 8 | a[1]) << 8) | c[0]),
    # Samsung 32-bit: address byte repeated, command byte repeated
    "Samsung32": ("samsung32", lambda a, c: (a[0] << 8) | c[0]),
    # Sony SIRC 12-bit: 5-bit address + 7-bit command
    "SIRC": ("sony-12", lambda a, c: ((a[0] & 0x1F) << 7) | (c[0] & 0x7F)),
    # Sony SIRC 15-bit: 8-bit address + 7-bit command
    "SIRC15": ("sony-15", lambda a, c: (a[0] << 7) | (c[0] & 0x7F)),
    # Sony SIRC 20-bit: 5-bit address + 8-bit extended + 7-bit command
    "SIRC20": ("sony-20", lambda a, c: (a[0] << 7) | (c[0] & 0x7F)),
    # Philips RC-5: 5-bit address + 6-bit command
    "RC5": ("rc-5", lambda a, c: ((a[0] & 0x1F) << 6) | (c[0] & 0x3F)),
    # Philips RC-6 mode 0: 8-bit address + 8-bit command
    "RC6": ("rc-6-0", lambda a, c: (a[0] << 8) | c[0]),
    # Kaseikyo / Panasonic: manufacturer code + device + sub-device + function
    # Stored in Flipper as address=manufacturer+device, command=sub-device+function
    "Kaseikyo": ("panasonic", lambda a, c: ((a[0] << 24) | (a[1] << 16) | (c[0] << 8) | c[1]) if len(a) >= 2 and len(c) >= 2 else (a[0] << 8) | c[0]),
    "Kaseikyo_Denon": ("panasonic", lambda a, c: ((a[0] << 8) | a[1]) if len(a) >= 2 else a[0]),
    "Kaseikyo_JVC": ("panasonic", lambda a, c: (a[0] << 8) | c[0]),
    "Kaseikyo_Mitsubishi": ("panasonic", lambda a, c: (a[0] << 8) | c[0]),
    "Kaseikyo_Sharp": ("panasonic", lambda a, c: (a[0] << 8) | c[0]),
    # JVC: 8-bit address + 8-bit command
    "JVC": ("jvc", lambda a, c: (a[0] << 8) | c[0]),
}

# Set of all protocols in Flipper-IRDB that we recognize (for UI display)
ALL_KNOWN_PROTOCOLS = set(_IR_CTL_MAP.keys()) | {
    "NEC42",
    "NEC48",
    "NECf16",
    "Haier",
    "Hitachi",
    "Daikin",
    "Mitsubishi",
    "MitsubishiAC",
    "Pioneer",
    "Sharp",
    "Toshiba",
    "Whirlpool",
    "GoodweatherAC",
    "ZX",
}


def is_protocol_supported(protocol: str) -> bool:
    """Returns True if the protocol can be sent via ir-ctl on the local agent."""
    return protocol in _IR_CTL_MAP


def get_ir_ctl_args(protocol: str, address_str: str, command_str: str) -> Tuple[str, int]:
    """
    Compute (ir_ctl_protocol_name, scancode_int) for the given Flipper-IRDB signal.
    Raises ValueError if the protocol is not supported.
    """
    entry = _IR_CTL_MAP.get(protocol)
    if not entry:
        raise ValueError(f"Protocol '{protocol}' is not supported for local ir-ctl send")

    ir_ctl_name, scancode_fn = entry
    addr = _parse_bytes(address_str)
    cmd = _parse_bytes(command_str)

    if not addr or not cmd:
        raise ValueError(f"Invalid address or command for protocol '{protocol}'")

    scancode = scancode_fn(addr, cmd)
    return ir_ctl_name, scancode


def get_mqtt_protocol_payload(protocol: str, address_str: str, command_str: str) -> Dict[str, Any]:
    """
    Build the protocol section of an MQTT send payload for an IR agent.
    The agent is responsible for decoding this into the correct send call.
    """
    addr = _parse_bytes(address_str)
    cmd = _parse_bytes(command_str)
    return {
        "protocol": protocol,
        # Pass address and command as hex strings so the agent can decode them
        # regardless of the number of bytes.
        "address": f"0x{int(''.join(f'{b:02X}' for b in addr), 16):X}" if addr else "0x0",
        "command": f"0x{int(''.join(f'{b:02X}' for b in cmd), 16):X}" if cmd else "0x0",
    }
