import sqlite3
import time
from typing import Optional, List, Dict, Any

from database.database_base import DatabaseBase


class Buttons(DatabaseBase):
    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS buttons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remote_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                icon TEXT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(remote_id) REFERENCES remotes(id) ON DELETE CASCADE,
                UNIQUE(remote_id, name)
            );

            CREATE INDEX IF NOT EXISTS ix_buttons_remote_id ON buttons(remote_id);
            """
        )

    # -----------------------------
    # Buttons
    # -----------------------------

    def create(self, remote_id: int, name: str, icon: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Button name must not be empty")

        c, close = self._use_conn(conn)
        try:
            remote_row = c.execute("SELECT id FROM remotes WHERE id = ?", (remote_id,)).fetchone()
            if not remote_row:
                raise ValueError("Unknown remote_id")

            now = time.time()
            c.execute(
                "INSERT OR IGNORE INTO buttons(remote_id, name, icon, created_at, updated_at) VALUES(?, ?, ?, ?, ?)",
                (remote_id, name, icon, now, now),
            )
            c.commit()

            row = c.execute(
                "SELECT id, remote_id, name, icon, created_at, updated_at FROM buttons WHERE remote_id = ? AND name = ?",
                (remote_id, name),
            ).fetchone()
            if not row:
                raise ValueError("Failed to create button")
            return dict(row)
        finally:
            if close:
                c.close()

    def get(self, button_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute(
                "SELECT id, remote_id, name, icon, created_at, updated_at FROM buttons WHERE id = ?",
                (button_id,),
            ).fetchone()
            if not row:
                raise ValueError("Unknown button_id")
            return dict(row)
        finally:
            if close:
                c.close()

    def get_by_name(self, remote_id: int, name: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute(
                "SELECT id, remote_id, name, icon, created_at, updated_at FROM buttons WHERE remote_id = ? AND name = ?",
                (remote_id, name.strip()),
            ).fetchone()
            return dict(row) if row else None
        finally:
            if close:
                c.close()

    def list(self, remote_id: int, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            rows = c.execute(
                """
                SELECT b.id, b.remote_id, b.name, b.icon, b.created_at, b.updated_at,
                       CASE WHEN s.button_id IS NULL THEN 0 ELSE 1 END AS has_press,
                       CASE WHEN s.hold_initial IS NULL OR s.hold_initial = '' THEN 0 ELSE 1 END AS has_hold,
                       s.encoding,
                       s.protocol
                FROM buttons b
                LEFT JOIN button_signals s ON s.button_id = b.id
                WHERE b.remote_id = ?
                ORDER BY b.name
                """,
                (remote_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if close:
                c.close()

    def rename(self, button_id: int, name: str, icon: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Button name must not be empty")

        c, close = self._use_conn(conn)
        try:
            current = c.execute("SELECT id, remote_id FROM buttons WHERE id = ?", (button_id,)).fetchone()
            if not current:
                raise ValueError("Unknown button_id")

            now = time.time()
            c.execute(
                "UPDATE buttons SET name = ?, icon = ?, updated_at = ? WHERE id = ?",
                (name, icon, now, button_id),
            )
            c.commit()

            out = c.execute(
                "SELECT id, remote_id, name, icon, created_at, updated_at FROM buttons WHERE id = ?",
                (button_id,),
            ).fetchone()
            if not out:
                raise ValueError("Unknown button_id")
            return dict(out)
        finally:
            if close:
                c.close()

    def delete(self, button_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute(
                "SELECT id, remote_id, name, icon, created_at, updated_at FROM buttons WHERE id = ?",
                (button_id,),
            ).fetchone()
            if not row:
                raise ValueError("Unknown button_id")

            c.execute("DELETE FROM buttons WHERE id = ?", (button_id,))
            c.commit()
            return dict(row)
        finally:
            if close:
                c.close()
                