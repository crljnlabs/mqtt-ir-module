# Developer Guide

## Architecture

The system has three deployment targets built from a single Dockerfile:

| Target | Role |
| --- | --- |
| `ir-hub` | Hub only: browser UI, REST API, firmware catalog, no local IR hardware |
| `ir-agent-hub` | Hub + integrated local IR agent: same as above but with direct LIRC access on the host |
| `ir-agent` | Standalone agent: MQTT-only, no UI, no HTTP API, IR hardware via LIRC |

**Hub** manages remotes, buttons, and signal storage. It communicates with **agents** either directly (local agent via shared process state) or via MQTT (external agents). **ESP32** clients are a special agent type that pair over MQTT and receive OTA updates from the Hub catalog.

MQTT topology:
- Agents publish state and logs to `ir/agents/<agent_id>/...`
- Hub publishes commands to `ir/agents/<agent_id>/cmd/...`
- Responses go to `ir/hubs/<hub_id>/agents/<agent_id>/resp/<request_id>`
- Pairing uses `ir/pairing/open` and `ir/pairing/offer`

## Repository layout

```
backend/            FastAPI application (hub + agent logic, IR capture/send)
  API.md            REST API reference
  helper/           Environment parsing, settings storage, utilities
  ...

frontend/           React + Vite UI
  README.md         Vite/React dev setup (boilerplate)
  src/pages/        One file per page (Router.jsx defines routes)

esp-agent/          ESP32 PlatformIO project
  src/              C++ firmware source
  VERSION           Current firmware version (single source of truth)
  build_and_publish.sh  Build + publish script

docs/
  DEVELOPER_README.md   This file
  deployment/       Docker mode guides and env var reference
  hardware/         Raspberry Pi wiring and LIRC setup
  esp32/            ESP32 firmware management and changelog
  ui/               UI page guide
  dev/tasks/        AI-assisted implementation specs (historical)

brain/
  GLOBAL_RULES.md   Project-wide coding standards (not tracked in git)
```

## API reference

Full endpoint reference: [../backend/API.md](../backend/API.md)

Interactive Swagger UI at runtime: `/api/docs`

## Coding rules

[brain/GLOBAL_RULES.md](../../brain/GLOBAL_RULES.md) — coding standards, architecture rules, commit process, firmware changelog requirements.

## Firmware development

1. Edit firmware in `esp-agent/src/`.
2. Bump version in `esp-agent/VERSION`.
3. Build and publish: `cd esp-agent && ./build_and_publish.sh`
4. Record flash/RAM stats in [esp32/FIRMWARE_CHANGELOG.md](esp32/FIRMWARE_CHANGELOG.md) before committing.

Full guide: [esp32/firmware-management.md](esp32/firmware-management.md)

## Implementation specs

[dev/tasks/](dev/tasks/) — detailed task specs used during AI-assisted development phases. These are historical planning documents, not active requirements.
