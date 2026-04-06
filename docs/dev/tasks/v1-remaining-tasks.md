# v1 Remaining Tasks

**Context:**
- Three Docker targets exist and work: `ir-hub`, `ir-agent-hub`, `ir-agent`
- Hub owns the SQLite DB; agents are stateless regarding code library
- Remotes are hard-bound to one agent (`assigned_agent_id`)
- MQTT federation is implemented; `LocalAgent` works without a broker
- ESP32 firmware: custom PlatformIO/C++ (not ESPHome) — complete and working
- Pairing, send, learn, agent registry, settings with encrypted MQTT password — all done

---

## MIDDLE — Important, but not v1 blockers

The system is releasable without these. However, the two schema additions (M1, M2) are cheapest
to include before v1 — adding new tables post-release requires migration scripts for existing
deployments.

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
