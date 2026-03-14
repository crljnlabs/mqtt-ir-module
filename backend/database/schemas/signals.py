import sqlite3
import time
from typing import Optional, Dict, Any

from database.database_base import DatabaseBase


class Signals(DatabaseBase):

    # -----------------------------
    # Schema / migrations
    # -----------------------------

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS button_signals (
                button_id INTEGER PRIMARY KEY,
                encoding TEXT NOT NULL,
                press_initial TEXT NULL,
                press_repeat TEXT NULL,
                hold_initial TEXT NULL,
                hold_repeat TEXT NULL,
                hold_gap_us INTEGER NULL,
                sample_count_press INTEGER NOT NULL,
                sample_count_hold INTEGER NOT NULL,
                quality_score_press REAL NULL,
                quality_score_hold REAL NULL,

                -- Protocol fields. Populated for encoding='protocol' signals.
                -- A later decoder component may also fill these for captured raw signals.
                protocol TEXT NULL,
                address TEXT NULL,
                command_hex TEXT NULL,
                decode_confidence REAL NULL,

                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(button_id) REFERENCES buttons(id) ON DELETE CASCADE
            );
            """
        )

    # -----------------------------
    # Signals
    # -----------------------------
    def list_by_button(self, button_id: int, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        c, close = self._use_conn(conn)
        try:
            row = c.execute(
                "SELECT * FROM button_signals WHERE button_id = ?",
                (button_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            if close:
                c.close()

    def upsert_press(
        self,
        button_id: int,
        press_initial: str,
        press_repeat: Optional[str],
        sample_count_press: int,
        quality_score_press: Optional[float],
        encoding: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        press_initial = press_initial.strip()
        if not press_initial:
            raise ValueError("press_initial must not be empty")
        if sample_count_press <= 0:
            raise ValueError("sample_count_press must be > 0")

        c, close = self._use_conn(conn)
        try:
            now = time.time()
            existing = c.execute(
                "SELECT button_id FROM button_signals WHERE button_id = ?",
                (button_id,),
            ).fetchone()

            if existing:
                c.execute(
                    """
                    UPDATE button_signals
                    SET encoding = ?,
                        press_initial = ?,
                        press_repeat = ?,
                        sample_count_press = ?,
                        quality_score_press = ?,
                        updated_at = ?
                    WHERE button_id = ?
                    """,
                    (encoding, press_initial, press_repeat, sample_count_press, quality_score_press, now, button_id),
                )
            else:
                c.execute(
                    """
                    INSERT INTO button_signals(
                        button_id,
                        encoding,
                        press_initial,
                        press_repeat,
                        hold_initial,
                        hold_repeat,
                        hold_gap_us,
                        sample_count_press,
                        sample_count_hold,
                        quality_score_press,
                        quality_score_hold,
                        protocol,
                        address,
                        command_hex,
                        decode_confidence,
                        created_at,
                        updated_at
                    )
                    VALUES(?, ?, ?, ?, NULL, NULL, NULL, ?, 0, ?, NULL, NULL, NULL, NULL, NULL, ?, ?)
                    """,
                    (button_id, encoding, press_initial, press_repeat, sample_count_press, quality_score_press, now, now),
                )

            c.commit()
            out = c.execute("SELECT * FROM button_signals WHERE button_id = ?", (button_id,)).fetchone()
            if not out:
                raise ValueError("Failed to upsert press signal")
            return dict(out)
        finally:
            if close:
                c.close()

    def upsert_protocol(
        self,
        button_id: int,
        protocol: str,
        address: str,
        command_hex: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        """Store a protocol-encoded IR signal (NEC, Samsung32, etc.)."""
        protocol = protocol.strip()
        address = address.strip()
        command_hex = command_hex.strip()
        if not protocol or not address or not command_hex:
            raise ValueError("protocol, address, and command_hex must not be empty")

        c, close = self._use_conn(conn)
        try:
            now = time.time()
            existing = c.execute(
                "SELECT button_id FROM button_signals WHERE button_id = ?",
                (button_id,),
            ).fetchone()

            if existing:
                c.execute(
                    """
                    UPDATE button_signals
                    SET encoding = 'protocol',
                        press_initial = NULL,
                        press_repeat = NULL,
                        sample_count_press = 0,
                        quality_score_press = NULL,
                        protocol = ?,
                        address = ?,
                        command_hex = ?,
                        updated_at = ?
                    WHERE button_id = ?
                    """,
                    (protocol, address, command_hex, now, button_id),
                )
            else:
                c.execute(
                    """
                    INSERT INTO button_signals(
                        button_id,
                        encoding,
                        press_initial,
                        press_repeat,
                        hold_initial,
                        hold_repeat,
                        hold_gap_us,
                        sample_count_press,
                        sample_count_hold,
                        quality_score_press,
                        quality_score_hold,
                        protocol,
                        address,
                        command_hex,
                        decode_confidence,
                        created_at,
                        updated_at
                    )
                    VALUES(?, 'protocol', NULL, NULL, NULL, NULL, NULL, 0, 0, NULL, NULL, ?, ?, ?, NULL, ?, ?)
                    """,
                    (button_id, protocol, address, command_hex, now, now),
                )

            c.commit()
            out = c.execute("SELECT * FROM button_signals WHERE button_id = ?", (button_id,)).fetchone()
            if not out:
                raise ValueError("Failed to upsert protocol signal")
            return dict(out)
        finally:
            if close:
                c.close()

    def update_hold(
        self,
        button_id: int,
        hold_initial: str,
        hold_repeat: Optional[str],
        hold_gap_us: Optional[int],
        sample_count_hold: int,
        quality_score_hold: Optional[float],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        hold_initial = hold_initial.strip()
        if not hold_initial:
            raise ValueError("hold_initial must not be empty")
        if sample_count_hold <= 0:
            raise ValueError("sample_count_hold must be > 0")

        c, close = self._use_conn(conn)
        try:
            existing = c.execute(
                "SELECT button_id FROM button_signals WHERE button_id = ?",
                (button_id,),
            ).fetchone()
            if not existing:
                raise ValueError("Press signal must be captured before hold")

            now = time.time()
            c.execute(
                """
                UPDATE button_signals
                SET hold_initial = ?,
                    hold_repeat = ?,
                    hold_gap_us = ?,
                    sample_count_hold = ?,
                    quality_score_hold = ?,
                    updated_at = ?
                WHERE button_id = ?
                """,
                (hold_initial, hold_repeat, hold_gap_us, sample_count_hold, quality_score_hold, now, button_id),
            )
            c.commit()

            out = c.execute("SELECT * FROM button_signals WHERE button_id = ?", (button_id,)).fetchone()
            if not out:
                raise ValueError("Unknown button_id")
            return dict(out)
        finally:
            if close:
                c.close()
