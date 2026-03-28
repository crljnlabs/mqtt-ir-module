import sqlite3
import time
from typing import Optional, List, Dict, Any

from database.database_base import DatabaseBase

_VALID_STATUSES = ("running", "completed", "failed", "cancelled")


class ScriptRuns(DatabaseBase):
    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS script_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                script_id   INTEGER NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'running',
                started_at  REAL    NOT NULL,
                finished_at REAL    NULL,
                FOREIGN KEY(script_id) REFERENCES scripts(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS ix_script_runs_script_id ON script_runs(script_id);
            """
        )

    def create(self, script_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)).fetchone()
            if not row:
                raise ValueError("Unknown script_id")

            now = time.time()
            c.execute(
                "INSERT INTO script_runs(script_id, status, started_at) VALUES(?, 'running', ?)",
                (script_id, now),
            )
            c.commit()
            out = c.execute(
                "SELECT id, script_id, status, started_at, finished_at "
                "FROM script_runs WHERE id = last_insert_rowid()"
            ).fetchone()
            if not out:
                raise ValueError("Failed to create script run")
            return dict(out)
        finally:
            if close:
                c.close()

    def finish(
        self,
        run_id: int,
        status: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid run status: {status!r}")

        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT id FROM script_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                raise ValueError("Unknown run_id")

            now = time.time()
            c.execute(
                "UPDATE script_runs SET status = ?, finished_at = ? WHERE id = ?",
                (status, now, run_id),
            )
            c.commit()
            out = c.execute(
                "SELECT id, script_id, status, started_at, finished_at FROM script_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if not out:
                raise ValueError("Unknown run_id")
            return dict(out)
        finally:
            if close:
                c.close()

    def get(self, run_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute(
                "SELECT id, script_id, status, started_at, finished_at FROM script_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if not row:
                raise ValueError("Unknown run_id")
            return dict(row)
        finally:
            if close:
                c.close()

    def list(self, script_id: int, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            rows = c.execute(
                "SELECT id, script_id, status, started_at, finished_at "
                "FROM script_runs WHERE script_id = ? ORDER BY started_at DESC",
                (script_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if close:
                c.close()

    def prune(self, script_id: int, max_runs: int, conn: Optional[sqlite3.Connection] = None) -> int:
        """Delete oldest runs beyond max_runs for a script. Returns number of deleted rows."""
        c, close = self._use_conn(conn)
        try:
            result = c.execute(
                """
                DELETE FROM script_runs
                WHERE script_id = ?
                  AND id NOT IN (
                      SELECT id FROM script_runs
                      WHERE script_id = ?
                      ORDER BY started_at DESC
                      LIMIT ?
                  )
                """,
                (script_id, script_id, max_runs),
            )
            c.commit()
            return int(result.rowcount or 0)
        finally:
            if close:
                c.close()
