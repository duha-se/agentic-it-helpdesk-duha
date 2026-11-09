"""A small SQLite file for two things the agent must not lose on a restart.

  sessions: the conversation state (history, the draft waiting for approval, approvals already done)
  audit:    one row for every decision about a ticket (drafted, approved, rejected, created, failed)

SQLite is built into Python (the sqlite3 module): no server and nothing to install. The data is one file.
The ticket system is NOT replaced by this file: tickets live in the helpdesk system, which is the source of truth.
"""
import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    data       TEXT NOT NULL,          -- the session snapshot as JSON
    updated_at REAL NOT NULL           -- unix time, used to delete old sessions
);
CREATE TABLE IF NOT EXISTS audit (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    at         REAL NOT NULL,
    session_id TEXT NOT NULL,
    action_id  TEXT,
    event      TEXT NOT NULL,          -- draft_created | approved | rejected | ticket_created | creation_failed | ...
    detail     TEXT                    -- extra facts as JSON (priority, ticket id, error code)
);
CREATE INDEX IF NOT EXISTS audit_action ON audit (action_id);
"""


class Store:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # One process uses this file, and every call is a few milliseconds, so one shared connection is enough.
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(SCHEMA)

    def save_session(self, session_id: str, snapshot: dict) -> None:
        with self.db:                                    # "with" commits the change
            self.db.execute("INSERT OR REPLACE INTO sessions (session_id, data, updated_at) VALUES (?, ?, ?)",
                            (session_id, json.dumps(snapshot), time.time()))

    def load_session(self, session_id: str) -> dict | None:
        row = self.db.execute("SELECT data FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def log(self, session_id: str, event: str, action_id: str | None = None, **detail) -> None:
        with self.db:
            self.db.execute("INSERT INTO audit (at, session_id, action_id, event, detail) VALUES (?, ?, ?, ?, ?)",
                            (time.time(), session_id, action_id, event, json.dumps(detail) if detail else None))

    def events(self, action_id: str) -> list[str]:
        """The events of one draft, oldest first. Handy in tests and when you explain what happened."""
        rows = self.db.execute("SELECT event FROM audit WHERE action_id = ? ORDER BY id", (action_id,)).fetchall()
        return [r[0] for r in rows]

    def recent_events(self, limit: int = 50) -> list[dict]:
        rows = self.db.execute("SELECT at, session_id, action_id, event, detail FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"at": r[0], "session_id": r[1], "action_id": r[2], "event": r[3], "detail": json.loads(r[4]) if r[4] else {}} for r in rows]

    def count_events(self, event: str) -> int:
        return self.db.execute("SELECT COUNT(*) FROM audit WHERE event = ?", (event,)).fetchone()[0]

    def purge_older_than(self, days: float) -> int:
        with self.db:
            cur = self.db.execute("DELETE FROM sessions WHERE updated_at < ?", (time.time() - days * 86400,))
        return cur.rowcount
    def user_role(self, email: str | None) -> str | None:
        """Role of an account in the users table (created by Accounts). None if unknown."""
        try:
            row = self.db.execute("SELECT role FROM users WHERE email = ?",
                                  ((email or "").strip().lower(),)).fetchone()
        except sqlite3.OperationalError:          # users table not created yet
            return None
        return row[0] if row else None
    
    def close(self) -> None:
        self.db.close()
