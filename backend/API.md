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

---

## Status

### Health check

`GET /api/health`

Response:
```json
{ "ok": true }
```

### Electronics status

`GET /api/status/electronics`

Response:
```json
{
  "ir_device": "/dev/lirc0",
  "ir_rx_device": "/dev/lirc0",
  "ir_tx_device": "/dev/lirc1",
  "debug": false
}
```

### Learning status (HTTP)

`GET /api/status/learning`

Response:
```json
{
  "learn_enabled": false,
  "learn_remote_id": null,
  "learn_remote_name": null,
  "learn_agent_id": null
}
```

### MQTT status

`GET /api/status/mqtt`

Response:
```json
{
  "configured": true,
  "connected": true,
  "role": "hub",
  "node_id": "...",
  "base_topic": "ir",
  "app_name": "mqtt-ir-module",
  "client_id": "...",
  "last_error": null,
  "homeassistant_enabled": false,
  "homeassistant_thread_running": false
}
```

### Pairing status

`GET /api/status/pairing`

Response:
```json
{
  "running": true,
  "open": true,
  "session_id": "abc123",
  "expires_at": 1740000000.0
}
```

`expires_at` is a Unix timestamp, only present when `open` is true.

---

## Remotes CRUD

### Create remote

`POST /api/remotes`

Body:
```json
{
  "name": "TV Remote",
  "icon": "mdi:television"
}
```

`icon` is optional (MDI icon key).

### List remotes

`GET /api/remotes`

### Update remote

`PUT /api/remotes/{remote_id}`

Body:
```json
{
  "name": "TV Remote",
  "icon": "mdi:television",
  "assigned_agent_id": "agent-uuid",
  "carrier_hz": 38000,
  "duty_cycle": 33
}
```

All fields except `name` are optional. `assigned_agent_id` controls which agent handles IR for this remote.

### Delete remote

`DELETE /api/remotes/{remote_id}`

---

## Buttons CRUD

### List buttons for remote

`GET /api/remotes/{remote_id}/buttons`

Returns `has_press` / `has_hold` flags per button.

### Update button

`PUT /api/buttons/{button_id}`

Body:
```json
{
  "name": "VOLUME_UP",
  "icon": "mdi:volume-plus"
}
```

`icon` is optional (MDI icon key).

### Delete button

`DELETE /api/buttons/{button_id}`

---

## Learning

### Start learning session

`POST /api/learn/start`

Body:
```json
{ "remote_id": 1, "extend": false }
```

- `extend=false`: deletes all existing buttons/signals for the remote (remote stays)
- `extend=true`: keeps existing buttons and continues with the next `BTN_XXXX` name

### Capture press or hold

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

### Stop learning

`POST /api/learn/stop`

### Learning status snapshot (HTTP)

`GET /api/learn/status`

Returns the current full learning status payload (same shape as WebSocket messages), including logs.
Useful as a polling fallback when WebSocket delivery is unavailable.

### Learning status (WebSocket)

`WS /api/learn/status/ws`

Sends the current learning status payload on connect, then on every new log/status update.

---

## Sending

`POST /api/send`

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

---

## Agents

### List agents

`GET /api/agents`

Returns an array of agent payloads (see GET /api/agents/{agent_id} for the shape).

### Get agent

`GET /api/agents/{agent_id}`

Response:
```json
{
  "agent_id": "string",
  "name": "Living Room ESP32",
  "icon": "mdi:remote",
  "transport": "mqtt",
  "status": "online",
  "can_send": true,
  "can_learn": true,
  "sw_version": "0.0.6",
  "agent_topic": "ir/agents/abc123",
  "configuration_url": null,
  "pending": false,
  "pairing_session_id": null,
  "last_seen": 1740000000.0,
  "created_at": 1739000000.0,
  "updated_at": 1740000000.0,
  "capabilities": {
    "can_send": true,
    "can_learn": true,
    "sw_version": "0.0.6",
    "agent_type": "esp32",
    "protocol_version": "1",
    "ota_supported": true
  },
  "runtime": {
    "agent_type": "esp32",
    "protocol_version": "1",
    "sw_version": "0.0.6",
    "can_send": true,
    "can_learn": true,
    "ota_supported": true,
    "reboot_required": false,
    "last_reset_reason": "PowerOn",
    "last_reset_code": null,
    "last_reset_crash": false,
    "free_heap": 180000,
    "ir_rx_pin": 34,
    "ir_tx_pin": 4,
    "power_mode": "",
    "runtime_commands": ["send", "learn"],
    "state_seen_at": 1740000000.0,
    "state_updated_at": 1740000000.0
  },
  "ota": {
    "supported": true,
    "agent_type": "esp32",
    "current_version": "0.0.6",
    "latest_version": "0.0.6",
    "update_available": false,
    "reboot_required": false
  },
  "installation": {
    "status": "idle",
    "in_progress": false,
    "progress_pct": null,
    "target_version": "",
    "current_version": "0.0.6",
    "message": "",
    "error_code": "",
    "updated_at": null
  }
}
```

`transport` is `"local"` for the integrated agent in `ir-agent-hub` mode, `"mqtt"` for external agents.
`status` is `"online"`, `"offline"`, or `"pending"` (during pairing, before accept).

### Update agent

`PUT /api/agents/{agent_id}`

Body (all fields optional):
```json
{
  "name": "Living Room ESP32",
  "icon": "mdi:remote",
  "configuration_url": "http://homeassistant.local/device/abc"
}
```

Response: full agent payload (same as GET).

### Get agent logs

`GET /api/agents/{agent_id}/logs?limit=100`

Response:
```json
{
  "agent_id": "string",
  "items": [
    {
      "ts": 1740000000.0,
      "level": "info",
      "category": "transport",
      "message": "MQTT connected",
      "error_code": null,
      "meta": null
    }
  ]
}
```

### Agent logs (WebSocket)

`WS /api/agents/{agent_id}/logs/ws`

Streams new log entries as they arrive. Sends current snapshot on connect.

### Delete agent

`DELETE /api/agents/{agent_id}?force=false`

- `force=false` (default): attempts clean unpair via MQTT before removing.
- `force=true`: removes local records immediately, still dispatches unpair over MQTT but does not wait for ack.

---

## Pairing

Pairing registers a new external MQTT agent with the Hub.

### Open pairing window

`POST /api/pairing/open`

Body (optional):
```json
{ "duration_seconds": 300 }
```

`duration_seconds` is accepted (range 10–3600) but currently ignored; the server always uses its configured default window duration.

Response:
```json
{
  "running": true,
  "open": true,
  "session_id": "abc123",
  "expires_at": 1740000300.0
}
```

### Close pairing window

`POST /api/pairing/close`

Response: same shape as `/api/pairing/open` response, with `open: false`.

### Accept pairing offer

`POST /api/pairing/accept/{agent_id}`

Accepts a pending pairing offer from an agent that announced itself during the open window. Returns the newly created agent record.

---

## Hub runtime-control endpoints for MQTT agents

These endpoints exist only on the Hub backend.
They do **not** create an HTTP API on the agent.
Hub forwards these actions to agents over MQTT command/response topics.

### Get debug flag

`GET /api/agents/{agent_id}/debug`

### Set debug flag

`PUT /api/agents/{agent_id}/debug`

Body:

```json
{ "debug": true }
```

### Get runtime config (ESP32)

`GET /api/agents/{agent_id}/runtime-config`

### Update runtime config (ESP32)

`PUT /api/agents/{agent_id}/runtime-config`

Body:

```json
{
  "ir_rx_pin": 34,
  "ir_tx_pin": 4
}
```

Pin updates require agent reboot to fully apply.

### Reboot agent (ESP32)

`POST /api/agents/{agent_id}/reboot`

### Trigger OTA (ESP32)

`POST /api/agents/{agent_id}/ota`

Body:

```json
{ "version": "0.0.6" }
```

If version is omitted, Hub uses latest installable catalog entry.

### Cancel OTA (ESP32)

`POST /api/agents/{agent_id}/ota/cancel`

Cancels a running OTA update (or cancels a queued OTA before download starts).

### Reset installation state

`POST /api/agents/{agent_id}/installation/reset`

Clears retained/local OTA installation status for this agent.

---

## Firmware catalog

### List firmware entries

`GET /api/firmware?agent_type=esp32`

### ESP Web Tools manifest

`GET /api/firmware/webtools-manifest?agent_type=esp32`

---

## Debug capture storage

- If `DEBUG=true`, every raw take is stored in the `captures` table.
- If `DEBUG=false`, the service clears the `captures` table on container start.

## Future extension: protocol decoding

The DB schema contains optional fields (`protocol`, `address`, `command_hex`, `decode_confidence`) reserved for a future decoder. These are currently not populated.
