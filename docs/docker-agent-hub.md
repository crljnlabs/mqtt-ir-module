# Docker Mode: `ir-agent-hub`

This mode runs Hub + integrated local IR agent in one container.

## Build

```bash
docker build --target ir-agent-hub -t mqtt-ir-agent-hub:latest .
```

## Run

```bash
docker run --rm -p 8080:80 \
  --device /dev/lirc0:/dev/lirc0 \
  --device /dev/lirc1:/dev/lirc1 \
  -e DATA_DIR=/data \
  -e SETTINGS_MASTER_KEY=change-me \
  -v ir_hub_data:/data \
  mqtt-ir-agent-hub:latest
```

## Environment reference

- `IR_RX_DEVICE` / `IR_TX_DEVICE` (optional, defaults: `/dev/lirc0` and `/dev/lirc1`)
  Use these when your host exposes different device paths. Values must match the mapped container device paths.
- `IR_WIDEBAND` (optional, default: `false`)
  Enable only if your receiver requires wideband mode.
- `DATA_DIR` (optional, default: `/data`)
  Use only if you want a different internal path. For persistence, mount a volume to this path.
- `FIRMWARE_DIR` (optional, default: `<DATA_DIR>/firmware`)
  Directory used for ESP32 firmware catalog (`catalog.json`) and served firmware files (`files/`).
  Container startup copies firmware template data from the image into this directory.
  `catalog.json` is overwritten from template on each start.
- `SETTINGS_MASTER_KEY` (required only for storing MQTT password from UI)
  Without this key, host/port/username can still be saved, but password save is blocked.
- `API_KEY` (optional)
  Protects write endpoints. Set this if the Hub UI/API should require authentication for changes.
- `PUBLIC_BASE_URL` (optional)
  Use when served behind reverse proxy sub-path (for example `/mqtt-ir-module/`).
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

MQTT settings for Hub are configured in UI and stored in DB (same as `ir-hub`).

## Defaults in image

- `START_MODE=hub`
- `LOCAL_AGENT_ENABLED=true`

`LOCAL_AGENT_ENABLED=true` forces local integrated agent registration in Hub mode.

## Notes

- Internal local agent does not require MQTT to execute IR.
- External MQTT agents can still be paired and used in parallel.
- Accepted external MQTT agents execute `send` and `learn` via MQTT command/response topics.
- External agent pairing uses a fixed 5-minute pairing window with explicit accept in the Hub UI.
- `hub_is_agent` is treated as read-only in UI/API and controlled by `LOCAL_AGENT_ENABLED`.
- If you do not mount a volume for `DATA_DIR`, settings/database are lost when the container is recreated.
