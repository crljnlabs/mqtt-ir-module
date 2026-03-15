import json
import sqlite3
import time
from typing import Optional, List, Dict, Any

from database.database_base import DatabaseBase

_VALID_STATUSES = ("pending", "running", "completed", "failed", "skipped")


class ScriptRunSteps(DatabaseBase):
    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS script_run_steps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      INTEGER NOT NULL,
                position    INTEGER NOT NULL,
                label       TEXT    NOT NULL,
                type        TEXT    NOT NULL,
                params      TEXT    NOT NULL DEFAULT '{}',
                status      TEXT    NOT NULL DEFAULT 'pending',
                error       TEXT    NULL,
                started_at  REAL    NULL,
                finished_at REAL    NULL,
                FOREIGN KEY(run_id) REFERENCES script_runs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS ix_script_run_steps_run_id ON script_run_steps(run_id);
            """
        )

    def create_batch(
        self,
        run_id: int,
        steps: List[Dict[str, Any]],
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        """Insert all expanded step rows for a run in one transaction. Each step: {position, label, type, params}."""
        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT id FROM script_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                raise ValueError("Unknown run_id")

            for step in steps:
                params_json = json.dumps(step.get("params", {}), ensure_ascii=False)
                c.execute(
                    "INSERT INTO script_run_steps(run_id, position, label, type, params, status) "
                    "VALUES(?, ?, ?, ?, ?, 'pending')",
                    (run_id, step["position"], step["label"], step["type"], params_json),
                )
            c.commit()
            return self.list(run_id, conn=c)
        finally:
            if close:
                c.close()

    def start(self, step_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT id FROM script_run_steps WHERE id = ?", (step_id,)).fetchone()
            if not row:
                raise ValueError("Unknown step_id")

            now = time.time()
            c.execute(
                "UPDATE script_run_steps SET status = 'running', started_at = ? WHERE id = ?",
                (now, step_id),
            )
            c.commit()
            return self._fetch(step_id, c)
        finally:
            if close:
                c.close()

    def finish(
        self,
        step_id: int,
        status: str,
        error: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid step status: {status!r}")

        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT id FROM script_run_steps WHERE id = ?", (step_id,)).fetchone()
            if not row:
                raise ValueError("Unknown step_id")

            now = time.time()
            c.execute(
                "UPDATE script_run_steps SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                (status, error, now, step_id),
            )
            c.commit()
            return self._fetch(step_id, c)
        finally:
            if close:
                c.close()

    def list(self, run_id: int, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            rows = c.execute(
                "SELECT id, run_id, position, label, type, params, status, error, started_at, finished_at "
                "FROM script_run_steps WHERE run_id = ? ORDER BY position",
                (run_id,),
            ).fetchall()
            result = []
            for r in rows:
                entry = dict(r)
                entry["params"] = json.loads(entry["params"])
                result.append(entry)
            return result
        finally:
            if close:
                c.close()

    def _fetch(self, step_id: int, conn: sqlite3.Connection) -> Dict[str, Any]:
        row = conn.execute(
            "SELECT id, run_id, position, label, type, params, status, error, started_at, finished_at "
            "FROM script_run_steps WHERE id = ?",
            (step_id,),
        ).fetchone()
        if not row:
            raise ValueError("Unknown step_id")
        entry = dict(row)
        entry["params"] = json.loads(entry["params"])
        return entry
