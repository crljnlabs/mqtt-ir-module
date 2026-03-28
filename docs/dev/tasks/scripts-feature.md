# Scripts Feature

**Status:** DB schema implemented. API, runner, and frontend pending.

## Goal

Allow users to define named scripts: ordered sequences of IR actions that can be executed as a single unit. Each run is logged step-by-step so failures can be traced precisely.

## Context

- Hub owns the SQLite DB (`ir.db`); scripts belong there.
- Remotes and buttons already exist with integer IDs.
- Scripts reference buttons by `remote_id` + `button_id` (survive renames, break on delete — acceptable).
- Step params stored as JSON blob; one table covers all step types without schema sprawl.
- HA integration is currently facade-only (entity classes not yet implemented) — scripts are not exposed to HA in this version.

---

## DB Schema (CREATE — no migration needed, add to initial setup)

```sql
-- Script definition
CREATE TABLE IF NOT EXISTS scripts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

-- Ordered steps belonging to a script
CREATE TABLE IF NOT EXISTS script_steps (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id INTEGER NOT NULL,
    position  INTEGER NOT NULL,           -- 0-based, contiguous
    type      TEXT    NOT NULL,           -- send | hold | wait | repeat
    params    TEXT    NOT NULL DEFAULT '{}',
    FOREIGN KEY(script_id) REFERENCES scripts(id) ON DELETE CASCADE,
    UNIQUE(script_id, position)
);

CREATE INDEX IF NOT EXISTS ix_script_steps_script_id ON script_steps(script_id);

-- One row per script execution
CREATE TABLE IF NOT EXISTS script_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id   INTEGER NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'running',  -- running | completed | failed | cancelled
    started_at  REAL    NOT NULL,
    finished_at REAL    NULL,
    FOREIGN KEY(script_id) REFERENCES scripts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_script_runs_script_id ON script_runs(script_id);

-- One row per step execution within a run (repeat iterations expand to individual rows)
CREATE TABLE IF NOT EXISTS script_run_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL,
    position    INTEGER NOT NULL,     -- sequential execution order (0, 1, 2, ...)
    label       TEXT    NOT NULL,     -- human-readable: "send TV:Power" or "repeat[2] iter 2/5 › wait"
    type        TEXT    NOT NULL,
    params      TEXT    NOT NULL DEFAULT '{}',
    status      TEXT    NOT NULL DEFAULT 'pending',  -- pending | running | completed | failed | skipped
    error       TEXT    NULL,
    started_at  REAL    NULL,
    finished_at REAL    NULL,
    FOREIGN KEY(run_id) REFERENCES script_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_script_run_steps_run_id ON script_run_steps(run_id);
```

**Run retention** is controlled by the global setting key `script_max_runs` (integer, default: `10`).
When a new run is created for a script and the stored run count exceeds this limit, the oldest runs for that script are deleted (cascade removes their step rows).

---

## Step Type Reference

### `send`
Single IR button press.
```json
{ "remote_id": 1, "button_id": 3 }
```

### `hold`
Hold a button for a given duration (long press).
```json
{ "remote_id": 1, "button_id": 3, "duration_ms": 2000 }
```

### `wait`
Pause execution.
```json
{ "duration_ms": 1000 }
```

### `repeat`
Repeat a nested sub-sequence N times. Nested steps follow the same `{ type, params }` shape.
Max nesting depth: 1 (no repeat inside repeat).
```json
{
  "count": 3,
  "steps": [
    { "type": "send", "params": { "remote_id": 1, "button_id": 3 } },
    { "type": "wait", "params": { "duration_ms": 500 } }
  ]
}
```

---

## Example Script

```
Name: "Turn on TV and set volume"
Steps:
  0 — send   { remote_id: 1, button_id: 5 }          // TV power
  1 — wait   { duration_ms: 1500 }                    // wait for TV to boot
  2 — repeat { count: 5, steps: [
                 { type: "send", params: { remote_id: 1, button_id: 8 } },  // vol+
                 { type: "wait", params: { duration_ms: 300 } }
               ] }

Resulting script_run_steps rows for one run (sequential position):
  0  send  "send TV:Power"               completed
  1  wait  "wait 1500ms"                 completed
  2  send  "repeat[2] iter 1/5 › send TV:Vol+"   completed
  3  wait  "repeat[2] iter 1/5 › wait 300ms"     completed
  4  send  "repeat[2] iter 2/5 › send TV:Vol+"   completed
  5  wait  "repeat[2] iter 2/5 › wait 300ms"     completed
  ...
  11 wait  "repeat[2] iter 5/5 › wait 300ms"     completed
```

---

## What to Implement

### Backend — Database ✅ DONE

- `backend/database/schemas/scripts.py` — `Scripts` class
  - `_create_schema`, `create`, `get`, `list`, `update`, `delete`
- `backend/database/schemas/script_steps.py` — `ScriptSteps` class
  - `set_steps(script_id, steps)`: replace all steps atomically (DELETE + bulk INSERT)
  - `get_steps(script_id)`: ordered by `position`
- `backend/database/schemas/script_runs.py` — `ScriptRuns` class
  - `create(script_id)` → returns run row with `status='running'`
  - `finish(run_id, status)` → sets `status` + `finished_at`
  - `get(run_id)`, `list(script_id)` → ordered by `started_at DESC`
  - `prune(script_id, max_runs)` → delete oldest runs beyond the limit
- `backend/database/schemas/script_run_steps.py` — `ScriptRunSteps` class
  - `create_batch(run_id, steps)` → inserts all expanded step rows in one transaction
  - `start(step_id)` → sets `status='running'`, `started_at`
  - `finish(step_id, status, error=None)` → sets `status`, `finished_at`, `error`
  - `list(run_id)` → ordered by `position`
- All four registered in `Database.__init__` and `Database.init()`.
- `script_max_runs` added to `Settings.get_script_settings()`, included in `get_ui_settings()` and `update_ui_settings()` (default: 10, range: 1–100).

### Backend — API Endpoints

```
GET    /scripts                        list all scripts (no steps)
POST   /scripts                        create script + steps
GET    /scripts/{id}                   get script with steps
PUT    /scripts/{id}                   update name/description + replace steps
DELETE /scripts/{id}                   delete script (cascades runs)

POST   /scripts/{id}/run               start a run → returns { run_id } immediately (async)
GET    /scripts/{id}/runs              list runs for a script (with summary, no step detail)
GET    /scripts/{id}/runs/{run_id}     get run with all step rows
DELETE /scripts/{id}/runs/{run_id}     cancel a running script (sets cancel flag; runner checks between steps)
```

### Backend — Script Runner

`backend/scripts/script_runner.py`

- Accepts `script_id` + `run_id`; fetches steps from DB
- Expands `repeat` blocks into individual step records in `script_run_steps` before starting
- Executes steps sequentially:
  - Marks each step `running` → executes → marks `completed` or `failed` (with error)
  - After each step: checks cancellation flag for `run_id`; if set → marks remaining steps `skipped`, run `cancelled`
  - On unhandled exception: marks current step `failed`, remaining steps `skipped`, run `failed`
- Delegates `send`/`hold` to existing send logic (reuse `IrSendHandler` or equivalent)
- Handles `wait` with `asyncio.sleep`
- On completion: calls `ScriptRuns.prune(script_id, max_runs_setting)`
- Cancellation flag: in-memory dict `{ run_id: True }` on the runner instance (no DB column needed — a cancelled run that completes before the flag is checked just finishes normally, which is acceptable)

### Settings

Add to the existing settings table:
- Key: `script_max_runs`, type: integer, default: `10`
- Exposed in the existing settings UI

### Frontend — 3 new pages

**ScriptsPage** (`/scripts`)
- List all scripts: name, description, step count, last-run status badge, run / edit / delete actions
- "New script" button → opens editor

**ScriptEditorPage** (`/scripts/new`, `/scripts/{id}/edit`)
- Name + description fields
- Step list with drag-and-drop reorder
- Step type selector (send / hold / wait / repeat)
- Per-type param form:
  - `send`/`hold`: remote dropdown → button dropdown; `hold` adds duration field
  - `wait`: duration field
  - `repeat`: count field + nested step list (same controls, no further nesting)
- Save → `POST /scripts` or `PUT /scripts/{id}`

**ScriptRunsPage** (`/scripts/{id}/runs`)
- List of past runs for a script (status, started_at, duration)
- Click a run → expand step-level detail
- Visualization: vertical timeline of steps; each step shows label, status (color-coded), duration, error message if failed
- Cancel button for runs with `status='running'` → `DELETE /scripts/{id}/runs/{run_id}`

---

## Validation

- `type` must be one of `send | hold | wait | repeat`
- `send`/`hold`: `remote_id` and `button_id` must exist in DB
- `hold`: `duration_ms` > 0
- `wait`: `duration_ms` > 0
- `repeat`: `count` >= 1; nested steps validated recursively; no nested `repeat` inside `repeat`
- `position` values: contiguous 0-based integers; enforced by `set_steps`

---

## Key Decisions

- **JSON params blob** over per-type tables: avoids schema sprawl; params are never queried individually.
- **`set_steps` replaces all steps atomically**: avoids orphan/gap issues with positions on edit.
- **`duration_ms` (integer)** over `duration_s` (float): avoids float precision issues; consistent with IR timing conventions.
- **Max repeat nesting depth: 1**: keeps runner and UI simple; covers all practical use cases.
- **Repeat expands to flat step rows at run time**: each iteration gets its own `script_run_steps` row with a readable `label`; makes visualization and failure tracing straightforward.
- **Cancellation via in-memory flag**: no DB column needed; a run only checks between steps, so a cancel request on an already-completed run is a no-op.
- **Run retention via `script_max_runs` setting**: pruning happens after each run completes; cascade delete handles step cleanup.
- **No script-to-script call type**: avoids recursion/cycle detection complexity; can be added later.
- **HA integration deferred**: current HA support is facade-only; entity classes are missing. Scripts will be exposed as HA buttons in a future version once the entity layer is implemented. No preparatory schema columns added now — the `scripts` table is clean and the HA layer can reference `script.id` externally when ready.
