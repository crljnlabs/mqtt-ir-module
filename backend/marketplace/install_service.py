"""
Installs a marketplace remote from Flipper-IRDB into the local database.

For each signal in the .ir file:
  - raw type   → stored as encoding='raw', press_initial=timing_data
  - parsed type → stored as encoding='protocol', protocol/address/command_hex fields populated
"""
import logging
import urllib.parse
from typing import Any, Dict, Optional

import requests

from .ir_file_parser import parse_ir_file

logger = logging.getLogger(__name__)

_RAW_BASE = "https://raw.githubusercontent.com/Lucaslhm/Flipper-IRDB/main/"


class InstallService:
    def __init__(self, database: Any) -> None:
        self._db = database

    def install(self, path: str, remote_name: str) -> Dict[str, Any]:
        """
        Fetch the .ir file at the given path and install it as a new Remote.

        Raises ValueError on name conflict or if the path is already installed.
        Raises RuntimeError on network or parse failure.
        """
        remote_name = remote_name.strip()
        if not remote_name:
            raise ValueError("remote_name must not be empty")

        # Prevent duplicate installs of the same marketplace file
        existing_by_path = self._db.remotes.get_by_marketplace_path(path)
        if existing_by_path:
            raise ValueError(
                f"This remote is already installed as '{existing_by_path['name']}'."
            )

        # Guard against name collisions with user-created remotes
        existing_by_name = self._db.remotes.get_by_name(remote_name)
        if existing_by_name:
            raise ValueError(
                f"A remote named '{remote_name}' already exists. Choose a different name."
            )

        # Fetch and parse the .ir file
        url = _RAW_BASE + urllib.parse.quote(path)
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to download IR file: {exc}") from exc

        signals = parse_ir_file(resp.text)
        if not signals:
            raise ValueError("The .ir file contains no valid signals.")

        # Derive carrier_hz and duty_cycle from the first raw signal (applies to the whole remote)
        carrier_hz: Optional[int] = None
        duty_cycle: Optional[int] = None
        for sig in signals:
            if sig["type"] == "raw":
                carrier_hz = sig.get("frequency")
                duty_cycle = sig.get("duty_cycle")
                break

        # Create the Remote
        remote = self._db.remotes.create(
            name=remote_name,
            marketplace_source="flipper-irdb",
            marketplace_path=path,
            carrier_hz=carrier_hz,
            duty_cycle=duty_cycle,
        )
        remote_id = remote["id"]

        # Create a Button + Signal per entry in the .ir file
        installed_count = 0
        for sig in signals:
            name = sig.get("name", "").strip()
            if not name:
                continue

            try:
                button = self._db.buttons.create(remote_id=remote_id, name=name)
                button_id = button["id"]

                if sig["type"] == "raw":
                    data = sig.get("data", "").strip()
                    if not data:
                        continue
                    sample_count = len(data.split())
                    self._db.signals.upsert_press(
                        button_id=button_id,
                        press_initial=data,
                        press_repeat=None,
                        sample_count_press=sample_count,
                        quality_score_press=None,
                        encoding="raw",
                    )
                elif sig["type"] == "parsed":
                    self._db.signals.upsert_protocol(
                        button_id=button_id,
                        protocol=sig["protocol"],
                        address=sig["address"],
                        command_hex=sig["command"],
                    )
                installed_count += 1
            except Exception as exc:
                logger.warning(f"Skipping signal '{name}' during install: {exc}")

        logger.info(
            f"Installed marketplace remote '{remote_name}' from '{path}' "
            f"({installed_count}/{len(signals)} signals)"
        )
        return remote
