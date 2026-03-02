# IR Hub + Agents – Step-by-Step Umsetzungsplan (ein Repo, mehrere Build-Targets)

Stand: Planung basierend auf Branch `fix-frontend-bugs` des Repos `mqtt-ir-module`.

Ziele (final):
- **Ein Codebase**, aber 3 Docker Build-Targets/Images:
  - `ir-hub` (Hub ohne IR-Hardware)
  - `ir-agent-hub` (Hub + integrierter Local-Agent, funktioniert ohne MQTT-Broker)
  - `ir-agent` (reiner Agent für Raspberry Pi/Zero etc., MQTT + optional HTTP)
- **Multi-Agent**: Externe Agents werden **nur via MQTT** angebunden.
- **Home Assistant** sendet **an den Hub** (Hub routet an den Remote-zugeordneten Agent).
- **Raw-IR** bleibt zuerst so wie jetzt (ir-ctl/raw), **Chunking** für große Payloads.
- **ESP32 Agent** via **ESPHome External Component** (1:1 Contract so gut wie möglich, Send-only möglich, Learn möglich).
- **Agent-ID** bleibt über Updates stabil (persistenter Storage), Neuinstallation darf neue ID erzeugen.
- **MQTT Settings** in UI speicherbar, Credentials **verschlüsselt-at-rest** mit Master-Key aus ENV.

---

## Phase 0 – Ausgangsbasis sichern (kein Refactor, nur Stabilität)

### Task 0.1 – Branch und Baseline-Tests dokumentieren
**Ziel:** Vor jedem Umbau sicherstellen, dass „jetzt“ reproduzierbar läuft.

1. Prüfe lokalen Stand:
   - Hub+IR (aktuelles System) startet im Docker-Setup
   - Learn + Send funktionieren mit `/dev/lirc*`
2. Lege eine kurze Test-Checkliste an (README/Docs):
   - Start
   - Learn Start/Stop
   - Code wird gespeichert
   - Send eines gespeicherten Codes
   - „Sending blocked while learning“ Verhalten

**Test:** Alles einmal manuell durchklicken und die erwarteten Outputs notieren.

---

## Phase 1 – Domänenmodell & Agent-Abstraktion im Code (ohne Deployment-Änderungen)

### Task 1.1 – Agent-Konzept als interne Schnittstelle einführen
**Ziel:** Hub und IR-Hardware sauber trennen, ohne dass sich das Verhalten ändert.

1. Definiere interne Konzepte (nur Struktur/Interfaces, keine neuen Features nötig):
   - `Agent` (kann Befehle ausführen: `send`, `learn_start`, `learn_stop`, `status`)
   - `AgentRegistry` (Hub kennt verfügbare Agents + Status)
   - `Transport` (wie Hub einen Agent anspricht: `local` oder `mqtt`)
2. Baue den bestehenden IR-Teil so um, dass er wie ein `LocalAgent` wirkt, aber weiterhin exakt dasselbe tut wie vorher.

**Test:** Baseline-Tests aus Phase 0 müssen weiterhin 1:1 funktionieren.

---

## Phase 2 – Runtime-Splitting auf Raspberry-Pi-Ebene (erstmal ohne MQTT-Broker-Zwang)

### Task 2.1 – „Hub spricht Agent“ (Local-Transport) implementieren
**Ziel:** `ir-agent-hub` soll ohne Broker laufen, aber trotzdem Agent-Konzept nutzen.

1. Implementiere Local-Transport:
   - Hub ruft Local-Agent direkt auf (im selben Prozess oder via localhost-HTTP, je nach Architektur)
2. Hub registriert Local-Agent beim Start automatisch in der DB als „verfügbar“.

**Test:**
- Kein MQTT-Broker nötig.
- Learn/Senden funktioniert weiterhin.

### Task 2.2 – Agent-ID Persistenz (Update-stabil)
**Ziel:** Der Local-Agent (und später der `ir-agent`) behält `agentId` über Updates.

1. Beim ersten Start:
   - `agentId` generieren (UUID ist ok)
   - in persistentem Pfad speichern (Volume), z. B. `/data/agent/agent_id`
2. Bei Start:
   - wenn Datei existiert → wiederverwenden
   - sonst → neu generieren

**Test:** Container neu bauen/neu starten → `agentId` bleibt gleich (solange Volume bleibt).

---

## Phase 3 – Docker Build-Targets/Images (ohne Funktion zu brechen)

### Task 3.1 – Dockerfile als Multi-Target aufbauen
**Ziel:** Ein Dockerfile, 3 Targets.

Targets:
- `ir-agent-hub`: Hub + Local-Agent + IR dependencies (ir-ctl etc.)
- `ir-hub`: Hub ohne IR dependencies (kein /dev/lirc*, IR features disabled)
- `ir-agent`: reiner Agent (IR dependencies + MQTT + optional HTTP), ohne UI/DB

Wichtig:
- Kein Code-Duplikat, nur unterschiedliche Start-Commands und Abhängigkeiten.

**Test:**
- `ir-agent-hub` läuft exakt wie vorher.
- `ir-hub` startet ohne `/dev/lirc*` und zeigt UI, aber „Learn/Send“ sind deaktiviert oder führen zu sauberer Fehlermeldung („kein Agent“).
- `ir-agent` startet standalone (zunächst ohne Pairing/Hub, nur „health/status“).

---

## Phase 4 – MQTT optional im Hub (für externe Agents), ohne Broker-Zwang für Local

### Task 4.1 – MQTT Settings in UI + DB (verschlüsselt-at-rest)
**Ziel:** Broker-Daten in UI editierbar, Passwort nicht im Klartext in DB.

1. UI/Settings:
   - broker host
   - port
   - username
   - password
   - optional: base topic, client id prefix
2. Storage:
   - Non-secrets (host/port/user) im Klartext ok
   - password verschlüsselt speichern
3. Master-Key:
   - kommt via ENV (oder Docker Secret)
   - bei fehlendem Key → Settings-UI zeigt Warnung und speichert Passwort nicht (oder speichert Klartext, je nach gewünschtem Fallback)

**Test:**
- MQTT disabled (leere Settings) → Hub läuft weiterhin.
- MQTT enabled (gültige Settings) → Hub kann subscriben/publishen.

### Task 4.2 – MQTT Transport im Hub (ohne Topic-Versionierung)
**Ziel:** Hub kann externe Agents sehen und ansprechen.

1. Topics ohne Versionierung, aber Payload hat:
   - `protocolVersion` (oder `agentSoftwareVersion`)
2. Bei mismatch:
   - Hub markiert Agent als „incompatible“ und zeigt UI-Fehler an
   - optional später: Update-Mechanismus

**Test:**
- Hub startet mit MQTT, ohne Agents: ok.
- Simulierter Agent (oder später echter `ir-agent`) taucht in UI als „online“ auf.

---

## Phase 5 – Pairing/Registrierung über UI (dein gewünschter Flow)

### Task 5.1 – Pairing-Window (Hub initiiert, Agents bieten sich an)
**Ziel:** Kein manuelles Token setzen. UI „Hinzufügen“ und fertig.

Ablauf:
1. In UI: „Pairing starten (60s)“
2. Hub publisht `pairing/request` (mit nonce + expiry)
3. Unpaired Agents hören auf `pairing/request` und antworten auf `pairing/offer`
4. Hub listet Offers in UI
5. User klickt „Übernehmen“
6. Hub publisht `pairing/accept` für genau diesen Agent
7. Agent speichert „paired=true“ persistent

**Test:**
- Pairing startet, Agent erscheint, „Übernehmen“ → Agent ist registriert
- Neustart Agent → bleibt registriert (paired)

### Task 5.2 – Agent Capabilities bei Registrierung
**Ziel:** Hub/UI wissen, ob Agent send-only oder learn+send kann.

Capabilities (Minimal):
- `canSend` (bool)
- `canLearn` (bool)
- `formatRaw` (bool)
- `maxPayloadBytes` (int, wichtig für Chunking)

**Test:** UI zeigt korrekt an, Learn-Button nur wenn `canLearn=true`.

---

## Phase 6 – Remote/Code/Agent Zuordnung & UX-Regeln

### Task 6.1 – Remote ist hart an Agent gebunden (pro Remote)
**Ziel:** Kein Fallback, klare Fehlermeldung.

Regeln:
- Remote hat `assignedAgentId`
- Wenn `None`:
  - beim ersten Learn: UI fragt Agent-Auswahl
  - danach wird das Remote default auf diesen Agent gesetzt (nur wenn vorher `None`)

**Test:**
- Neues Remote → first learn fragt Agent, dann default gesetzt
- Remote sendet immer über assigned Agent

### Task 6.2 – „Agent offline“ Handling
**Ziel:** Saubere Meldung.

- Wenn assigned Agent offline:
  - UI: „Agent offline“
  - Send/Learn wird nicht ausgeführt

**Test:** Agent stoppen → UI zeigt offline; Send ergibt klaren Fehler.

---

## Phase 7 – Logging (Hub Log + Action Events)

### Task 7.1 – Hub Log mit Retention + LogLevel
**Ziel:** Debugging „warum ging’s nicht“.

1. Settings:
   - LogLevel (info/debug/warn/error)
   - Retention (z. B. 7 Tage, einstellbar)
2. Speicherung:
   - Datei oder DB (DB sinnvoll für UI-Ansicht)
3. UI:
   - Log-Viewer (filterbar)

**Test:** Send/learn erzeugt Logs; alte Logs werden nach Retention entfernt.

### Task 7.2 – Action Event Tabelle (optional aber sehr hilfreich)
**Ziel:** Jede Aktion ist nachvollziehbar.

- Event pro Aktion:
  - type: `send` / `learn_start` / `learn_result`
  - remoteId/buttonId
  - agentId
  - correlationId
  - status + reason

---

## Phase 8 – Message-Contract Details (nur was nötig ist) + Chunking

### Task 8.1 – Standardfelder pro Nachrichtentyp (nicht „immer überall alles“)
**Ziel:** Du hattest recht: Nicht jedes Feld in jeder Message, aber ein konsistentes Minimum je Typ.

Empfehlung:
- **Commands (Hub→Agent)**:
  - `correlationId` (damit Antworten zuordenbar)
  - `agentId` optional (meist Topic/Client already identifies)
  - `ts` optional (nice-to-have)
  - payload spezifisch: z. B. raw, repeats, carrier
- **Results/Events (Agent→Hub)**:
  - `correlationId`
  - `result` (`ok|error`)
  - `reason` bei error
  - optional: timings, duration, captured raw data

**Test:** Parallel Send+Learn in UI → Hub kann Responses sauber zuordnen.

### Task 8.2 – Chunking-Protokoll für Raw IR
**Ziel:** Große Raw-Daten in mehrere MQTT Messages splitten.

Konzept:
1. Hub startet Learn Session → Agent liefert capture als Chunk-Stream:
   - `chunkIndex`, `chunkCount` (oder `isLast`)
   - `transferId` (kann = correlationId sein)
2. Hub sammelt Chunks und setzt Raw-Daten wieder zusammen
3. Hub speichert finalen Code in DB

Wichtig:
- `maxPayloadBytes` Capability vom Agent nutzen (oder Broker Limit konservativ annehmen)

**Test:** Learn eines langen Signals → kommt in mehreren Chunks an, wird korrekt gespeichert und sendbar.

---

## Phase 9 – `ir-agent` (Pi/Zero) fertig machen (MQTT + optional HTTP)

### Task 9.1 – MQTT Agent Runtime
**Ziel:** Externer Agent kann alles wie Local-Agent, nur über MQTT.

1. Implementiere:
   - connect to broker
   - listen pairing
   - commands: learn_start/stop, send, status
   - publish results/events

**Test:** Hub (`ir-hub` oder `ir-agent-hub`) + externer `ir-agent`:
- Pairing klappt
- Learn/Senden klappt remote

### Task 9.2 – Optional: HTTP API zusätzlich
**Ziel:** Für Pi-Agent kann HTTP praktisch sein (Debug/Standalone Nutzung), aber nicht zwingend.

Wenn du es machst:
- HTTP endpoints spiegeln Commands/Status
- Hub nutzt HTTP nur dann, wenn du es explizit willst (sonst MQTT-only für externe Agents)

---

## Phase 10 – ESP32 Agent via ESPHome External Component

### Task 10.1 – External Component Repo + Package
**Ziel:** Wiederverwendbares Template.

1. Repo-Struktur:
   - `components/ir_agent/` (C++ + Python glue)
   - `packages/ir_agent.yaml` (Defaults, substitutions)
2. MQTT:
   - subscribe command topics
   - publish results/events
3. IR:
   - send raw
   - learn raw (optional v1/v2: erst send-only, dann learn)

**Test:**
- ESP32 flasht, verbindet sich, registriert sich am Hub
- Send eines gespeicherten Codes funktioniert

### Task 10.2 – OTA beim ESP
**Ziel:** „ultra geil“: Updates ohne Kabel.

- ESPHome unterstützt OTA Updates out-of-the-box (über `ota:` im YAML und passwort).  
- Für dein Agent-Template bedeutet das: Du lieferst OTA als Standard in deinem Package mit.

**Test:** OTA-Update durchführen und prüfen, dass `agentId` (NVS) gleich bleibt.

---

## Phase 11 – Feinschliff & Erweiterungen

- Erweiterte Agent-Verwaltung UI (Status, Last seen, restart hints)
- Update-Strategie:
  - ESP: OTA ist der Standard
  - Container: optional später pull/restart (nicht Teil der Kernarchitektur)
- Robustheit:
  - reconnect handling
  - offline detection (last seen heartbeat)
- Optional: Agent busy state im Hub anzeigen

---

# Empfohlene Reihenfolge (kurz)
1. Phase 0 (Baseline)
2. Phase 1 (Agent-Abstraktion intern)
3. Phase 2 (Local-Transport, AgentId persist)
4. Phase 3 (Docker Targets: `ir-agent-hub` zuerst, dann `ir-hub`, dann `ir-agent`)
5. Phase 4 (MQTT optional + Settings)
6. Phase 5 (Pairing UI)
7. Phase 6 (Remote binding + offline UX)
8. Phase 7 (Logging)
9. Phase 8 (Chunking)
10. Phase 9 (Externer Pi-Agent)
11. Phase 10 (ESPHome external component + OTA)

Wenn du das so durchgehst, kannst du nach jeder Phase testen, ohne den Rest zu brechen.
