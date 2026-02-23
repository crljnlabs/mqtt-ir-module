import sqlite3
import time
from typing import Any, Dict, List, Optional

from database.database_base import DatabaseBase


class Agents(DatabaseBase):
    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                name TEXT NULL,
                icon TEXT NULL,
                transport TEXT NOT NULL,
                status TEXT NOT NULL,
                can_send INTEGER NOT NULL DEFAULT 0,
                can_learn INTEGER NOT NULL DEFAULT 0,
                sw_version TEXT NULL,
                agent_topic TEXT NULL,
                configuration_url TEXT NULL,
                pending INTEGER NOT NULL DEFAULT 0,
                pairing_session_id TEXT NULL,
                last_seen REAL NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )

    def upsert(
        self,
        agent_id: str,
        name: Optional[str],
        icon: Optional[str],
        transport: str,
        status: str,
        can_send: bool,
        can_learn: bool,
        sw_version: Optional[str],
        agent_topic: Optional[str],
        last_seen: Optional[float],
        configuration_url: Optional[str] = None,
        pending: bool = False,
        pairing_session_id: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            raise ValueError("agent_id must not be empty")

        normalized_name = self._normalize_name(name)
        normalized_icon = self._normalize_icon(icon)
        normalized_url = self._normalize_configuration_url(configuration_url)
        normalized_sw_version = self._normalize_optional_text(sw_version)
        normalized_agent_topic = self._normalize_optional_text(agent_topic)
        normalized_pairing_session_id = self._normalize_optional_text(pairing_session_id)

        c, close = self._use_conn(conn)
        try:
            now = time.time()
            c.execute(
                """
                INSERT INTO agents(
                    agent_id,
                    name,
                    icon,
                    transport,
                    status,
                    can_send,
                    can_learn,
                    sw_version,
                    agent_topic,
                    configuration_url,
                    pending,
                    pairing_session_id,
                    last_seen,
                    created_at,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    name = excluded.name,
                    icon = COALESCE(excluded.icon, agents.icon),
                    transport = excluded.transport,
                    status = excluded.status,
                    can_send = excluded.can_send,
                    can_learn = excluded.can_learn,
                    sw_version = excluded.sw_version,
                    agent_topic = excluded.agent_topic,
                    configuration_url = COALESCE(excluded.configuration_url, agents.configuration_url),
                    pending = excluded.pending,
                    pairing_session_id = excluded.pairing_session_id,
                    last_seen = excluded.last_seen,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_agent_id,
                    normalized_name,
                    normalized_icon,
                    transport,
                    status,
                    self._to_int_bool(can_send),
                    self._to_int_bool(can_learn),
                    normalized_sw_version,
                    normalized_agent_topic,
                    normalized_url,
                    self._to_int_bool(pending),
                    normalized_pairing_session_id,
                    last_seen,
                    now,
                    now,
                ),
            )
            c.commit()
            row = c.execute("SELECT * FROM agents WHERE agent_id = ?", (normalized_agent_id,)).fetchone()
            if not row:
                raise ValueError("Failed to upsert agent")
            return self._row_to_dict(row)
        finally:
            if close:
                c.close()

    def update_agent(
        self,
        agent_id: str,
        changes: Dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            raise ValueError("agent_id must not be empty")

        c, close = self._use_conn(conn)
        try:
            existing = c.execute("SELECT * FROM agents WHERE agent_id = ?", (normalized_agent_id,)).fetchone()
            if not existing:
                raise ValueError("Unknown agent_id")

            existing_data = self._row_to_dict(existing)
            next_name = existing_data.get("name")
            next_icon = existing_data.get("icon")
            next_configuration_url = existing_data.get("configuration_url")

            if "name" in changes:
                next_name = self._normalize_name(changes.get("name"))
            if "icon" in changes:
                next_icon = self._normalize_icon(changes.get("icon"))
            if "configuration_url" in changes:
                next_configuration_url = self._normalize_configuration_url(changes.get("configuration_url"))

            now = time.time()
            c.execute(
                "UPDATE agents SET name = ?, icon = ?, configuration_url = ?, updated_at = ? WHERE agent_id = ?",
                (next_name, next_icon, next_configuration_url, now, normalized_agent_id),
            )
            c.commit()

            row = c.execute("SELECT * FROM agents WHERE agent_id = ?", (normalized_agent_id,)).fetchone()
            if not row:
                raise ValueError("Unknown agent_id")
            return self._row_to_dict(row)
        finally:
            if close:
                c.close()

    def set_status(
        self,
        agent_id: str,
        status: str,
        last_seen: Optional[float] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return
        c, close = self._use_conn(conn)
        try:
            now = time.time()
            c.execute(
                "UPDATE agents SET status = ?, last_seen = ?, updated_at = ? WHERE agent_id = ?",
                (status, last_seen, now, normalized_agent_id),
            )
            c.commit()
        finally:
            if close:
                c.close()

    def update_last_seen(self, agent_id: str, last_seen: Optional[float], conn: Optional[sqlite3.Connection] = None) -> None:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return
        c, close = self._use_conn(conn)
        try:
            now = time.time()
            c.execute(
                "UPDATE agents SET last_seen = ?, updated_at = ? WHERE agent_id = ?",
                (last_seen, now, normalized_agent_id),
            )
            c.commit()
        finally:
            if close:
                c.close()

    def get(self, agent_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return None
        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT * FROM agents WHERE agent_id = ?", (normalized_agent_id,)).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            if close:
                c.close()

    def list(self, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            rows = c.execute("SELECT * FROM agents ORDER BY name, agent_id").fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            if close:
                c.close()

    def set_pending_state(
        self,
        agent_id: str,
        pending: bool,
        pairing_session_id: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            raise ValueError("agent_id must not be empty")

        normalized_pairing_session_id = self._normalize_optional_text(pairing_session_id)
        if not pending:
            normalized_pairing_session_id = None

        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT * FROM agents WHERE agent_id = ?", (normalized_agent_id,)).fetchone()
            if not row:
                raise ValueError("Unknown agent_id")

            now = time.time()
            c.execute(
                "UPDATE agents SET pending = ?, pairing_session_id = ?, updated_at = ? WHERE agent_id = ?",
                (self._to_int_bool(pending), normalized_pairing_session_id, now, normalized_agent_id),
            )
            c.commit()
            updated = c.execute("SELECT * FROM agents WHERE agent_id = ?", (normalized_agent_id,)).fetchone()
            if not updated:
                raise ValueError("Unknown agent_id")
            return self._row_to_dict(updated)
        finally:
            if close:
                c.close()

    def delete_pending(self, pairing_session_id: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> int:
        c, close = self._use_conn(conn)
        try:
            if pairing_session_id:
                result = c.execute(
                    "DELETE FROM agents WHERE pending = 1 AND pairing_session_id = ?",
                    (str(pairing_session_id),),
                )
            else:
                result = c.execute("DELETE FROM agents WHERE pending = 1")
            c.commit()
            return int(result.rowcount or 0)
        finally:
            if close:
                c.close()

    def delete(self, agent_id: str, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            raise ValueError("agent_id must not be empty")

        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT * FROM agents WHERE agent_id = ?", (normalized_agent_id,)).fetchone()
            if not row:
                raise ValueError("Unknown agent_id")
            c.execute("DELETE FROM agents WHERE agent_id = ?", (normalized_agent_id,))
            c.commit()
            return self._row_to_dict(row)
        finally:
            if close:
                c.close()

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        can_send = bool(data.get("can_send"))
        can_learn = bool(data.get("can_learn"))
        pending = bool(data.get("pending"))
        data["can_send"] = can_send
        data["can_learn"] = can_learn
        data["pending"] = pending
        data["capabilities"] = {
            "can_send": can_send,
            "can_learn": can_learn,
        }
        return data

    def _normalize_name(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized

    def _normalize_icon(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        return normalized

    def _normalize_configuration_url(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized

    def _normalize_optional_text(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        return normalized

    def _to_int_bool(self, value: bool) -> int:
        return 1 if bool(value) else 0
