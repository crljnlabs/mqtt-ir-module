import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from database.database_base import DatabaseBase


class Logs(DatabaseBase):
    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          REAL    NOT NULL,
                level       TEXT    NOT NULL,
                source_type TEXT    NOT NULL,
                source_id   TEXT,
                category    TEXT,
                message     TEXT    NOT NULL,
                request_id  TEXT,
                error_code  TEXT,
                meta        TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_logs_ts     ON logs(ts);
            CREATE INDEX IF NOT EXISTS idx_logs_source ON logs(source_type, source_id);
            """
        )

    def insert(
        self,
        source_type: str,
        source_id: Optional[str],
        event: Dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        c, close = self._use_conn(conn)
        try:
            meta = event.get("meta")
            meta_json = json.dumps(meta, separators=(",", ":")) if meta else None
            c.execute(
                """
                INSERT INTO logs(ts, level, source_type, source_id, category, message, request_id, error_code, meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    float(event.get("ts") or time.time()),
                    str(event.get("level") or "info"),
                    str(source_type),
                    str(source_id) if source_id else None,
                    str(event.get("category") or "runtime"),
                    str(event.get("message") or ""),
                    str(event.get("request_id") or "") or None,
                    str(event.get("error_code") or "") or None,
                    meta_json,
                ),
            )
            c.commit()
        finally:
            if close:
                c.close()

    def query(
        self,
        levels: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        source_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        limit: int = 200,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            where, params = self._build_where(levels, source_types, source_ids, categories, from_ts, to_ts)
            bounded = max(1, min(int(limit or 0), 1000))
            sql = f"SELECT * FROM logs{where} ORDER BY ts ASC LIMIT ?"
            params.append(bounded)
            rows = c.execute(sql, params).fetchall()
            return [self._row_to_dict(row) for row in rows]
        finally:
            if close:
                c.close()

    def delete(
        self,
        levels: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        source_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> int:
        c, close = self._use_conn(conn)
        try:
            where, params = self._build_where(levels, source_types, source_ids, categories, from_ts, to_ts)
            sql = f"DELETE FROM logs{where}"
            cursor = c.execute(sql, params)
            c.commit()
            return cursor.rowcount
        finally:
            if close:
                c.close()

    def prune(self, retention_days: int, conn: Optional[sqlite3.Connection] = None) -> int:
        cutoff = time.time() - max(0, int(retention_days)) * 86400
        c, close = self._use_conn(conn)
        try:
            cursor = c.execute("DELETE FROM logs WHERE ts < ?", (cutoff,))
            c.commit()
            return cursor.rowcount
        finally:
            if close:
                c.close()

    def _build_where(
        self,
        levels: Optional[List[str]],
        source_types: Optional[List[str]],
        source_ids: Optional[List[str]],
        categories: Optional[List[str]],
        from_ts: Optional[float],
        to_ts: Optional[float],
    ):
        clauses = []
        params = []

        if levels:
            placeholders = ",".join("?" * len(levels))
            clauses.append(f"level IN ({placeholders})")
            params.extend(levels)

        if source_types:
            placeholders = ",".join("?" * len(source_types))
            clauses.append(f"source_type IN ({placeholders})")
            params.extend(source_types)

        if source_ids:
            placeholders = ",".join("?" * len(source_ids))
            clauses.append(f"source_id IN ({placeholders})")
            params.extend(source_ids)

        if categories:
            placeholders = ",".join("?" * len(categories))
            clauses.append(f"category IN ({placeholders})")
            params.extend(categories)

        if from_ts is not None:
            clauses.append("ts >= ?")
            params.append(float(from_ts))

        if to_ts is not None:
            clauses.append("ts <= ?")
            params.append(float(to_ts))

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, params

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "id": row["id"],
            "ts": row["ts"],
            "level": row["level"],
            "source_type": row["source_type"],
            "source_id": row["source_id"],
            "category": row["category"],
            "message": row["message"],
        }
        if row["request_id"]:
            entry["request_id"] = row["request_id"]
        if row["error_code"]:
            entry["error_code"] = row["error_code"]
        if row["meta"]:
            try:
                entry["meta"] = json.loads(row["meta"])
            except Exception:
                pass
        return entry
