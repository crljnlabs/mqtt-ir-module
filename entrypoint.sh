#!/usr/bin/env bash
# entrypoint.sh
set -euo pipefail

start_mode="${START_MODE:-hub}"
start_mode="${start_mode,,}"

# Initialize firmware catalog/files layout from image template.
data_dir="${DATA_DIR:-/data}"
firmware_dir="${FIRMWARE_DIR:-${data_dir}/firmware}"
firmware_template_dir="/opt/app/firmware_template"
if [ -f "${firmware_template_dir}/catalog.json" ]; then
    mkdir -p "${firmware_dir}/files"
    cp -f "${firmware_template_dir}/catalog.json" "${firmware_dir}/catalog.json"
fi
if [ -d "${firmware_template_dir}/files" ]; then
    mkdir -p "${firmware_dir}/files"
    cp -af "${firmware_template_dir}/files/." "${firmware_dir}/files/"
fi

case "${start_mode}" in
    agent)
        exec python3 agent_main.py
        ;;
    hub|"")
        exec uvicorn main:app --host 0.0.0.0 --port 80 --ws websockets --ws-ping-interval 15 --ws-ping-timeout 15 --log-config /opt/app/log_config.json
        ;;
    *)
        echo "Unsupported START_MODE: ${start_mode}" >&2
        exit 1
        ;;
esac
