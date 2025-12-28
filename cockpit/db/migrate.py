from __future__ import annotations

import sqlite3
from pathlib import Path


def _read_schema_sql() -> str:
    schema_path = Path(__file__).with_name("schema.sql")
    return schema_path.read_text(encoding="utf-8")


def initialize_database(conn: sqlite3.Connection) -> None:
    conn.executescript(_read_schema_sql())

    session_cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "last_seen_at" not in session_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN last_seen_at TEXT;")
        conn.execute("UPDATE sessions SET last_seen_at = logged_in_at WHERE last_seen_at IS NULL;")

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(fight_matches)").fetchall()}
    if "fight_number" not in cols:
        conn.execute("ALTER TABLE fight_matches ADD COLUMN fight_number INTEGER UNIQUE;")

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sessions_active_user
        ON sessions(user_id)
        WHERE logged_out_at IS NULL
        """
    )

    conn.execute(
        """
        INSERT OR IGNORE INTO fight_structures(code, name, cocks_per_entry, default_rounds, is_active, created_at)
        VALUES
          ('SINGLE', 'Single Cock', 1, 1, 1, datetime('now')),
          ('DERBY_2', '2-Cock Derby', 2, 1, 1, datetime('now')),
          ('DERBY_3', '3-Cock Derby', 3, 1, 1, datetime('now')),
          ('DERBY_5', '5-Cock Derby', 5, 1, 1, datetime('now'))
        """
    )
