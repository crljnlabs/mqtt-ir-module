#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
build_dir="${script_dir}/.pio/build/esp32dev"
source_firmware="${build_dir}/firmware.bin"
source_bootloader="${build_dir}/bootloader.bin"
source_partitions="${build_dir}/partitions.bin"
target_fw_dir="${repo_root}/backend/firmware_template/files"
catalog_path="${repo_root}/backend/firmware_template/catalog.json"
version_file="${script_dir}/VERSION"
selected_version=""

normalize_version() {
  local raw="$1"
  raw="$(echo "${raw}" | xargs)"
  raw="${raw#v}"
  if [[ ! "${raw}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    return 1
  fi
  printf '%s' "${raw}"
}

read_version_file() {
  if [ ! -f "${version_file}" ]; then
    printf '%s\n' "0.0.1" > "${version_file}"
  fi
  local raw_version
  raw_version="$(cat "${version_file}")"
  local normalized
  if ! normalized="$(normalize_version "${raw_version}")"; then
    echo "Invalid version in ${version_file}: ${raw_version}" >&2
    echo "Expected x.y.z or vx.y.z." >&2
    exit 1
  fi
  printf '%s' "${normalized}"
}

write_version_file() {
  local normalized="$1"
  printf '%s\n' "${normalized}" > "${version_file}"
}

select_firmware_version() {
  local current_version="$1"
  local user_input

  while true; do
    read -r -p "Firmware version (x.y.z or vx.y.z) [${current_version}]: " user_input
    user_input="$(echo "${user_input}" | xargs)"
    if [ -z "${user_input}" ]; then
      selected_version="${current_version}"
      return
    fi

    local normalized
    if normalized="$(normalize_version "${user_input}")"; then
      selected_version="${normalized}"
      return
    fi
    echo "Invalid version format. Expected x.y.z or vx.y.z." >&2
  done
}

run_build() {
  if command -v pio >/dev/null 2>&1; then
    (cd "${script_dir}" && pio run -e esp32dev)
    return
  fi
  (cd "${script_dir}" && python3 -m platformio run -e esp32dev)
}

compute_sha256() {
  local file_path="$1"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${file_path}" | awk '{print $1}'
    return
  fi
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${file_path}" | awk '{print $1}'
    return
  fi

  python3 - "${file_path}" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
digest = hashlib.sha256(path.read_bytes()).hexdigest()
print(digest)
PY
}

resolve_boot_app0() {
  local env_path="${BOOT_APP0_PATH:-}"
  if [ -n "${env_path}" ] && [ -f "${env_path}" ]; then
    printf '%s' "${env_path}"
    return
  fi

  local default_path="${HOME}/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin"
  if [ -f "${default_path}" ]; then
    printf '%s' "${default_path}"
    return
  fi

  echo "Could not find boot_app0.bin. Set BOOT_APP0_PATH to its full path." >&2
  exit 1
}

resolve_esptool() {
  local env_path="${ESPTOOL_PY_PATH:-}"
  if [ -n "${env_path}" ] && [ -f "${env_path}" ]; then
    printf '%s' "${env_path}"
    return
  fi

  local default_path="${HOME}/.platformio/packages/tool-esptoolpy/esptool.py"
  if [ -f "${default_path}" ]; then
    printf '%s' "${default_path}"
    return
  fi

  if command -v esptool.py >/dev/null 2>&1; then
    command -v esptool.py
    return
  fi

  echo "Could not find esptool.py. Set ESPTOOL_PY_PATH to its full path." >&2
  exit 1
}

build_factory_firmware() {
  local target_factory_path="$1"
  if [ ! -f "${source_bootloader}" ]; then
    echo "Build completed but bootloader file was not found: ${source_bootloader}" >&2
    exit 1
  fi
  if [ ! -f "${source_partitions}" ]; then
    echo "Build completed but partitions file was not found: ${source_partitions}" >&2
    exit 1
  fi

  local boot_app0_path
  boot_app0_path="$(resolve_boot_app0)"
  local esptool_path
  esptool_path="$(resolve_esptool)"

  if [ -f "${esptool_path}" ]; then
    python3 "${esptool_path}" --chip esp32 merge_bin -o "${target_factory_path}" \
      0x1000 "${source_bootloader}" \
      0x8000 "${source_partitions}" \
      0xe000 "${boot_app0_path}" \
      0x10000 "${source_firmware}"
    return
  fi

  "${esptool_path}" --chip esp32 merge_bin -o "${target_factory_path}" \
    0x1000 "${source_bootloader}" \
    0x8000 "${source_partitions}" \
    0xe000 "${boot_app0_path}" \
    0x10000 "${source_firmware}"
}

upsert_catalog_entry() {
  local version="$1"
  local ota_filename="$2"
  local ota_checksum="$3"
  local factory_filename="$4"
  local factory_checksum="$5"
  local catalog_file="$6"

  python3 - "${catalog_file}" "${version}" "${ota_filename}" "${ota_checksum}" "${factory_filename}" "${factory_checksum}" <<'PY'
import json
import os
import time
import sys

catalog_file = sys.argv[1]
version = sys.argv[2]
ota_filename = sys.argv[3]
ota_checksum = sys.argv[4]
factory_filename = sys.argv[5]
factory_checksum = sys.argv[6]

payload = {
    "schema_version": 1,
    "updated_at": 0,
    "firmwares": [],
}

if os.path.isfile(catalog_file):
    try:
        with open(catalog_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            payload = loaded
    except Exception:
        pass

if not isinstance(payload.get("firmwares"), list):
    payload["firmwares"] = []

entry = {
    "agent_type": "esp32",
    "version": version,
    "installable": True,
    "ota_file": ota_filename,
    "ota_sha256": ota_checksum,
    "factory_file": factory_filename,
    "factory_sha256": factory_checksum,
    "notes": "generated by esp-agent/build_and_publish.sh",
}

updated = False
for idx, item in enumerate(payload["firmwares"]):
    if not isinstance(item, dict):
        continue
    agent_type = str(item.get("agent_type") or "").strip().lower() or "esp32"
    item_version = str(item.get("version") or "").strip()
    if agent_type == "esp32" and item_version == version:
        merged = dict(item)
        merged.update(entry)
        payload["firmwares"][idx] = merged
        updated = True
        break

if not updated:
    payload["firmwares"].append(entry)

def version_key(item):
    raw = str(item.get("version") or "0.0.0")
    parts = raw.split(".")
    if len(parts) != 3:
        return (0, 0, 0)
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return (0, 0, 0)

payload["firmwares"] = sorted(payload["firmwares"], key=version_key, reverse=True)
payload["schema_version"] = int(payload.get("schema_version") or 1)
payload["updated_at"] = time.time()

os.makedirs(os.path.dirname(catalog_file), exist_ok=True)
with open(catalog_file, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
    f.write("\n")
PY
}

current_version="$(read_version_file)"
select_firmware_version "${current_version}"
if [ "${selected_version}" != "${current_version}" ]; then
  write_version_file "${selected_version}"
  echo "Updated ${version_file} to ${selected_version}"
fi

echo "Building firmware version: ${selected_version}"
run_build

if [ ! -f "${source_firmware}" ]; then
  echo "Build completed but firmware file was not found: ${source_firmware}" >&2
  exit 1
fi

echo "Build succeeded: ${source_firmware}"
read -r -p "Copy firmware to ${target_fw_dir}? [y/N]: " copy_choice

case "${copy_choice}" in
  y|Y|yes|YES)
    mkdir -p "${target_fw_dir}"
    target_ota_filename="esp32-ir-client-v${selected_version}.bin"
    target_ota_path="${target_fw_dir}/${target_ota_filename}"
    target_factory_filename="esp32-ir-client-v${selected_version}.factory.bin"
    target_factory_path="${target_fw_dir}/${target_factory_filename}"

    cp -f "${source_firmware}" "${target_ota_path}"
    build_factory_firmware "${target_factory_path}"

    ota_checksum="$(compute_sha256 "${target_ota_path}")"
    factory_checksum="$(compute_sha256 "${target_factory_path}")"
    upsert_catalog_entry "${selected_version}" "${target_ota_filename}" "${ota_checksum}" "${target_factory_filename}" "${factory_checksum}" "${catalog_path}"

    echo "Copied OTA firmware to: ${target_ota_path}"
    echo "Generated factory firmware to: ${target_factory_path}"
    echo "OTA SHA-256: ${ota_checksum}"
    echo "Factory SHA-256: ${factory_checksum}"
    echo "Catalog entry updated: ${catalog_path}"
    echo "Fields set: ota_file=${target_ota_filename}, factory_file=${target_factory_filename}"
    ;;
  *)
    echo "Build finished. No file was copied."
    ;;
esac
