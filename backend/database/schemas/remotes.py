import sqlite3
import time
from typing import Optional, List, Dict, Any

from database.database_base import DatabaseBase


class Remotes(DatabaseBase):
    # -----------------------------
    # Schema
    # -----------------------------
    @staticmethod
    def _create_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS remotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                icon TEXT NULL,
                assigned_agent_id TEXT NULL,
                carrier_hz INTEGER NULL,
                duty_cycle INTEGER NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )

    # -----------------------------
    # Table methods
    # -----------------------------
    def create(
        self,
        name: str,
        icon: Optional[str] = None,
        assigned_agent_id: Optional[str] = None,
        carrier_hz: Optional[int] = None,
        duty_cycle: Optional[int] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Remote name must not be empty")

        c, close = self._use_conn(conn)
        try:
            now = time.time()
            c.execute(
                "INSERT OR IGNORE INTO remotes(name, icon, assigned_agent_id, carrier_hz, duty_cycle, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (name, icon, assigned_agent_id, carrier_hz, duty_cycle, now, now),
            )
            c.commit()

            row = c.execute(
                "SELECT id, name, icon, assigned_agent_id, carrier_hz, duty_cycle, created_at, updated_at FROM remotes WHERE name = ?",
                (name,),
            ).fetchone()
            if not row:
                raise ValueError("Failed to create remote")
            return dict(row)
        finally:
            if close:
                c.close()

    def update(
        self,
        remote_id: int,
        name: str,
        icon: Optional[str] = None,
        assigned_agent_id: Optional[str] = None,
        carrier_hz: Optional[int] = None,
        duty_cycle: Optional[int] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Remote name must not be empty")

        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT id FROM remotes WHERE id = ?", (remote_id,)).fetchone()
            if not row:
                raise ValueError("Unknown remote_id")

            now = time.time()
            c.execute(
                "UPDATE remotes SET name = ?, icon = ?, assigned_agent_id = ?, carrier_hz = ?, duty_cycle = ?, updated_at = ? WHERE id = ?",
                (name, icon, assigned_agent_id, carrier_hz, duty_cycle, now, remote_id),
            )
            c.commit()

            out = c.execute(
                "SELECT id, name, icon, assigned_agent_id, carrier_hz, duty_cycle, created_at, updated_at FROM remotes WHERE id = ?",
                (remote_id,),
            ).fetchone()
            if not out:
                raise ValueError("Unknown remote_id")
            return dict(out)
        finally:
            if close:
                c.close()

    def delete(self, remote_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute(
                "SELECT id, name, icon, assigned_agent_id, carrier_hz, duty_cycle, created_at, updated_at FROM remotes WHERE id = ?",
                (remote_id,),
            ).fetchone()
            if not row:
                raise ValueError("Unknown remote_id")

            c.execute("DELETE FROM remotes WHERE id = ?", (remote_id,))
            c.commit()
            return dict(row)
        finally:
            if close:
                c.close()

    def get(self, remote_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute(
                "SELECT id, name, icon, assigned_agent_id, carrier_hz, duty_cycle, created_at, updated_at FROM remotes WHERE id = ?",
                (remote_id,),
            ).fetchone()
            if not row:
                raise ValueError("Unknown remote_id")
            return dict(row)
        finally:
            if close:
                c.close()

    def list(self, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            rows = c.execute(
                "SELECT id, name, icon, assigned_agent_id, carrier_hz, duty_cycle, created_at, updated_at FROM remotes ORDER BY name"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if close:
                c.close()

    def clear_buttons(self, remote_id: int, conn: Optional[sqlite3.Connection] = None) -> None:
        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT id FROM remotes WHERE id = ?", (remote_id,)).fetchone()
            if not row:
                raise ValueError("Unknown remote_id")

            c.execute("DELETE FROM buttons WHERE remote_id = ?", (remote_id,))
            c.commit()
        finally:
            if close:
                c.close()

    def set_assigned_agent(
        self,
        remote_id: int,
        assigned_agent_id: Optional[str],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT id FROM remotes WHERE id = ?", (remote_id,)).fetchone()
            if not row:
                raise ValueError("Unknown remote_id")

            now = time.time()
            c.execute(
                "UPDATE remotes SET assigned_agent_id = ?, updated_at = ? WHERE id = ?",
                (assigned_agent_id, now, remote_id),
            )
            c.commit()
            out = c.execute(
                "SELECT id, name, icon, assigned_agent_id, carrier_hz, duty_cycle, created_at, updated_at FROM remotes WHERE id = ?",
                (remote_id,),
            ).fetchone()
            if not out:
                raise ValueError("Unknown remote_id")
            return dict(out)
        finally:
            if close:
                c.close()

    def clear_assigned_agent(self, agent_id: str, conn: Optional[sqlite3.Connection] = None) -> int:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return 0

        c, close = self._use_conn(conn)
        try:
            now = time.time()
            result = c.execute(
                "UPDATE remotes SET assigned_agent_id = NULL, updated_at = ? WHERE assigned_agent_id = ?",
                (now, normalized_agent_id),
            )
            c.commit()
            return int(result.rowcount or 0)
        finally:
            if close:
                c.close()
