"""Sign-in for the web app: a few fixed accounts, no sign-up and no password reset.

Passwords are never stored: only a salted PBKDF2 hash. A sign-in gives a random token that lives in an
HttpOnly cookie; the database keeps only the hash of the token, so a copy of the database cannot be used to sign in.
"""
import hashlib
import hmac
import secrets
import time

ITERATIONS = 200_000
DUMMY_SALT = "00" * 16          # used for unknown emails, so a wrong email takes as long as a wrong password

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    email         TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL,          -- employee | admin
    salt          TEXT NOT NULL,
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
"""


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return salt.hex(), digest.hex()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Accounts:
    def __init__(self, db, session_hours: float = 12.0, max_failures: int = 5, lock_seconds: int = 60) -> None:
        self.db = db
        self.session_seconds = session_hours * 3600
        self.max_failures = max_failures
        self.lock_seconds = lock_seconds
        self._failures: dict[str, list[float]] = {}     # recent wrong passwords per email, in memory
        db.executescript(SCHEMA)
        # Migration: add columns that did not exist in the first version of the schema.
        for col, dflt in (("salt", "''"), ("password_hash", "''"), ("role", "'employee'"), ("name", "''")):
            try:
                db.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT NOT NULL DEFAULT {dflt}")
                db.commit()
            except Exception:
                pass   # column already exists

    def seed(self, accounts: list[dict]) -> None:
        """Create or update the fixed accounts at start-up. Changing a password in .env takes effect after a restart."""
        with self.db:
            for a in accounts:
                salt, digest = hash_password(a["password"])
                self.db.execute(
                    "INSERT INTO users (email, name, role, salt, password_hash) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(email) DO UPDATE SET name = excluded.name, role = excluded.role, "
                    "salt = excluded.salt, password_hash = excluded.password_hash",
                    (a["email"].lower(), a["name"], a["role"], salt, digest))

    def login(self, email: str, password: str) -> tuple[str | None, str | None]:
        """Returns (token, None) when the password is right, or (None, "bad_credentials" | "locked")."""
        email = (email or "").strip().lower()
        now = time.time()
        recent = [t for t in self._failures.get(email, []) if now - t < self.lock_seconds]
        self._failures[email] = recent
        if len(recent) >= self.max_failures:              # too many wrong passwords: wait a minute
            return None, "locked"

        row = self.db.execute("SELECT salt, password_hash FROM users WHERE email = ?", (email,)).fetchone()
        salt_hex, expected = row if row else (DUMMY_SALT, "0" * 64)
        _, digest = hash_password(password or "", bytes.fromhex(salt_hex))
        if row is None or not hmac.compare_digest(digest, expected):
            self._failures[email].append(now)
            return None, "bad_credentials"               # the same answer for a wrong email and a wrong password

        self._failures.pop(email, None)
        token = secrets.token_urlsafe(32)
        with self.db:
            self.db.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (now,))
            self.db.execute("INSERT INTO auth_sessions (token_hash, email, created_at, expires_at) VALUES (?, ?, ?, ?)",
                            (_token_hash(token), email, now, now + self.session_seconds))
        return token, None

    def user_for_token(self, token: str | None) -> dict | None:
        if not token:
            return None
        row = self.db.execute(
            "SELECT u.email, u.name, u.role FROM auth_sessions s JOIN users u ON u.email = s.email "
            "WHERE s.token_hash = ? AND s.expires_at > ?", (_token_hash(token), time.time())).fetchone()
        return {"email": row[0], "name": row[1], "role": row[2]} if row else None

    def logout(self, token: str | None) -> None:
        if token:
            with self.db:
                self.db.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(token),))

    def list_users(self) -> list[dict]:
        rows = self.db.execute("SELECT email, name, role FROM users ORDER BY role, name").fetchall()
        return [{"email": r[0], "name": r[1], "role": r[2]} for r in rows]