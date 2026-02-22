import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote


class FirmwareCatalog:
    SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
    SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
    DEFAULT_AGENT_TYPE = "esp32"

    def __init__(self, root_dir: str) -> None:
        self._root_dir = Path(str(root_dir or "").strip() or "./firmware")
        self._files_dir = self._root_dir / "files"
        self._catalog_path = self._root_dir / "catalog.json"
        self._logger = logging.getLogger("firmware_catalog")
        self._lock = threading.Lock()

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    @property
    def files_dir(self) -> Path:
        return self._files_dir

    @property
    def catalog_path(self) -> Path:
        return self._catalog_path

    def ensure_layout(self) -> None:
        with self._lock:
            self._ensure_layout_locked()

    def _ensure_layout_locked(self) -> None:
        # Caller must hold self._lock.
        if not self._lock.locked():
            raise RuntimeError("firmware_catalog_lock_required")
        if not self._root_dir.exists():
            self._root_dir.mkdir(parents=True, exist_ok=True)
        if not self._files_dir.exists():
            self._files_dir.mkdir(parents=True, exist_ok=True)
        if self._catalog_path.exists():
            return
        payload = self._default_catalog_payload()
        self._catalog_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_firmwares(self, agent_type: str = DEFAULT_AGENT_TYPE, include_non_installable: bool = True) -> List[Dict[str, Any]]:
        normalized_agent_type = self._normalize_agent_type(agent_type)
        entries = self._read_entries()
        filtered: List[Dict[str, Any]] = []
        for entry in entries:
            if self._normalize_agent_type(entry.get("agent_type")) != normalized_agent_type:
                continue
            if not include_non_installable and not bool(entry.get("installable")):
                continue
            filtered.append(self._decorate_file_flags(entry))
        filtered.sort(key=lambda item: self._version_key(str(item.get("version") or "0.0.0")), reverse=True)
        return filtered

    def latest_firmware(self, agent_type: str = DEFAULT_AGENT_TYPE, include_non_installable: bool = False) -> Optional[Dict[str, Any]]:
        entries = self.list_firmwares(agent_type=agent_type, include_non_installable=include_non_installable)
        if not entries:
            return None
        return dict(entries[0])

    def resolve_firmware(
        self,
        agent_type: str = DEFAULT_AGENT_TYPE,
        version: Optional[str] = None,
        require_installable: bool = True,
    ) -> Dict[str, Any]:
        normalized_agent_type = self._normalize_agent_type(agent_type)
        normalized_version = self._normalize_version(version) if version is not None else None
        entries = self.list_firmwares(
            agent_type=normalized_agent_type,
            include_non_installable=not require_installable,
        )
        if normalized_version:
            for entry in entries:
                if str(entry.get("version") or "") != normalized_version:
                    continue
                return self._ensure_resolvable(entry, require_installable=require_installable)
            raise ValueError("firmware_version_not_found")
        if not entries:
            raise ValueError("firmware_not_found")
        return self._ensure_resolvable(entries[0], require_installable=require_installable)

    def ota_status(self, agent_type: str, current_version: str, ota_supported: bool) -> Dict[str, Any]:
        normalized_agent_type = self._normalize_agent_type(agent_type)
        normalized_current = self._normalize_version(current_version, allow_empty=True)
        latest = self.latest_firmware(agent_type=normalized_agent_type, include_non_installable=False)
        latest_version = str(latest.get("version") or "") if latest else ""
        update_available = False
        if bool(ota_supported) and normalized_current and latest_version:
            update_available = self.compare_versions(latest_version, normalized_current) > 0
        return {
            "supported": bool(ota_supported),
            "agent_type": normalized_agent_type,
            "current_version": normalized_current or "",
            "latest_version": latest_version,
            "update_available": bool(update_available),
        }

    def compare_versions(self, left: str, right: str) -> int:
        left_key = self._version_key(self._normalize_version(left))
        right_key = self._version_key(self._normalize_version(right))
        if left_key > right_key:
            return 1
        if left_key < right_key:
            return -1
        return 0

    def build_firmware_url(self, request: Any, public_base_url: str, filename: str) -> str:
        normalized_filename = self._normalize_filename(filename)
        host = str(request.headers.get("host") or "").strip()
        scheme = str(request.url.scheme or "http").strip() or "http"
        if not host:
            raise ValueError("request_host_missing")
        base_prefix = self._normalize_base_prefix(public_base_url)
        path = f"{base_prefix}/firmware/{quote(normalized_filename)}"
        return f"{scheme}://{host}{path}"

    def build_webtools_manifest(self, request: Any, public_base_url: str, agent_type: str = DEFAULT_AGENT_TYPE) -> Dict[str, Any]:
        firmware = self.resolve_firmware(agent_type=agent_type, version=None, require_installable=True)
        factory_file = str(firmware.get("factory_file") or "").strip()
        ota_file = str(firmware.get("ota_file") or "").strip()
        factory_exists = bool(factory_file and (self._files_dir / factory_file).is_file())
        ota_exists = bool(ota_file and (self._files_dir / ota_file).is_file())
        filename = ""
        offset = 0

        # Use factory image only when it is distinct from OTA image.
        # If both names are the same, treat it as OTA-only and flash to app offset.
        if factory_exists and factory_file != ota_file:
            filename = factory_file
            offset = 0
        elif ota_exists:
            filename = ota_file
            offset = 0x10000
        elif factory_exists:
            filename = factory_file
            offset = 0

        if not filename:
            raise ValueError("firmware_file_missing")
        url = self.build_firmware_url(request=request, public_base_url=public_base_url, filename=filename)
        return {
            "name": "ESP32 IR Client",
            "version": str(firmware.get("version") or ""),
            "builds": [
                {
                    "chipFamily": "ESP32",
                    "parts": [
                        {
                            "path": url,
                            "offset": offset,
                        }
                    ],
                }
            ],
        }

    def _default_catalog_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "updated_at": time.time(),
            "firmwares": [
                {
                    "agent_type": self.DEFAULT_AGENT_TYPE,
                    "version": "0.0.1",
                    "installable": False,
                    "ota_file": "esp32-ir-client-v0.0.1.bin",
                    "ota_sha256": "",
                    "factory_file": "esp32-ir-client-v0.0.1.factory.bin",
                    "factory_sha256": "",
                    "notes": "placeholder entry - set installable=true after adding binaries and checksums",
                }
            ],
        }

    def _read_entries(self) -> List[Dict[str, Any]]:
        with self._lock:
            self._ensure_layout_locked()
            try:
                payload = json.loads(self._catalog_path.read_text(encoding="utf-8"))
            except Exception as exc:
                self._logger.warning(f"Failed to load firmware catalog {self._catalog_path}: {exc}")
                return []
        raw_entries = payload.get("firmwares")
        if not isinstance(raw_entries, list):
            return []
        entries: List[Dict[str, Any]] = []
        for item in raw_entries:
            normalized = self._normalize_entry(item)
            if normalized is None:
                continue
            entries.append(normalized)
        return entries

    def _normalize_entry(self, item: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        try:
            version = self._normalize_version(item.get("version"))
        except ValueError:
            return None
        agent_type = self._normalize_agent_type(item.get("agent_type"))
        installable = bool(item.get("installable", True))
        ota_file = self._normalize_filename(item.get("ota_file"))
        ota_sha256 = self._normalize_sha256(item.get("ota_sha256"))
        factory_file = self._normalize_filename(item.get("factory_file"), allow_empty=True)
        factory_sha256 = self._normalize_sha256(item.get("factory_sha256"), allow_empty=True)
        notes = str(item.get("notes") or "").strip()

        if installable:
            if not ota_file:
                return None
            if not ota_sha256:
                return None
            if factory_file and not factory_sha256:
                return None

        return {
            "agent_type": agent_type,
            "version": version,
            "installable": installable,
            "ota_file": ota_file,
            "ota_sha256": ota_sha256,
            "factory_file": factory_file or "",
            "factory_sha256": factory_sha256 or "",
            "notes": notes,
        }

    def _ensure_resolvable(self, entry: Dict[str, Any], require_installable: bool) -> Dict[str, Any]:
        payload = dict(entry or {})
        installable = bool(payload.get("installable"))
        if require_installable and not installable:
            raise ValueError("firmware_not_installable")
        ota_file = str(payload.get("ota_file") or "").strip()
        if not ota_file:
            raise ValueError("firmware_file_missing")
        ota_path = self._files_dir / ota_file
        if require_installable and not ota_path.is_file():
            raise ValueError("firmware_file_missing")
        return self._decorate_file_flags(payload)

    def _decorate_file_flags(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(entry or {})
        ota_file = str(payload.get("ota_file") or "").strip()
        factory_file = str(payload.get("factory_file") or "").strip()
        payload["ota_exists"] = bool(ota_file and (self._files_dir / ota_file).is_file())
        payload["factory_exists"] = bool(factory_file and (self._files_dir / factory_file).is_file())
        return payload

    def _normalize_agent_type(self, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return self.DEFAULT_AGENT_TYPE
        return normalized

    def _normalize_version(self, value: Any, allow_empty: bool = False) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            if allow_empty:
                return ""
            raise ValueError("firmware_version_invalid")
        if not self.SEMVER_PATTERN.fullmatch(normalized):
            raise ValueError("firmware_version_invalid")
        return normalized

    def _normalize_filename(self, value: Any, allow_empty: bool = False) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            if allow_empty:
                return ""
            return ""
        # Only allow file names under /firmware without path traversal.
        if os.path.basename(normalized) != normalized:
            return ""
        if normalized.startswith("."):
            return ""
        return normalized

    def _normalize_sha256(self, value: Any, allow_empty: bool = False) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return "" if allow_empty else ""
        if not self.SHA256_PATTERN.fullmatch(normalized):
            return ""
        return normalized

    def _version_key(self, version: str) -> Tuple[int, int, int]:
        parts = str(version or "0.0.0").split(".")
        if len(parts) != 3:
            return 0, 0, 0
        try:
            return int(parts[0]), int(parts[1]), int(parts[2])
        except Exception:
            return 0, 0, 0

    def _normalize_base_prefix(self, public_base_url: str) -> str:
        normalized = str(public_base_url or "/").strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        if normalized.endswith("/"):
            normalized = normalized[:-1]
        if not normalized:
            return ""
        if normalized == "/":
            return ""
        return normalized
