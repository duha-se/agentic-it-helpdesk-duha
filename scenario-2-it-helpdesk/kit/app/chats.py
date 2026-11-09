"""Saved conversations for the web app: the list in the sidebar and the messages of each chat.

The agent keeps its own short memory (app/store.py). This file keeps what the employee SEES: the whole
transcript, so an old chat can be opened and continued. A conversation id is also the agent's session id.
"""
import json
import time
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY,
    email      TEXT NOT NULL,          -- the owner: nobody else can open it
    title      TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS conversations_owner ON conversations (email, updated_at);
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,     -- user | assistant
    content         TEXT NOT NULL,
    meta            TEXT,              -- citations, draft, result, tool calls as JSON
    at              REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_conversation ON messages (conversation_id, id);
"""


class Chats:
    def __init__(self, db) -> None:
        self.db = db
        db.executescript(SCHEMA)

    def create(self, email: str) -> str:
        cid = "c-" + uuid.uuid4().hex[:12]
        now = time.time()
        with self.db:
            self.db.execute("INSERT INTO conversations (id, email, title, created_at, updated_at) VALUES (?, ?, '', ?, ?)",
                            (cid, email, now, now))
        return cid

    def get(self, cid: str, email: str) -> dict | None:
        """The conversation, but only for its owner."""
        row = self.db.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id = ? AND email = ?",
                              (cid, email)).fetchone()
        return {"id": row[0], "title": row[1] or "New chat", "created_at": row[2], "updated_at": row[3]} if row else None

    def list_for(self, email: str, limit: int = 60, all_users: bool = False) -> list[dict]:
        if all_users:
            rows = self.db.execute("SELECT id, title, created_at, updated_at, email FROM conversations "
                                   "WHERE title != '' ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            return [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3], "owner": r[4]} for r in rows]
        rows = self.db.execute("SELECT id, title, created_at, updated_at FROM conversations "
                               "WHERE email = ? AND title != '' ORDER BY updated_at DESC LIMIT ?", (email, limit)).fetchall()
        return [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

    def set_title_if_empty(self, cid: str, text: str) -> None:
        title = " ".join(text.split())[:48]
        with self.db:
            self.db.execute("UPDATE conversations SET title = ? WHERE id = ? AND title = ''", (title, cid))

    def add_message(self, cid: str, role: str, content: str, meta: dict | None = None) -> None:
        now = time.time()
        with self.db:
            self.db.execute("INSERT INTO messages (conversation_id, role, content, meta, at) VALUES (?, ?, ?, ?, ?)",
                            (cid, role, content, json.dumps(meta) if meta else None, now))
            self.db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid))

    def messages(self, cid: str) -> list[dict]:
        rows = self.db.execute("SELECT role, content, meta, at FROM messages WHERE conversation_id = ? ORDER BY id", (cid,)).fetchall()
        return [{"role": r[0], "content": r[1], "meta": json.loads(r[2]) if r[2] else {}, "at": r[3]} for r in rows]

    def counts_by_user(self) -> dict[str, int]:
        rows = self.db.execute("SELECT email, COUNT(*) FROM conversations WHERE title != '' GROUP BY email").fetchall()
        return {r[0]: r[1] for r in rows}