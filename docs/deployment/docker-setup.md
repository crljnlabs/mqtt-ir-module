# Docker setup: environment variable reference

Complete reference for all environment variables supported by the backend. Applies to all three Docker images (`ir-agent-hub`, `ir-hub`, `ir-agent`). Not every variable is relevant for every mode — see the mode-specific guides for what is required.

## Pre-built Docker Hub images

Three images are published to Docker Hub under `devcorlijoni/`:

| Image | Purpose |
| --- | --- |
| `devcorlijoni/ir-agent-hub` | Hub + integrated local IR agent (requires IR hardware on host) |
| `devcorlijoni/ir-hub` | Hub only — no local IR hardware required |
| `devcorlijoni/ir-agent` | Standalone MQTT agent — no Hub UI, no HTTP API |

### Available tags

| Tag | When published |
| --- | --- |
| `latest` | On every version-tagged commit (points to the latest release) |
| `v1.0.0` *(example)* | On every version-tagged commit |
| `main` | On every build from the `main` branch |
| `dev` | On every build from any non-`main` branch |
| `main-amd64` / `main-arm64` | Per-architecture variants of the `main` build |
| `dev-amd64` / `dev-arm64` | Per-architecture variants of the `dev` build |

Multi-arch manifests (`main`, `dev`, `latest`, version tags) cover both `linux/amd64` and `linux/arm64`. Docker pulls the correct variant automatically.

## IR device

| Variable | Default | Description |
| --- | --- | --- |
| `IR_RX_DEVICE` | `/dev/lirc0` | Device path for IR receiving. |
| `IR_TX_DEVICE` | `/dev/lirc1` | Device path for IR transmitting. Set to the same device as `IR_RX_DEVICE` if RX and TX share one device. |
| `IR_WIDEBAND` | `false` | Adds `--wideband` to `ir-ctl` receive calls. Enable only if your receiver requires it. |

## Storage

| Variable | Default | Description |
| --- | --- | --- |
| `DATA_DIR` | `/data` | Root directory for all persistent data (SQLite DB, agent state, firmware). Mount a volume here. |
| `FIRMWARE_DIR` | `<DATA_DIR>/firmware` | Directory for the ESP32 firmware catalog and binary files. Seeded from image template on startup. `catalog.json` is overwritten from template on each container start. |

## Authentication

| Variable | Default | Description |
| --- | --- | --- |
| `API_KEY` | empty | If set, all write endpoints require `X-API-Key: <API_KEY>` header. Read-only endpoints are not protected. |
| `PUBLIC_API_KEY` | empty | If set, injected into the frontend runtime config so the browser sends it automatically. Exposes the key to any client that can load the UI. Prefer reverse-proxy header injection instead. |
| `SETTINGS_MASTER_KEY` | empty | Encryption key for sensitive settings stored in the database (for example the MQTT password saved via the Hub UI). Without this key, MQTT password storage is blocked. Generate once and keep stable — changing it makes existing encrypted values unreadable. |

Generate a key:
```bash
openssl rand -base64 32
```

## MQTT (agent mode only)

These variables configure the MQTT broker connection for the `ir-agent` Docker target. In Hub modes, MQTT settings are configured in the UI and stored encrypted in the database.

| Variable | Default | Description |
| --- | --- | --- |
| `MQTT_HOST` | empty | Broker hostname or IP. Required for `ir-agent` mode. |
| `MQTT_PORT` | empty (uses broker default `1883`) | Broker port, valid range 1–65535. |
| `MQTT_USERNAME` | empty | Broker username. |
| `MQTT_PASSWORD` | empty | Broker password. |

## UI and routing

| Variable | Default | Description |
| --- | --- | --- |
| `PUBLIC_BASE_URL` | `/` | Base path for sub-path hosting behind a reverse proxy (example: `/mqtt-ir-module/`). With or without trailing slash is accepted. |
| `DEBUG` | `false` | Enables debug behavior and stores raw capture sessions to disk. |

## Agent behavior

| Variable | Default | Description |
| --- | --- | --- |
| `LOCAL_AGENT_ENABLED` | unset (auto) | In Hub modes, forces the integrated local agent on (`true`) or off (`false`). When unset, the image default applies (`ir-agent-hub` defaults to `true`, `ir-hub` defaults to `false`). |
| `AGENT_PAIRING_RESET` | `false` | When `true`, clears stored pairing binding on startup. Useful for re-pairing after a Hub reset. |

## Agent ID persistence

The Hub's integrated local agent persists its agent ID at `${DATA_DIR}/agent/agent_id`. Mount a volume at `DATA_DIR` to retain the same agent ID across container recreations.

## Example docker-compose

```yaml
services:
  mqtt-ir-module:
    image: devcorlijoni/ir-agent-hub:latest
    container_name: mqtt-ir-module
    restart: unless-stopped

    devices:
      - "/dev/lirc0:/dev/lirc0"
      - "/dev/lirc1:/dev/lirc1"

    volumes:
      - "./data:/data"

    environment:
      - IR_RX_DEVICE=/dev/lirc0
      - IR_TX_DEVICE=/dev/lirc1
      - DATA_DIR=/data
      - SETTINGS_MASTER_KEY=change-me
      - DEBUG=false
      - IR_WIDEBAND=false
      - PUBLIC_BASE_URL=/mqtt-ir-module/

      # Optional:
      # - API_KEY=change-me
      # - PUBLIC_API_KEY=change-me

    ports:
      - "8000:80"
```

Open:
- UI: `http://<host>:8000/mqtt-ir-module/`
- API: `http://<host>:8000/mqtt-ir-module/api/...`
