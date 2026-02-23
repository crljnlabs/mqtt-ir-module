# mqtt-ir-module API

FastAPI exposes interactive Swagger UI at:
- `GET /api/docs`
- OpenAPI schema: `GET /api/openapi.json`

All endpoints below are under `/api`. If you host under a base path, the same endpoints are also available under `<PUBLIC_BASE_URL>/api`.

## Authentication

If `API_KEY` environment variable is set, write requests must include header:

`X-API-Key: <API_KEY>`

Read-only endpoints do not require the header.

## Data Model (DB)

- **Remote**: a physical remote control.
- **Button**: a named button for a remote.
- **Button signals**: raw pulse/space timing captured from `IR_RX_DEVICE` using `ir-ctl`.

Signals are stored as space-separated signed microseconds:

Example: `890 -906 871 -906 1781 -885 ...`

## Endpoints

### Health

`GET /api/health`

Response fields include:
- `ok`
- `ir_rx_device`
- `ir_tx_device`
- `ir_device` (legacy alias for RX)
- `debug`
- `learn_enabled`
- `learn_remote_id`
- `learn_remote_name`
- `learn_agent_id`

### Remotes CRUD

#### Create remote

`POST /api/remotes`

Body:
```json
{ "name": "TV Remote" }
```

#### List remotes

`GET /api/remotes`

#### Update remote (rename + optional transmit parameters)

`PUT /api/remotes/{remote_id}`

Body:
```json
{
  "name": "TV Remote",
  "carrier_hz": 38000,
  "duty_cycle": 33
}
```

#### Delete remote

`DELETE /api/remotes/{remote_id}`

### Buttons CRUD

#### List buttons for remote

`GET /api/remotes/{remote_id}/buttons`

Returns `has_press` / `has_hold` flags.

#### Rename button

`PUT /api/buttons/{button_id}`

Body:
```json
{ "name": "VOLUME_UP" }
```

#### Delete button

`DELETE /api/buttons/{button_id}`

### Learning (automated tool handling)

#### Start learning session

`POST /api/learn/start`

Body:
```json
{ "remote_id": 1, "extend": false }
```

- `extend=false`: deletes all existing buttons/signals for the remote (remote stays)
- `extend=true`: keeps existing buttons and continues with the next `BTN_XXXX` name

#### Capture press or hold

`POST /api/learn/capture`

Body (press):
```json
{
  "remote_id": 1,
  "mode": "press",
  "takes": 5,
  "timeout_ms": 3000,
  "overwrite": false,
  "button_name": null
}
```

- If `button_name` is omitted/null for `press`, the service creates `BTN_0001`, `BTN_0002`, ...
- `takes` controls how many separate presses you will perform.

Body (hold):
```json
{
  "remote_id": 1,
  "mode": "hold",
  "timeout_ms": 4000,
  "overwrite": false,
  "button_name": "VOLUME_UP"
}
```

- `hold` requires that the button already has a `press` captured.
- For `hold`, if `button_name` is omitted/null, the service uses the last captured button in the current session.

Errors:
- `408`: no signal within `timeout_ms`
- `409`: session/overwrite conflict

#### Stop learning

`POST /api/learn/stop`

#### Learning status snapshot (HTTP)

`GET /api/learn/status`

- Returns the current full learning status payload (same shape as WebSocket messages), including logs.
- Useful as a polling fallback when WebSocket delivery is unavailable.

#### Learning status (WebSocket)

`WS /api/learn/status/ws`

- Sends the current learning status payload on connect, then on every new log/status update.

### Sending

`POST /api/send`

Sending uses `IR_TX_DEVICE` under the hood.

Body (press):
```json
{ "button_id": 10, "mode": "press" }
```

Body (hold):
```json
{ "button_id": 10, "mode": "hold", "hold_ms": 800 }
```

Notes:
- Sending is disabled only for the agent that currently has an active learning session.
- `hold` uses the captured `hold_initial`, repeated `hold_repeat`, and the captured `hold_gap_us` timing.

### Hub runtime-control endpoints for MQTT agents

These endpoints exist only on the Hub backend.
They do **not** create an HTTP API on the agent.
Hub forwards these actions to agents over MQTT command/response topics.

#### Get debug flag

`GET /api/agents/{agent_id}/debug`

#### Set debug flag

`PUT /api/agents/{agent_id}/debug`

Body:

```json
{ "debug": true }
```

#### Get runtime config (ESP32)

`GET /api/agents/{agent_id}/runtime-config`

#### Update runtime config (ESP32)

`PUT /api/agents/{agent_id}/runtime-config`

Body:

```json
{
  "ir_rx_pin": 34,
  "ir_tx_pin": 4
}
```

Pin updates require agent reboot to fully apply.

#### Reboot runtime (ESP32)

`POST /api/agents/{agent_id}/reboot`

#### Trigger OTA (ESP32)

`POST /api/agents/{agent_id}/ota`

Body:

```json
{ "version": "0.1.0" }
```

If version is omitted, Hub uses latest installable catalog entry.

#### Cancel OTA (ESP32)

`POST /api/agents/{agent_id}/ota/cancel`

Cancels a running OTA update (or cancels a queued OTA before download starts).

#### Reset installation state

`POST /api/agents/{agent_id}/installation/reset`

Clears retained/local OTA installation status for this agent.

#### Delete agent with force

`DELETE /api/agents/{agent_id}?force=true`

Force delete skips waiting for unpair acknowledgment. Hub still attempts to dispatch unpair over MQTT and then removes local records immediately.

### Firmware catalog

#### List firmware entries

`GET /api/firmware?agent_type=esp32`

#### ESP Web Tools manifest

`GET /api/firmware/webtools-manifest?agent_type=esp32`

## Debug capture storage

- If `DEBUG=true`, every raw take is stored in the `captures` table.
- If `DEBUG=false`, the service clears the `captures` table on container start.

## Future extension: protocol decoding

The DB schema contains optional fields (`protocol`, `address`, `command_hex`, `decode_confidence`) reserved for a future decoder. These are currently not populated.
