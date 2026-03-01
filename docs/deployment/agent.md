# Docker Mode: `ir-agent`

This mode runs standalone agent runtime as a background MQTT process (no frontend and no HTTP API).

## Build

```bash
docker build --target ir-agent -t mqtt-ir-agent:latest .
```

## Run

```bash
docker run --rm \
  --device /dev/lirc0:/dev/lirc0 \
  --device /dev/lirc1:/dev/lirc1 \
  -e MQTT_HOST=broker.local \
  -e MQTT_PORT=1883 \
  -e MQTT_USERNAME=user \
  -e MQTT_PASSWORD=pass \
  mqtt-ir-agent:latest
```

## Environment reference

- `MQTT_HOST` (required)
  Broker hostname or IP reachable from inside the container (example: `192.168.215.2`).
  Do not wrap values with extra quotes in Compose list-style env lines.
- `MQTT_PORT` (optional, default: `1883`)
  Broker port. Set this only when broker does not use `1883`.
- `MQTT_USERNAME` / `MQTT_PASSWORD` (optional)
  Set when broker requires authentication.
- `AGENT_PAIRING_RESET` (optional, default: `false`)
  Set `true` to clear stored pairing binding on startup.
- `IR_RX_DEVICE` / `IR_TX_DEVICE` (optional, defaults: `/dev/lirc0` and `/dev/lirc1`)
  Use when your host exposes different device paths. Values must match mapped container device paths.
- `IR_WIDEBAND` (optional, default: `false`)
  Enable only if your receiver requires wideband mode.
- `DEBUG` (optional, default: `false`)
  Enables debug behavior and additional diagnostics.

## Defaults in image

- `START_MODE=agent`

## Runtime behavior

- Agent MQTT identity is derived from jmqtt client identity (stable deterministic client id generation).
- When unbound, agent keeps listening on `ir/pairing/open` until it is accepted by a Hub.
- Runtime state (pairing/debug/runtime metadata) is synchronized via retained MQTT topic `ir/agents/<agent_id>/state` (no local filesystem persistence in agent mode).
- Agent always listens for `ir/pairing/unpair/<agent_id>`. On unpair command, it clears binding, publishes an ack, and returns to pairable mode.
- While bound, agent executes Hub commands received on:
  - `ir/agents/<agent_id>/cmd/send`
  - `ir/agents/<agent_id>/cmd/learn/start`
  - `ir/agents/<agent_id>/cmd/learn/capture`
  - `ir/agents/<agent_id>/cmd/learn/stop`
  - `ir/agents/<agent_id>/cmd/runtime/debug/get`
  - `ir/agents/<agent_id>/cmd/runtime/debug/set`
  - `ir/agents/<agent_id>/cmd/runtime/config/get`
- Command results are published back to Hub on:
  - `ir/hubs/<hub_id>/agents/<agent_id>/resp/<request_id>`

## Notes

- This image does not host the Hub UI.
- This image does not expose an HTTP API.
- Hub pairing is initiated from Hub side (Agents page).
- MQTT connection settings for this mode are provided by env (`MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`).

## Troubleshooting

- `MQTT start failed: [Errno -2] Name or service not known`
  - `MQTT_HOST` is invalid or not resolvable from the container.
  - In Compose, prefer map-style env definitions:
    - `MQTT_HOST: 192.168.215.2`
  - If list-style is used, avoid embedded quotes:
    - `- MQTT_HOST=192.168.215.2`
