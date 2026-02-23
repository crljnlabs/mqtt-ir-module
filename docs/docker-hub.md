# Docker Mode: `ir-hub`

This mode runs the Hub backend + frontend without local IR hardware dependencies.

## Build

```bash
docker build --target ir-hub -t mqtt-ir-hub:latest .
```

## Run

```bash
docker run --rm -p 8080:80 \
  -e DATA_DIR=/data \
  -e SETTINGS_MASTER_KEY=change-me \
  -v ir_hub_data:/data \
  mqtt-ir-hub:latest
```

## Environment reference

- `DATA_DIR` (optional, default: `/data`)
  Use only if you want a different internal path. For persistent data, mount a volume to this path.
- `FIRMWARE_DIR` (optional, default: `<DATA_DIR>/firmware`)
  Directory used for ESP32 firmware catalog (`catalog.json`) and served firmware files (`files/`).
  Container startup copies firmware template data from the image into this directory.
  `catalog.json` is overwritten from template on each start.
- `SETTINGS_MASTER_KEY` (required only for storing MQTT password from UI)
  Without this key, host/port/username can still be saved, but password save is blocked.
- `API_KEY` (optional)
  Protects write endpoints. Set this if the Hub UI/API should require authentication for changes.
- `PUBLIC_BASE_URL` (optional)
  Use when the app is served under a sub-path (for example `/mqtt-ir-module/`) behind a reverse proxy.
- `PUBLIC_API_KEY` (optional, not recommended for public deployments)
  Exposes a write key to the browser. Prefer reverse-proxy header injection instead.
- `DEBUG` (optional, default: `false`)
  Enables debug behavior and additional diagnostics.

## Generate SETTINGS_MASTER_KEY

Use one of these commands to generate a strong random key:

```bash
openssl rand -base64 32
```

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Store it as an environment variable and keep it stable. Changing it later prevents decrypting already stored MQTT passwords.

MQTT settings for Hub are configured in UI and stored in DB:

- `mqtt_host`
- `mqtt_port`
- `mqtt_username`
- `mqtt_password` (encrypted)
- `mqtt_instance`
- `homeassistant_enabled`

## Defaults in image

- `START_MODE=hub`
- `LOCAL_AGENT_ENABLED=false`

`LOCAL_AGENT_ENABLED=false` means no integrated local IR agent is registered.

## Notes

- This image can run with or without MQTT configured.
- Pairing for external agents is manual from the Agents page (fixed 5-minute window).
- Agent offers are shown as pending and must be explicitly accepted from the UI.
- Accepted external MQTT agents can execute `send` and `learn` commands via MQTT command/response topics.
- ESP32 firmware files are served from `${DATA_DIR}/firmware/files` (default `/data/firmware/files`).
- Home Assistant integration is available only in hub role and only when enabled in settings.
- If you do not mount a volume for `DATA_DIR`, settings/database are lost when the container is recreated.
