import sqlite3
import time
from typing import Optional, List, Dict, Any

from database.database_base import DatabaseBase


class Scripts(DatabaseBase):
    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scripts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                description TEXT NULL,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            );
            """
        )

    def create(
        self,
        name: str,
        description: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Script name must not be empty")

        c, close = self._use_conn(conn)
        try:
            now = time.time()
            c.execute(
                "INSERT INTO scripts(name, description, created_at, updated_at) VALUES(?, ?, ?, ?)",
                (name, description, now, now),
            )
            c.commit()
            row = c.execute(
                "SELECT id, name, description, created_at, updated_at FROM scripts WHERE id = last_insert_rowid()"
            ).fetchone()
            if not row:
                raise ValueError("Failed to create script")
            return dict(row)
        finally:
            if close:
                c.close()

    def get(self, script_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute(
                "SELECT id, name, description, created_at, updated_at FROM scripts WHERE id = ?",
                (script_id,),
            ).fetchone()
            if not row:
                raise ValueError("Unknown script_id")
            return dict(row)
        finally:
            if close:
                c.close()

    def list(self, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            rows = c.execute(
                "SELECT id, name, description, created_at, updated_at FROM scripts ORDER BY name"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if close:
                c.close()

    def update(
        self,
        script_id: int,
        name: str,
        description: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Script name must not be empty")

        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT id FROM scripts WHERE id = ?", (script_id,)).fetchone()
            if not row:
                raise ValueError("Unknown script_id")

            now = time.time()
            c.execute(
                "UPDATE scripts SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                (name, description, now, script_id),
            )
            c.commit()
            out = c.execute(
                "SELECT id, name, description, created_at, updated_at FROM scripts WHERE id = ?",
                (script_id,),
            ).fetchone()
            if not out:
                raise ValueError("Unknown script_id")
            return dict(out)
        finally:
            if close:
                c.close()

    def delete(self, script_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute(
                "SELECT id, name, description, created_at, updated_at FROM scripts WHERE id = ?",
                (script_id,),
            ).fetchone()
            if not row:
                raise ValueError("Unknown script_id")

            c.execute("DELETE FROM scripts WHERE id = ?", (script_id,))
            c.commit()
            return dict(row)
        finally:
            if close:
                c.close()
