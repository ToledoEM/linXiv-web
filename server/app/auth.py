"""Login: argon2 password check, signed session cookie, CSRF double-submit.

Sessions live in `<data dir>/linxiv-web-state.db` (app/state_db.py) with the
signing key, so a restart keeps everyone logged in and logout revokes the token.
LINXIV_WEB_SECRET_KEY, when set, replaces the stored key.

Password source, first match wins: LINXIV_WEB_PASSWORD_HASH, LINXIV_WEB_PASSWORD,
then the hash stored by first-run setup in `<data dir>/linxiv-web-auth.json`.
With none of them: auth is off on a loopback bind; on any other bind the server
starts in setup mode, where the first visitor creates the admin password.

Multi-user mode (off by default, switched in Settings → Server Admin) adds named
accounts from the state DB. The owner account keeps the server password above;
every session row names its account, and role and library are read from that
account on each request, so a demotion, deletion or reset applies at once.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .settings import Settings, is_loopback
from .state_db import OWNER_LIBRARY, USER_FIELDS, StateDB

SESSION_COOKIE = "lxw_session"
CSRF_COOKIE = "lxw_csrf"
CSRF_HEADER = "x-csrf-token"
SESSION_MAX_AGE = 60 * 60 * 24 * 14
LOGIN_WINDOW = 300
LOGIN_MAX_ATTEMPTS = 5
_UNSAFE = ("POST", "PUT", "PATCH", "DELETE")
AUTH_FILE = "linxiv-web-auth.json"
PASSWORD_MIN = 8
PASSWORD_MAX = 256
USERNAME_RE = r"^[a-z0-9_.-]{1,32}$"
ROLES = ("admin", "user")
# Multi-user mode: requests carrying this header with SHARED_LIBRARY work on the
# shared library (app/libraries.py), which only admins may change.
LIBRARY_HEADER = "x-linxiv-library"
SHARED_LIBRARY = "shared"
# POSTs that only read the shared library, open to every account.
SHARED_READ_POSTS = ("/api/shared/copy", "/api/export/bibtex")


def auth_file(data_dir: Path) -> Path:
    return data_dir / AUTH_FILE


def stored_hash(data_dir: Path) -> str | None:
    """Hash saved by first-run setup; None when setup has not run. Raises ValueError when
    the file exists but is unusable (fail closed rather than reopen setup)."""
    path = auth_file(data_dir)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("password_hash")
    except (OSError, ValueError, AttributeError) as exc:
        raise ValueError(f"{path} is unreadable: {exc}") from exc
    if not isinstance(value, str) or not value.startswith("$argon2"):
        raise ValueError(f"{path} holds no argon2 password_hash")
    return value


def write_stored_hash(data_dir: Path, password_hash: str) -> None:
    """Create the auth file (0600). FileExistsError if setup already ran."""
    path = auth_file(data_dir)
    body = json.dumps(
        {"password_hash": password_hash, "created": datetime.now(UTC).isoformat()}, indent=2
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, body.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def replace_stored_hash(data_dir: Path, password_hash: str) -> None:
    """Write the auth file (0600) atomically, replacing any previous password."""
    path = auth_file(data_dir)
    body = json.dumps(
        {"password_hash": password_hash, "created": datetime.now(UTC).isoformat()}, indent=2
    )
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, body.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


class Auth:
    def __init__(self, settings: Settings) -> None:
        self.cookie_secure = settings.cookie_secure
        self.remember_max_age = settings.remember_days * 60 * 60 * 24
        self._data_dir = settings.data_dir
        self._hasher = PasswordHasher()
        self._hash = settings.password_hash
        if not self._hash and settings.password:
            self._hash = self._hasher.hash(settings.password)
        # "env": set by environment, read-only here; "stored": changeable in Settings.
        self.login_from: str | None = "env" if self._hash else None
        if not self._hash:
            self._hash = stored_hash(settings.data_dir)
            self.login_from = "stored" if self._hash else None
        self.setup_required = not self._hash and not is_loopback(settings.host)
        self.enabled = bool(self._hash) or self.setup_required
        self._setup_lock = threading.Lock()
        self._state = StateDB(settings.data_dir)
        key = settings.secret_key or self._state.secret_key()
        self._serializer = URLSafeTimedSerializer(key, salt="linxiv-web-session")

    # --- first-run setup ---

    def complete_setup(self, password: str) -> bool:
        """Store the admin password. False when setup is closed (someone was first)."""
        with self._setup_lock:
            if not self.setup_required:
                return False
            password_hash = self._hasher.hash(password)
            try:
                write_stored_hash(self._data_dir, password_hash)
            except FileExistsError:
                return False
            self._hash = password_hash
            self.login_from = "stored"
            self.setup_required = False
            return True

    def change_password(self, new_password: str) -> None:
        """Replace the stored server password (caller checked the current one) and end
        the owner's sessions (every session in single-user mode); the caller starts a
        fresh one for the browser that asked."""
        password_hash = self._hasher.hash(new_password)
        replace_stored_hash(self._data_dir, password_hash)
        self._hash = password_hash
        owner = self._state.owner()
        if owner:
            self._state.drop_user_sessions(owner["id"])
        else:
            self._state.drop_all_sessions()

    def set_user_password(self, user_id: int, new_password: str) -> None:
        """New password for a named (non-owner) account; ends its sessions."""
        self._state.update_user(user_id, password_hash=self._hasher.hash(new_password))
        self._state.drop_user_sessions(user_id)

    def hash_password(self, password: str) -> str:
        return self._hasher.hash(password)

    def password_collides(self, password: str, exclude_id: int | None) -> bool:
        """True when `password` is another account's password (CatalogueCanvas rule:
        no two accounts share one). Compared by hash check, never in plain text."""
        for user in self._state.list_users():
            if user["id"] == exclude_id:
                continue
            if user["library"] == OWNER_LIBRARY:
                if self.verify_password(password):
                    return True
            elif self._check(user["password_hash"], password):
                return True
        return False

    # --- accounts ---

    @property
    def state(self) -> StateDB:
        return self._state

    def multi_user(self) -> bool:
        return self.enabled and self._state.multi_user_enabled()

    def _owner_identity(self) -> dict:
        owner = self._state.owner()
        if owner:
            return public_user(owner)
        return {"id": None, "username": None, "role": "admin", "library": OWNER_LIBRARY}

    def verify_login(self, username: str | None, password: str) -> dict | None:
        """The account these credentials open, None on failure. Single-user mode
        ignores the username (password-only login, as before)."""
        if not self.multi_user():
            return self._owner_identity() if self.verify_password(password) else None
        name = (username or "").strip().lower()
        user = self._state.user_by_name(name) if name else None
        if user is None:
            return None
        if user["library"] == OWNER_LIBRARY:
            ok = self.verify_password(password)
        else:
            ok = self._check(user["password_hash"], password)
        return public_user(user) if ok else None

    def _check(self, password_hash: str | None, password: str) -> bool:
        if not password_hash:
            return False
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def revoke_others(self, token: str | None) -> int:
        """End every session except the one holding `token`. Returns how many ended."""
        return self._state.drop_other_sessions(self._sid(token))

    # --- password + throttle ---

    def verify_password(self, password: str) -> bool:
        if self.login_from == "stored":
            # Re-read: `python -m app reset-password` may have replaced it.
            try:
                self._hash = stored_hash(self._data_dir) or self._hash
            except ValueError:
                return False
        return self._check(self._hash, password)

    # Failures persist in the state DB, so a restart doesn't reset the count.
    def throttled(self, client: str) -> bool:
        cutoff = time.time() - LOGIN_WINDOW
        return self._state.failures_since(client, cutoff) >= LOGIN_MAX_ATTEMPTS

    def record_failure(self, client: str) -> None:
        now = time.time()
        self._state.add_failure(client, now, prune_before=now - LOGIN_WINDOW)

    def clear_failures(self, client: str) -> None:
        self._state.clear_failures(client)

    # --- sessions ---

    def create_session(self, max_age: int = SESSION_MAX_AGE, user_id: int | None = None) -> str:
        sid = secrets.token_urlsafe(24)
        now = time.time()
        self._state.add_session(sid, now + max_age, now, user_id)
        return self._serializer.dumps({"sid": sid})

    def sid(self, token: str | None) -> str | None:
        return self._sid(token)

    def _sid(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            # Per-session expiry is enforced in is_valid; this bound only caps old tokens.
            data = self._serializer.loads(
                token, max_age=max(SESSION_MAX_AGE, self.remember_max_age)
            )
        except BadSignature:
            return None
        return data.get("sid") if isinstance(data, dict) else None

    def is_valid(self, token: str | None) -> bool:
        return self.identity(token) is not None

    def identity(self, token: str | None) -> dict | None:
        """The account behind a live session, None when the session is not valid.
        Read from the account row each time, never from the token."""
        sid = self._sid(token)
        if sid is None:
            return None
        row = self._state.session(sid)
        if row is None:
            return None
        expiry, user_id = row
        if expiry < time.time():
            self._state.drop_session(sid)
            return None
        if user_id is None:
            return self._owner_identity()
        user = self._state.get_user(user_id)
        if user is None:
            return None
        if user["library"] != OWNER_LIBRARY and not self.multi_user():
            # Named accounts only exist while multi-user mode is on.
            return None
        return public_user(user)

    def revoke(self, token: str | None) -> None:
        sid = self._sid(token)
        if sid:
            self._state.drop_session(sid)

    # --- request guard ---

    @staticmethod
    def check_origin(request: Request) -> None:
        if request.method in _UNSAFE:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.url.netloc:
                raise HTTPException(status_code=403, detail="cross-origin request rejected")

    def check(self, request: Request) -> None:
        # Always on, even without a password: stops a foreign page from driving
        # a loopback-only instance through the browser.
        self.check_origin(request)
        if self.setup_required:
            raise HTTPException(status_code=403, detail="first-run setup required")
        if not self.enabled:
            request.state.user = self._owner_identity()
            return
        user = self.identity(request.cookies.get(SESSION_COOKIE))
        if user is None:
            raise HTTPException(status_code=401, detail="not authenticated")
        if request.method in _UNSAFE:
            cookie = request.cookies.get(CSRF_COOKIE)
            header = request.headers.get(CSRF_HEADER)
            if not cookie or not header or not secrets.compare_digest(cookie, header):
                raise HTTPException(status_code=403, detail="invalid or missing CSRF token")
            if (
                user["role"] != "admin"
                and _wants_shared(request)
                and request.url.path not in SHARED_READ_POSTS
                and self.multi_user()
            ):
                raise HTTPException(status_code=403, detail="the shared library is read-only")
        request.state.user = user


def _wants_shared(request: Request) -> bool:
    return (request.headers.get(LIBRARY_HEADER) or "").strip().lower() == SHARED_LIBRARY


def public_user(user: dict) -> dict:
    """Account fields safe to hand out: never the password hash."""
    return {k: user[k] for k in USER_FIELDS if k in user and k != "created_at"}


def require_auth(request: Request) -> None:
    request.app.state.auth.check(request)


def require_admin(request: Request) -> dict:
    """Any admin account (every login is admin in single-user mode). Returns the user."""
    if getattr(request.state, "user", None) is None:
        require_auth(request)
    user = request.state.user
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="admin privileges required")
    return user


def current_user(request: Request) -> dict:
    """The caller's account; set by require_auth on every guarded route."""
    user = getattr(request.state, "user", None)
    if user is None:
        require_auth(request)
        user = request.state.user
    return user
