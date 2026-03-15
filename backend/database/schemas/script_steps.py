import json
import sqlite3
from typing import Optional, List, Dict, Any

from database.database_base import DatabaseBase

_VALID_TYPES = ("send", "hold", "wait", "repeat")


class ScriptSteps(DatabaseBase):
    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS script_steps (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                script_id INTEGER NOT NULL,
                position  INTEGER NOT NULL,
                type      TEXT    NOT NULL,
                params    TEXT    NOT NULL DEFAULT '{}',
                FOREIGN KEY(script_id) REFERENCES scripts(id) ON DELETE CASCADE,
                UNIQUE(script_id, position)
            );

            CREATE INDEX IF NOT EXISTS ix_script_steps_script_id ON script_steps(script_id);
            """
        )

    def set_steps(
        self,
        script_id: int,
        steps: List[Dict[str, Any]],
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        """Replace all steps for a script atomically. steps is an ordered list of {type, params}."""
        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)).fetchone()
            if not row:
                raise ValueError("Unknown script_id")

            c.execute("DELETE FROM script_steps WHERE script_id = ?", (script_id,))
            for position, step in enumerate(steps):
                step_type = str(step.get("type", "")).strip()
                if step_type not in _VALID_TYPES:
                    raise ValueError(f"Invalid step type: {step_type!r}")
                params_json = json.dumps(step.get("params", {}), ensure_ascii=False)
                c.execute(
                    "INSERT INTO script_steps(script_id, position, type, params) VALUES(?, ?, ?, ?)",
                    (script_id, position, step_type, params_json),
                )
            c.commit()
            return self.get_steps(script_id, conn=c)
        finally:
            if close:
                c.close()

    def get_steps(
        self,
        script_id: int,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            rows = c.execute(
                "SELECT id, script_id, position, type, params FROM script_steps "
                "WHERE script_id = ? ORDER BY position",
                (script_id,),
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
