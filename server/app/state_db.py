"""linxiv-web's own small state, kept across restarts: `<data dir>/linxiv-web-state.db`.

Separate from linXiv's papers.db (which only the CLI touches) and from the
linxiv settings store. Holds login failures for the throttle, sessions (by
SHA-256 of their id), the session signing key, the multi-user switch and the
user accounts. Opened per call (one short transaction each), so it is safe
from the threadpool.

The server owner's account (`library = 'root'`) keeps no hash of its own: it
logs in with the server password (env or first-run setup), as in single-user mode.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATE_FILE = "linxiv-web-state.db"
OWNER_LIBRARY = "root"
USER_FIELDS = ("id", "username", "role", "library", "created_at")

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
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    library TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
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
            cols = {r[1] for r in db.execute("PRAGMA table_info(sessions)")}
            if "user_id" not in cols:
                # NULL = single-user session, which belongs to the server owner.
                db.execute("ALTER TABLE sessions ADD COLUMN user_id INTEGER")

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

    def add_session(self, sid: str, expires: float, now: float, user_id: int | None = None) -> None:
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (now,))
            db.execute(
                "INSERT INTO sessions (sid_hash, expires, user_id) VALUES (?, ?, ?)",
                (_sid_hash(sid), expires, user_id),
            )

    def session_expiry(self, sid: str) -> float | None:
        row = self.session(sid)
        return row[0] if row else None

    def session(self, sid: str) -> tuple[float, int | None] | None:
        """(expires, user_id) of a live session row, None when there is none."""
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT expires, user_id FROM sessions WHERE sid_hash = ?", (_sid_hash(sid),)
            ).fetchone()
        return (float(row[0]), row[1]) if row else None

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

    def drop_user_sessions(self, user_id: int, keep_sid: str | None = None) -> int:
        """End one account's sessions (all but `keep_sid`). The owner's account also
        holds the user-less single-user sessions."""
        keep = _sid_hash(keep_sid) if keep_sid else ""
        with closing(self._connect()) as db, db:
            owner = db.execute(
                "SELECT 1 FROM users WHERE id = ? AND library = ?", (user_id, OWNER_LIBRARY)
            ).fetchone()
            who = "(user_id = ? OR user_id IS NULL)" if owner else "user_id = ?"
            return db.execute(
                f"DELETE FROM sessions WHERE {who} AND sid_hash != ?",  # noqa: S608
                (user_id, keep),
            ).rowcount

    def drop_sessions_except_owner(self) -> int:
        with closing(self._connect()) as db, db:
            return db.execute(
                "DELETE FROM sessions WHERE user_id IS NOT NULL AND user_id NOT IN "
                "(SELECT id FROM users WHERE library = ?)",
                (OWNER_LIBRARY,),
            ).rowcount

    # --- multi-user mode ---

    def multi_user_enabled(self) -> bool:
        with closing(self._connect()) as db:
            row = db.execute("SELECT value FROM meta WHERE key = 'multi_user_enabled'").fetchone()
        return bool(row) and row[0] == "true"

    def set_multi_user(self, enabled: bool) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO meta (key, value) VALUES ('multi_user_enabled', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("true" if enabled else "false",),
            )

    # --- users ---

    @staticmethod
    def _user(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def _rows(self) -> sqlite3.Connection:
        db = self._connect()
        db.row_factory = sqlite3.Row
        return db

    def list_users(self) -> list[dict[str, Any]]:
        with closing(self._rows()) as db:
            rows = db.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        with closing(self._rows()) as db:
            return self._user(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    def user_by_name(self, username: str) -> dict[str, Any] | None:
        with closing(self._rows()) as db:
            row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return self._user(row)

    def owner(self) -> dict[str, Any] | None:
        with closing(self._rows()) as db:
            row = db.execute("SELECT * FROM users WHERE library = ?", (OWNER_LIBRARY,)).fetchone()
        return self._user(row)

    def count_admins(self) -> int:
        with closing(self._connect()) as db:
            return int(db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0])

    def create_owner(self, username: str) -> None:
        """The server owner's admin account, owning the root library. Kept when the
        mode is switched off; renamed when it exists already."""
        with closing(self._connect()) as db, db:
            updated = db.execute(
                "UPDATE users SET username = ? WHERE library = ?", (username, OWNER_LIBRARY)
            ).rowcount
            if not updated:
                db.execute(
                    "INSERT INTO users (username, password_hash, role, library, created_at) "
                    "VALUES (?, NULL, 'admin', ?, ?)",
                    (username, OWNER_LIBRARY, _now()),
                )

    def create_user(self, username: str, password_hash: str, role: str) -> int:
        """New account with its own library key `u<id>`. sqlite3.IntegrityError on a
        taken username."""
        with closing(self._connect()) as db, db:
            # Placeholder library keeps the UNIQUE column valid until the id is known.
            cur = db.execute(
                "INSERT INTO users (username, password_hash, role, library, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, password_hash, role, f"new-{secrets.token_hex(8)}", _now()),
            )
            user_id = int(cur.lastrowid or 0)
            db.execute("UPDATE users SET library = ? WHERE id = ?", (f"u{user_id}", user_id))
        return user_id

    def update_user(
        self,
        user_id: int,
        *,
        username: str | None = None,
        password_hash: str | None = None,
        role: str | None = None,
    ) -> None:
        """sqlite3.IntegrityError on a taken username."""
        sets: list[str] = []
        args: list[Any] = []
        for col, value in (
            ("username", username),
            ("password_hash", password_hash),
            ("role", role),
        ):
            if value is not None:
                sets.append(f"{col} = ?")
                args.append(value)
        if not sets:
            return
        with closing(self._connect()) as db, db:
            db.execute(
                f"UPDATE users SET {', '.join(sets)} WHERE id = ?",  # noqa: S608
                (*args, user_id),
            )

    def delete_user(self, user_id: int) -> None:
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
