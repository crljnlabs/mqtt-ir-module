#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
platformio_env="${PLATFORMIO_ENV:-esp32dev}"
monitor_baud="${MONITOR_BAUD:-115200}"
python_bin=""
selected_port=""
detected_ports=()

print_header() {
  echo "ESP Agent build + flash"
  echo "Environment: ${platformio_env}"
}

append_port_if_unique() {
  local candidate="$1"
  local existing
  for existing in "${detected_ports[@]:-}"; do
    if [ "${existing}" = "${candidate}" ]; then
      return
    fi
  done
  detected_ports+=("${candidate}")
}

detect_serial_ports() {
  shopt -s nullglob

  local patterns=(
    /dev/cu.usb*
    /dev/cu.SLAB_USBtoUART*
    /dev/cu.wchusbserial*
    /dev/cu.usbserial*
    /dev/tty.usb*
    /dev/ttyUSB*
    /dev/ttyACM*
  )
  local pattern
  local device
  for pattern in "${patterns[@]}"; do
    for device in ${pattern}; do
      [ -e "${device}" ] || continue
      append_port_if_unique "${device}"
    done
  done

  shopt -u nullglob
}

resolve_python_with_platformio() {
  local candidates=()
  local candidate

  if [ -n "${PYTHON_BIN:-}" ]; then
    candidates+=("${PYTHON_BIN}")
  fi
  candidates+=("python" "python3")

  for candidate in "${candidates[@]}"; do
    if ! command -v "${candidate}" >/dev/null 2>&1; then
      continue
    fi
    if "${candidate}" -m platformio --version >/dev/null 2>&1; then
      python_bin="${candidate}"
      return
    fi
  done

  echo "Could not find a Python interpreter with platformio installed." >&2
  echo "Install it in your active environment: python -m pip install -U platformio" >&2
  echo "Or set PYTHON_BIN to a Python that already has platformio." >&2
  exit 1
}

show_platformio_device_list() {
  echo "PlatformIO device list:"
  if ! "${python_bin}" -m platformio device list; then
    echo "PlatformIO device list is unavailable. Continuing with /dev auto-detection."
  fi
}

prompt_manual_port() {
  while true; do
    read -r -p "Enter serial port path (example: /dev/cu.usbserial-110): " selected_port
    selected_port="$(echo "${selected_port}" | xargs)"
    if [ -n "${selected_port}" ]; then
      return
    fi
    echo "Serial port path cannot be empty."
  done
}

select_serial_port() {
  local count="${#detected_ports[@]}"
  local choice
  local index

  if [ "${count}" -eq 0 ]; then
    echo "No serial ports auto-detected."
    prompt_manual_port
    return
  fi

  if [ "${count}" -eq 1 ]; then
    selected_port="${detected_ports[0]}"
    read -r -p "Use detected port ${selected_port}? [Y/n]: " choice
    case "${choice}" in
      n|N|no|NO)
        prompt_manual_port
        ;;
      *)
        ;;
    esac
    return
  fi

  echo "Detected serial ports:"
  index=1
  for choice in "${detected_ports[@]}"; do
    echo "  ${index}) ${choice}"
    index=$((index + 1))
  done
  echo "  m) Enter port manually"

  while true; do
    read -r -p "Select a port number or 'm': " choice
    case "${choice}" in
      m|M)
        prompt_manual_port
        return
        ;;
      ''|*[!0-9]*)
        echo "Invalid selection. Enter a number or 'm'."
        ;;
      *)
        if [ "${choice}" -lt 1 ] || [ "${choice}" -gt "${count}" ]; then
          echo "Selection out of range."
          continue
        fi
        selected_port="${detected_ports[$((choice - 1))]}"
        return
        ;;
    esac
  done
}

run_platformio() {
  (cd "${script_dir}" && "${python_bin}" -m platformio "$@")
}

build_erase_upload() {
  echo ""
  echo "Running build for ${platformio_env}..."
  run_platformio run -e "${platformio_env}"

  echo ""
  echo "Erasing flash on ${selected_port}..."
  run_platformio run -e "${platformio_env}" -t erase --upload-port "${selected_port}"

  echo ""
  echo "Uploading firmware to ${selected_port}..."
  run_platformio run -e "${platformio_env}" -t upload --upload-port "${selected_port}"

  echo ""
  echo "Build + erase + upload completed."
}

prompt_open_monitor() {
  local choice
  read -r -p "Open serial monitor now on ${selected_port} (${monitor_baud} baud)? [Y/n]: " choice
  case "${choice}" in
    n|N|no|NO)
      return
      ;;
    *)
      echo ""
      echo "Opening monitor. Quit with Ctrl+C."
      run_platformio device monitor --port "${selected_port}" --baud "${monitor_baud}"
      ;;
  esac
}

print_header
resolve_python_with_platformio
show_platformio_device_list
detect_serial_ports
select_serial_port

echo "Selected serial port: ${selected_port}"
echo "Make sure serial monitors (Logs & Console, screen, miniterm) are closed."
build_erase_upload
prompt_open_monitor
