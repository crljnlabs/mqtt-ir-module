# IR Hub + Agents – Codex-Ready Task List (Self-Contained)

This document is written so that **each task can be copied verbatim into Codex** as an implementation prompt.
Assumptions:

- Final deliverables are **three Docker build targets/images**:
  - `ir-hub` (Hub only, no IR hardware dependencies)
  - `ir-agent-hub` (Hub + integrated local agent; hub <-> integrated agent commuznications works **without** MQTT broker, but also over MQTT with external Brokers)
  - `ir-agent` (standalone agent for Raspberry Pi/Zero; MQTT)
- Externals:
  - External agents connect **only via MQTT**.
  - Home Assistant sends IR actions **to the Hub** (Hub routes to assigned agent).
- IR payload format: start with **raw IR** (as currently used), support **chunking** for large transfers.
- ESP32 agent later via **ESPHome external component** (1:1 contract as much as possible), with **OTA**.

---

## Global Architecture Rules (applies to all tasks)

1. **Hub owns the database** for remotes/codes/settings/logs.
2. Agents are **stateless regarding code library** (they may cache, but Hub is source of truth).
3. A Remote is **hard-bound to exactly one agent** (`assignedAgentId`).
4. If a Remote has `assignedAgentId=None`, the UI asks the user to choose an agent on first learn action and then sets it.
6. Hub must run:
   - with zero agents connected: UI works, send/learn disabled with clear errors
   - with integrated local agent only: works without MQTT broker
   - with MQTT enabled: can pair and control external agents

---

# TASKS
---



---

## TASK 06 — MQTT Transport in Hub (Connect, Subscribe, Publish)

**Objective**
Add MQTT client logic to Hub that:

- connects only when settings are present
- supports pairing and agent command routing
- tracks agent online/offline and capabilities

**Deliverables**

- Hub MQTT module that:
  - connects with stored settings
  - subscribes to pairing offers + agent events
  - publishes pairing requests/accepts + command messages

**Compatibility Handling**

- Every agent offer/status must include `protocolVersion`.
- If mismatch: mark agent as `incompatible` and block routing to it with clear error.

**Definition of Done**

- With MQTT enabled, Hub shows discovered agents and can send commands.
- With MQTT disabled, Hub still runs normally.

---

## TASK 07 — Pairing UX: “Start Pairing” + “Adopt Agent” Flow

**Objective**
Implement UI and backend endpoints to pair external agents without manually setting tokens.

**Flow**

1. User clicks “Start pairing (60s)” in UI.
2. Hub publishes `ir/pairing/request` with `{nonce, expiresAt, protocolVersion}`.
3. Unpaired agents publish `ir/pairing/offer` with `{agentId, capabilities, protocolVersion, agentSoftwareVersion}`.
4. UI lists offers.
5. User selects an offer and clicks “Adopt”.
6. Hub publishes `ir/pairing/accept/{agentId}`.
7. Agent persists `paired=true` and begins accepting commands.

**Deliverables**

- UI page: Agent Management
- Backend endpoints:
  - `POST /api/pairing/start`
  - `POST /api/pairing/adopt` (agentId)
  - `GET /api/agents` list with status/capabilities

**Definition of Done**

- Pairing works end-to-end with `ir-agent`.
- Paired agent persists across restarts.

---

## TASK 08 — Standalone `ir-agent` (Pi): MQTT Commands + Results + Busy/Learning

**Objective**
Implement the external agent process that connects to MQTT, pairs, executes IR actions, and publishes results.

**Deliverables**

- `ir-agent` runtime process that:
  - loads persistent `agentId`
  - connects to broker
  - supports pairing
  - subscribes to command topics for its `agentId`
  - publishes results/events including busy/learning errors

**Behavior**

- Remote is hard-bound to agent; hub routes accordingly.
- If agent is in learning mode and receives a send: return error `busy_learning`.
- Learning is started/stopped via hub commands only.

**Definition of Done**

- Hub can pair agent, learn via agent, store codes in hub DB, and send via agent.

---

## TASK 09 — Remote/Code Model: Hard Agent Binding + Default Assignment

**Objective**
Implement the data model and UI rules:

- Remote has `assignedAgentId` (nullable)
- On first learn for a remote with `assignedAgentId=None`, UI forces user to choose agent and then sets it
- Later learn/send always uses assigned agent
- If agent offline: show error

**Deliverables**

- DB schema for Remote `assignedAgentId`
- UI behavior:
  - remote settings page shows assigned agent
  - initial assignment flow
- Backend routing uses assigned agent id

**Definition of Done**

- No send/learn without assigned agent.
- Offline agent produces clear message and action is not attempted.

---

## TASK 10 — Hub Logging: Retention + Level + UI Viewer

**Objective**
Add a hub log store for debugging with configurable retention and level, viewable in UI.

**Deliverables**

- Settings:
  - `logLevel` (debug/info/warn/error)
  - `logRetentionDays` (integer)
- Log storage:
  - DB table recommended (timestamp, level, source, message, context JSON)
- UI page:
  - filter by level and time
  - display latest logs

**Definition of Done**

- Logs exist for pairing, send, learn, failures.
- Old logs are pruned according to retention.

---

## TASK 11 — Action Events (Send/Learn Audit Trail)

**Objective**
Create a structured event record for user actions so “why did this fail?” is easy to answer.

**Deliverables**

- DB table `action_events`:
  - `id`, `ts`, `type` (`send`, `learn_start`, `learn_chunk`, `learn_complete`)
  - `remoteId`, `buttonId` (nullable)
  - `agentId`
  - `correlationId`
  - `result`, `reason`, `durationMs` (nullable)
  - `context` JSON

**Definition of Done**

- Every send and learn produces at least one event entry with final result.

---

## TASK 12 — Raw IR Chunking (Agent→Hub for Learn)

**Objective**
Support large raw IR captures by chunking into multiple MQTT messages.

**Deliverables**

- Contract implemented according to `docs/mqtt-contract.md`
- Hub reassembles chunks and stores final raw code in DB
- Agent splits capture according to its `maxPayloadBytes`

**Implementation Steps**

1. Define encoding for chunk payload (base64 recommended for compactness).
2. Agent emits:
   - `transferId`, `chunkIndex`, `chunkCount`, `chunkData`
3. Hub collects by `transferId` with timeout.
4. On completion, hub validates and stores.

**Definition of Done**

- Learn works for long signals that exceed single MQTT message size.

---

## TASK 13 — Home Assistant Integration: HA → Hub → Agent Routing

**Objective**
Ensure Home Assistant publishes intent to Hub (remote/button/action), and Hub resolves to code and routes to assigned agent.

**Deliverables**

- MQTT topics for HA→Hub (or HTTP endpoint, but MQTT preferred):
  - `ir/ha/send` with payload `{remoteId, buttonId}` (or `{remoteName, buttonName}`)
- Hub handler:
  - look up code in DB
  - route to assigned agent
  - emit action events/logs

**Definition of Done**

- HA can trigger a stored code via Hub without direct agent access.

---

## TASK 14 — Optional: HTTP API for `ir-agent` (Pi) for Debug/Standalone

**Objective**
Add an optional HTTP server to `ir-agent` to:

- report health/status
- allow manual send/learn without MQTT (optional mode)
  This is optional and should not be required by Hub routing.

**Deliverables**

- `GET /health`, `GET /status`
- `POST /send`, `POST /learn/start`, `POST /learn/stop`
- Feature toggle via env: `AGENT_HTTP_ENABLED=true`, `AGENT_HTTP_PORT`

**Definition of Done**

- When enabled, endpoints work; when disabled, no HTTP server runs.

---

## TASK 15 — ESP32 Agent: ESPHome External Component + Package + OTA

**Objective**
Create an ESPHome-based agent template that speaks the same MQTT contract as `ir-agent`, as closely as practical, with OTA enabled.

**Deliverables**

- Separate repo (or subfolder) for ESPHome external component:
  - `components/ir_agent/*` (C++ + Python glue)
  - `packages/ir_agent.yaml` (ESPHome package with substitutions)
- Supports:
  - MQTT connect
  - Pairing offer/accept
  - Send raw IR (must work)
  - Learn raw IR (planned; may be v2 if needed)
  - Capabilities reflect send-only vs learn+send
- OTA enabled in package (`ota:`)

**Definition of Done**

- Flash ESP32 with template, pair with Hub, send works.
- OTA update works and does not change agent identity (store `agentId` in NVS).

---

## TASK 16 — Compatibility Mismatch UX + Future Update Hooks

**Objective**
If `protocolVersion` mismatch occurs, Hub must mark agent incompatible and show clear UI guidance. Create hooks for future OTA/container update automation without implementing it now.

**Deliverables**

- Agent list shows status:
  - online/offline
  - compatible/incompatible
  - software version
- Hub blocks routing to incompatible agents.
- Documentation in `docs/updates.md` describing future update options:
  - ESP: OTA
  - Containers: pull+restart (manual/optional automation later)

**Definition of Done**

- Mismatch is visible, actionable, and does not break the Hub.

---

# Suggested Execution Order (Optimized for Continuous Testing)

1. TASK 01 (contract doc)
2. TASK 02 (hub agent abstraction + local agent)
3. TASK 03 (persistent agent id)
4. TASK 04 (docker targets)
5. TASK 05 (settings + encryption-at-rest)
6. TASK 06 (hub mqtt transport)
7. TASK 07 (pairing UI)
8. TASK 08 (pi agent mqtt runtime)
9. TASK 09 (remote binding rules)
10. TASK 10 (hub logs)
11. TASK 11 (action events)
12. TASK 12 (chunking)
13. TASK 13 (home assistant → hub routing)
14. TASK 14 (optional agent http)
15. TASK 15 (esphome external component + ota)
16. TASK 16 (compatibility UX + update hooks)

---

# Notes for Codex Prompts

When you paste a task into Codex, include:

- “Work on branch `fix-frontend-bugs`”
- “Follow `docs/mqtt-contract.md`”
- “Do not introduce topic versioning”
- “Remote is hard-bound to one agent”
- “Hub must run without MQTT broker when using `ir-agent-hub`”
