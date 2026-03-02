# mqtt-ir-module

A system for learning and transmitting infrared (IR) remote codes over a local network. The **Hub** provides a browser UI and REST API. **Agents** are IR hardware nodes — either a Raspberry Pi with LIRC hardware or an ESP32 WiFi client — that receive and send IR signals on command.

## Choose your deployment mode

| Mode | Use case | Guide |
| --- | --- | --- |
| **Hub + local agent** | Hub UI + IR hardware on the same host (most common single-device setup) | [docs/deployment/agent-hub.md](docs/deployment/agent-hub.md) |
| **Hub only** | Hub UI without local IR hardware; external agents connect via MQTT | [docs/deployment/hub.md](docs/deployment/hub.md) |
| **Standalone agent** | No UI, MQTT-only IR agent for a Raspberry Pi | [docs/deployment/agent.md](docs/deployment/agent.md) |

Environment variable reference for all modes: [docs/deployment/docker-setup.md](docs/deployment/docker-setup.md)

## ESP32 client

An ESP32 with an IR LED and receiver can act as a WiFi-based IR agent. It pairs with the Hub over MQTT and supports OTA firmware updates from the Hub UI. No USB cable required after initial flash.

Guide: [docs/esp32/firmware-management.md](docs/esp32/firmware-management.md)

## Raspberry Pi hardware setup

LIRC kernel overlay wiring, device detection, and Docker device mapping:
[docs/hardware/](docs/hardware/)

## Reverse proxy

Hosting under a sub-path or injecting `X-API-Key` via proxy:
[docs/deployment/reverse-proxy.md](docs/deployment/reverse-proxy.md)

## UI guide

Pages, learning wizard, and agent management:
[docs/ui/website.md](docs/ui/website.md)

## API reference

Swagger UI: `/api/docs`
OpenAPI schema: `/api/openapi.json`
Full endpoint reference: [backend/API.md](backend/API.md)

## For developers

Architecture, repository layout, coding rules, and implementation specs:
[docs/DEVELOPER_README.md](docs/DEVELOPER_README.md)
