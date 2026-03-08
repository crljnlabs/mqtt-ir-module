# v1 Remaining Tasks

**Context:**
- Three Docker targets exist and work: `ir-hub`, `ir-agent-hub`, `ir-agent`
- Hub owns the SQLite DB; agents are stateless regarding code library
- Remotes are hard-bound to one agent (`assigned_agent_id`)
- MQTT federation is implemented; `LocalAgent` works without a broker
- ESP32 firmware: custom PlatformIO/C++ (not ESPHome) — complete and working
- Pairing, send, learn, agent registry, settings with encrypted MQTT password — all done

---

## HIGHEST — Must be done before v1

These are either core UX breakages or decisions that become much harder to change post-release
(existing DB rows, retained MQTT topics already in the field, paired agents losing identity).

---

### H1 — Docker Agent: Stable Persistent Agent ID

**Problem:**
The standalone `ir-agent` Docker container derives its `agentId` from the MQTT `client_id`, which
is not guaranteed stable across restarts or broker reconnects. If the ID changes, all remotes
assigned to that agent become orphaned and must be re-paired manually.

**What to implement:**
- On first start: generate a UUID, write it to `/data/agent_id` (or a configurable path)
- On every subsequent start: read and reuse that file
- Pass this ID into `AgentRuntimeStateStore` and `AgentCommandHandler` instead of deriving from MQTT
- Declare the `/data/` directory as a named volume in the Docker Compose service

**Acceptance:** Restart the `ir-agent` container without removing its volume → `agentId` is
unchanged in the hub, paired remotes still work.

---

### H2 — Protocol Version Mismatch: Detect and Block Routing

**Problem:**
Hub and agent both carry `protocol_version` but there is no mismatch check. An incompatible agent
silently receives commands it cannot handle. Post-v1, fixing this requires touching retained MQTT
state topics already published by deployed agents.

**What to implement:**
- Compare the agent's `protocol_version` (from `ir/agents/{id}/state`) against the hub's
  `AGENT_PROTOCOL_VERSION` constant in `AgentRuntimeStateHub`
- On mismatch: write `status = "incompatible"` to the `agents` DB table
- In `AgentRegistry.resolve_agent_for_remote()`: refuse routing to incompatible agents,
  return error reason `"agent_incompatible"`
- Agent list UI (`AgentsPage`): show an "incompatible" badge alongside online/offline

**Schema note:** The `agents.status` column already exists with values `"online"/"offline"`.
Add `"incompatible"` as a valid value, or add a separate `incompatible BOOLEAN` column — decide
and lock in before v1 so no migration is needed later.

**Acceptance:** Connect an agent with a mismatched `protocol_version` → hub marks it incompatible,
UI shows the badge, send/learn return a clear error, no IR action is attempted.

---

### H3 — busy_learning: Block Send During Active Learn Session

**Problem:**
If a learn session is active and a send is triggered, the current behavior is undefined.
`busy.learning` is tracked internally but no explicit error is returned to the API caller.

**What to implement:**
- In `LocalAgent.send()` (and the agent-side command handler for `MqttAgent`): if a learn session
  is active, immediately return an error with reason `"busy_learning"` without attempting to send
- API propagates the reason to the frontend
- Frontend shows: "Cannot send while a learn session is active"

**Acceptance:** Start a learn session → trigger a send → receive `"busy_learning"` error,
no IR signal is emitted.

---

### H4 — Offline Agent: Block Action with Clear Error

**Problem:**
The agent's online/offline status is tracked, but the end-to-end error path from a blocked
send/learn to a user-visible message in the UI is unverified and likely incomplete.

**What to implement:**
- In `AgentRegistry.resolve_agent_for_remote()`: if the resolved agent's status is `"offline"`,
  return an error with reason `"agent_offline"` immediately — do not dispatch the action
- API must propagate this reason
- Frontend shows: "Agent [name] is offline" on the remote/button that triggered the action

**Acceptance:** Stop the agent process → try send from UI → "agent offline" error is shown
immediately, no timeout, no silent failure.

---

## MIDDLE — Important, but not v1 blockers

The system is releasable without these. However, the two schema additions (M1, M2) are cheapest
to include before v1 — adding new tables post-release requires migration scripts for existing
deployments.

---

### M1 — Action Events Table (Schema + Basic Recording)

**Why before v1:** Adding a table to an existing SQLite deployment needs a migration. Including it
in the initial schema costs nothing and provides a foundation for debugging from day one.

**Schema to add:**
```sql
CREATE TABLE IF NOT EXISTS action_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT    NOT NULL,
    type           TEXT    NOT NULL,  -- "send" | "learn_start" | "learn_complete" | "learn_fail"
    remote_id      INTEGER,
    button_id      INTEGER,
    agent_id       TEXT,
    correlation_id TEXT,
    result         TEXT,              -- "ok" | "error"
    reason         TEXT,              -- "agent_offline" | "busy_learning" | "timeout" | ...
    duration_ms    INTEGER,
    context        TEXT               -- JSON for extra data
);
```

**What to implement:**
- Add the table to DB schema initialization
- Record one event per send (result + reason)
- Record one event for learn start and one on completion/failure
- No UI required for v1 — just the data

**Acceptance:** Perform a send and a learn → query the DB → events exist with correct `type`,
`result`, and `reason`.

---

### M2 — Hub Log Store (DB Table, Level Setting, Retention)

**Why before v1:** Same as M1. The table is cheap to add now. Without it, agent logs only exist in
a 100-entry in-memory deque and are lost on restart — useless for production debugging.

**What to implement:**
- Add `hub_logs` table: `(id INTEGER PK AUTOINCREMENT, ts TEXT, level TEXT, source TEXT, message TEXT, context TEXT)`
- Add two settings keys: `log_level` (debug/info/warn/error, default: `info`) and
  `log_retention_days` (integer, default: `7`)
- Prune logs older than the retention window on startup and on a background interval
- Extend `AgentLogsPage` or add a tab to show hub-level logs with level filter

**Acceptance:** Hub generates log entries during pairing, send, and learn → entries appear in the
UI → entries older than the retention setting are removed on the next startup.

---

### M3 — Home Assistant: Inbound Command Routing

**Current state:** Hub publishes MQTT discovery payloads so HA knows about buttons (outbound only).
HA has no way to trigger the hub to actually send an IR code.

**What to implement:**
- Subscribe to `ir/ha/send` (or `{mqtt_instance}/ha/send` to namespace it)
- Expected payload: `{"remote_id": <int>, "button_id": <int>}` (or by name as a secondary option)
- On message: look up the IR code in the DB → resolve the assigned agent → send
- Record an action event (M1) if that table exists

**Acceptance:** Publish a test MQTT message to `ir/ha/send` with a valid remote/button → the
correct IR code is sent via the assigned agent.

---

### M4 — MQTT Chunking for Large IR Payloads

**Current state:** IR signals are transferred as single MQTT messages. Very long raw signals
(certain AC protocols) may exceed broker message size limits.

**What to implement:**
- Use the agent's `maxPayloadBytes` capability to decide whether chunking is needed
- Agent splits the learn result into chunks:
  `{transfer_id, chunk_index, chunk_count, chunk_data}` (base64-encode `chunk_data`)
- Hub collects all chunks by `transfer_id` with a timeout, reassembles, and stores the result
- If reassembly times out: record a `"learn_fail"` action event with reason `"chunk_timeout"`

**Acceptance:** Simulate a signal exceeding 1 KB → it arrives in multiple MQTT messages →
hub reassembles correctly → code is stored and sendable.

---

## LOW — Defer until after v1

Independent features or large separate efforts. Defer to keep the release scope manageable.

---

### L1 — ir-agent: Optional Local HTTP API

**What:** Thin HTTP server on the standalone `ir-agent` for local debugging without MQTT.

**Endpoints:** `GET /health`, `GET /status`, `POST /send`, `POST /learn/start`, `POST /learn/stop`

**Toggle:** `AGENT_HTTP_ENABLED=true` / `AGENT_HTTP_PORT` env vars.
Hub must never use this for routing — MQTT remains the only hub ↔ agent channel.

---

### L2 — ESP32 OTA: HTTPS with Certificate Validation

**Current state:** ESP32 OTA downloads firmware over plain HTTP. SHA-256 checksum is already
verified after download.

**What to implement:**
- Use `WiFiClientSecure` with an embedded CA or pinned server certificate
- Reject OTA if TLS handshake or certificate validation fails
- Plain HTTP: either block entirely or allow only behind an explicit build flag
- Add a TLS failure reason to the OTA status reported back to the hub

**Note:** Acceptable over a trusted LAN for v1. Prioritize before any public OTA endpoint exposure.

---

### L3 — ESPHome External Component

**Current state:** The ESP32 firmware is implemented as custom PlatformIO/C++ and is fully
functional. This task would be a parallel implementation for users who prefer ESPHome-based setups.

**What it would involve:**
- `components/ir_agent/` (C++ + ESPHome Python glue)
- `packages/ir_agent.yaml` (ESPHome package with substitutions)
- Must speak the identical MQTT contract as the current ESP32 firmware

**Note:** Significant standalone effort. Not needed for v1. Evaluate after initial release based
on user demand.
