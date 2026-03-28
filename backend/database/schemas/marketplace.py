import sqlite3
import time
from typing import Any, Dict, List, Optional

from database.database_base import DatabaseBase


class Marketplace(DatabaseBase):

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS marketplace_remotes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                source     TEXT NOT NULL,
                path       TEXT NOT NULL UNIQUE,
                category   TEXT NOT NULL,
                brand      TEXT NOT NULL,
                model      TEXT NOT NULL,
                sha        TEXT NOT NULL,
                synced_at  REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_marketplace_remotes_category
                ON marketplace_remotes(category);

            CREATE TABLE IF NOT EXISTS marketplace_buttons (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                remote_id   INTEGER NOT NULL,
                name        TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                protocol    TEXT NULL,
                FOREIGN KEY(remote_id) REFERENCES marketplace_remotes(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS ix_marketplace_buttons_remote_id
                ON marketplace_buttons(remote_id);

            CREATE TABLE IF NOT EXISTS marketplace_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

    # ------------------------------------------------------------------
    # Sync helpers
    # ------------------------------------------------------------------

    def get_meta(self, key: str, conn: Optional[sqlite3.Connection] = None) -> Optional[str]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT value FROM marketplace_meta WHERE key = ?", (key,)).fetchone()
            return row[0] if row else None
        finally:
            if close:
                c.close()

    def set_meta(self, key: str, value: str, conn: Optional[sqlite3.Connection] = None) -> None:
        c, close = self._use_conn(conn)
        try:
            c.execute(
                "INSERT INTO marketplace_meta(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            c.commit()
        finally:
            if close:
                c.close()

    def count(self, conn: Optional[sqlite3.Connection] = None) -> int:
        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT COUNT(*) FROM marketplace_remotes").fetchone()
            return int(row[0]) if row else 0
        finally:
            if close:
                c.close()

    def list_paths_and_shas(
        self,
        source: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            if source:
                rows = c.execute(
                    "SELECT path, sha FROM marketplace_remotes WHERE source = ?", (source,)
                ).fetchall()
            else:
                rows = c.execute("SELECT path, sha FROM marketplace_remotes").fetchall()
            return [dict(r) for r in rows]
        finally:
            if close:
                c.close()

    def delete_by_paths(self, paths: List[str], conn: Optional[sqlite3.Connection] = None) -> None:
        c, close = self._use_conn(conn)
        try:
            for path in paths:
                c.execute("DELETE FROM marketplace_remotes WHERE path = ?", (path,))
            c.commit()
        finally:
            if close:
                c.close()

    def upsert(
        self,
        source: str,
        path: str,
        category: str,
        brand: str,
        model: str,
        sha: str,
        buttons: List[Dict[str, Any]],
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Insert or update a marketplace remote and replace its buttons."""
        c, close = self._use_conn(conn)
        try:
            now = time.time()
            existing = c.execute(
                "SELECT id FROM marketplace_remotes WHERE path = ?", (path,)
            ).fetchone()

            if existing:
                remote_id = existing[0]
                c.execute("DELETE FROM marketplace_buttons WHERE remote_id = ?", (remote_id,))
                c.execute(
                    "UPDATE marketplace_remotes SET source=?, category=?, brand=?, model=?, sha=?, synced_at=? WHERE id=?",
                    (source, category, brand, model, sha, now, remote_id),
                )
            else:
                cursor = c.execute(
                    "INSERT INTO marketplace_remotes(source, path, category, brand, model, sha, synced_at) VALUES(?,?,?,?,?,?,?)",
                    (source, path, category, brand, model, sha, now),
                )
                remote_id = cursor.lastrowid

            for btn in buttons:
                signal_type = btn.get("type", "raw")
                protocol = btn.get("protocol") if signal_type == "parsed" else None
                c.execute(
                    "INSERT INTO marketplace_buttons(remote_id, name, signal_type, protocol) VALUES(?,?,?,?)",
                    (remote_id, btn.get("name", ""), signal_type, protocol),
                )

            c.commit()
        finally:
            if close:
                c.close()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        q: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        source: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        conditions: List[str] = []
        params: List[Any] = []

        if q:
            q_lower = f"%{q.lower()}%"
            conditions.append("(LOWER(brand) LIKE ? OR LOWER(model) LIKE ?)")
            params.extend([q_lower, q_lower])
        if category:
            conditions.append("category = ?")
            params.append(category)
        if brand:
            conditions.append("brand = ?")
            params.append(brand)
        if source:
            conditions.append("source = ?")
            params.append(source)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        c, close = self._use_conn(conn)
        try:
            remotes = c.execute(
                f"SELECT * FROM marketplace_remotes {where} ORDER BY brand, model",
                params,
            ).fetchall()

            result: List[Dict[str, Any]] = []
            for remote in remotes:
                remote_dict = dict(remote)
                btns = c.execute(
                    "SELECT id, name, signal_type, protocol FROM marketplace_buttons WHERE remote_id = ? ORDER BY name",
                    (remote_dict["id"],),
                ).fetchall()
                remote_dict["buttons"] = [dict(b) for b in btns]
                result.append(remote_dict)

            return result
        finally:
            if close:
                c.close()

    def get_by_path(self, path: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute("SELECT * FROM marketplace_remotes WHERE path = ?", (path,)).fetchone()
            return dict(row) if row else None
        finally:
            if close:
                c.close()

    def list_categories(self, conn: Optional[sqlite3.Connection] = None) -> List[str]:
        c, close = self._use_conn(conn)
        try:
            rows = c.execute(
                "SELECT DISTINCT category FROM marketplace_remotes ORDER BY category"
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            if close:
                c.close()

    def list_brands(
        self, category: Optional[str] = None, conn: Optional[sqlite3.Connection] = None
    ) -> List[str]:
        c, close = self._use_conn(conn)
        try:
            if category:
                rows = c.execute(
                    "SELECT DISTINCT brand FROM marketplace_remotes WHERE category = ? ORDER BY brand",
                    (category,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT DISTINCT brand FROM marketplace_remotes ORDER BY brand"
                ).fetchall()
            return [r[0] for r in rows]
        finally:
            if close:
                c.close()
