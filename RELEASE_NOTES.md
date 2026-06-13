# mqtt-ir-module — Release v1.0.0

First stable release.

---

## Overview

mqtt-ir-module is a self-hosted IR hub that captures, stores, and sends IR remote signals. It runs in Docker and communicates with IR hardware agents over MQTT or a direct local interface.

---

## Deployment

Three Docker images are published to Docker Hub under `devcorlijoni/`:

| Image | Purpose |
| --- | --- |
| `devcorlijoni/ir-agent-hub` | Hub + integrated IR agent on the same host (Raspberry Pi with LIRC) |
| `devcorlijoni/ir-hub` | Hub only — no local IR hardware required |
| `devcorlijoni/ir-agent` | Standalone MQTT IR agent — no UI, pairs with a remote Hub |

Multi-arch images (`linux/amd64`, `linux/arm64`) — Docker pulls the correct variant automatically.

```yaml
services:
  mqtt-ir-module:
    image: devcorlijoni/ir-agent-hub:latest
    restart: unless-stopped
    devices:
      - "/dev/lirc0:/dev/lirc0"
      - "/dev/lirc1:/dev/lirc1"
    volumes:
      - "./data:/data"
    environment:
      - SETTINGS_MASTER_KEY=change-me
    ports:
      - "8000:80"
```

Full environment variable reference: [docs/deployment/docker-setup.md](docs/deployment/docker-setup.md)

---

## Core features

### Remotes and buttons

- Create remotes with name, icon (MDI), carrier frequency, and duty cycle
- Assign remotes to specific IR agents
- Buttons support both press and hold signals

### IR learning wizard

Guided capture flow directly in the browser:

- **Add buttons** — extend an existing remote
- **Re-learn remote** — replace all buttons (with confirmation)
- Captures raw pulse/space timing via `ir-ctl`
- Configurable per-capture: number of takes, timeout, hold timing

### IR sending

- Send press or hold commands per button
- Sending is routed to the agent assigned to the remote

### Marketplace

Built-in IR remote database synced from a GitHub-hosted `.ir` file index:

- Search by brand, category, or name
- One-click import of pre-captured remotes
- Background sync with efficient change detection (no per-file DNS lookups)

---

## Agents

### Raspberry Pi agent (LIRC)

- Runs as `ir-agent` or integrated in `ir-agent-hub`
- Communicates via LIRC (`ir-ctl`) for RX and TX
- Configurable RX/TX device paths and wideband mode

### ESP32 agent

Custom PlatformIO firmware (`esp-agent/`):

- Pairs with the Hub over MQTT
- IR RX/TX via configurable GPIO pins (default: RX=34, TX=4)
- Pin reconfiguration from Hub UI without reflash
- SHA-256 verified OTA updates triggered from the Hub
- Browser-based initial USB flash via [ESP Web Tools](https://esphome.github.io/esp-web-tools/) (HTTPS or localhost)
- Boot diagnostics and runtime state reported to Hub (heap, reset reason, crash flag)

**Firmware v1.0.0** — Flash: 90.4% (1,184,793 bytes) · RAM: 15.2% (49,664 bytes)

---

## MQTT and Home Assistant

- Hub and agents communicate over standard MQTT topics (`ir/agents/<id>/...`)
- MQTT connection settings stored encrypted in the database (`SETTINGS_MASTER_KEY` required for password storage)
- Home Assistant MQTT discovery: buttons are published as HA entities automatically when enabled in settings

---

## Logs

- Per-agent and global log stream
- Filterable by level, category, source, and time range
- Live tail via WebSocket
- Configurable retention (default: 7 days)

---

## Security and access control

- Optional API key for all write endpoints (`API_KEY`)
- Sub-path hosting behind a reverse proxy (`PUBLIC_BASE_URL`)
- Encrypted sensitive settings at rest

---

## Links

- [Deployment guide](docs/deployment/docker-setup.md)
- [ESP32 firmware guide](docs/esp32/firmware-management.md)
- [Firmware changelog](docs/esp32/FIRMWARE_CHANGELOG.md)
- [API reference](backend/API.md)
- [UI guide](docs/ui/website.md)