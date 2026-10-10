"""linxiv-web's own small state, kept across restarts: `<data dir>/linxiv-web-state.db`.

Separate from linXiv's papers.db (which only the CLI touches) and from the
linxiv settings store. Holds login failures for the throttle, sessions (by
SHA-256 of their id) and the session signing key. Opened per call
(one short transaction each), so it is safe from the threadpool.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path

STATE_FILE = "linxiv-web-state.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS login_failures (
    client TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS login_failures_client ON login_failures (client, at);
CREATE TABLE IF NOT EXISTS sessions (
    sid_hash TEXT PRIMARY KEY,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _sid_hash(sid: str) -> str:
    # Only the hash is stored: a copied state file can't be turned into a cookie.
    return hashlib.sha256(sid.encode()).hexdigest()


class StateDB:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / STATE_FILE
        if not self.path.exists():
            # Create owner-only before sqlite opens it.
            os.close(os.open(self.path, os.O_WRONLY | os.O_CREAT, 0o600))
        with closing(self._connect()) as db, db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA busy_timeout = 5000")
        return db

    # --- login throttle ---

    def failures_since(self, client: str, cutoff: float) -> int:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT COUNT(*) FROM login_failures WHERE client = ? AND at >= ?",
                (client, cutoff),
            ).fetchone()
        return int(row[0])

    def add_failure(self, client: str, at: float, prune_before: float) -> None:
        """Record one failure; drop every client's failures older than `prune_before`."""
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM login_failures WHERE at < ?", (prune_before,))
            db.execute("INSERT INTO login_failures (client, at) VALUES (?, ?)", (client, at))

    def clear_failures(self, client: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM login_failures WHERE client = ?", (client,))

    # --- sessions ---

    def secret_key(self) -> str:
        """Session signing key, generated on first use and kept, so restarts keep logins."""
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('session_key', ?)",
                (secrets.token_urlsafe(48),),
            )
            return db.execute("SELECT value FROM meta WHERE key = 'session_key'").fetchone()[0]

    def add_session(self, sid: str, expires: float, now: float) -> None:
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (now,))
            db.execute(
                "INSERT INTO sessions (sid_hash, expires) VALUES (?, ?)", (_sid_hash(sid), expires)
            )

    def session_expiry(self, sid: str) -> float | None:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT expires FROM sessions WHERE sid_hash = ?", (_sid_hash(sid),)
            ).fetchone()
        return float(row[0]) if row else None

    def drop_session(self, sid: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM sessions WHERE sid_hash = ?", (_sid_hash(sid),))

    def drop_other_sessions(self, keep_sid: str | None) -> int:
        keep = _sid_hash(keep_sid) if keep_sid else ""
        with closing(self._connect()) as db, db:
            return db.execute("DELETE FROM sessions WHERE sid_hash != ?", (keep,)).rowcount

    def drop_all_sessions(self) -> int:
        with closing(self._connect()) as db, db:
            return db.execute("DELETE FROM sessions").rowcount
