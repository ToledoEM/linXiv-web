"""Single-admin login: argon2 password check, signed session cookie, CSRF double-submit.

Sessions live in `<data dir>/linxiv-web-state.db` (app/state_db.py) with the
signing key, so a restart keeps everyone logged in and logout revokes the token.
LINXIV_WEB_SECRET_KEY, when set, replaces the stored key.

Password source, first match wins: LINXIV_WEB_PASSWORD_HASH, LINXIV_WEB_PASSWORD,
then the hash stored by first-run setup in `<data dir>/linxiv-web-auth.json`.
With none of them: auth is off on a loopback bind; on any other bind the server
starts in setup mode, where the first visitor creates the admin password.
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
from .state_db import StateDB

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
        """Replace the stored password (caller checked the current one) and end every
        session; the caller starts a fresh one for the browser that asked."""
        password_hash = self._hasher.hash(new_password)
        replace_stored_hash(self._data_dir, password_hash)
        self._hash = password_hash
        self._state.drop_all_sessions()

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
        if not self._hash:
            return False
        try:
            return self._hasher.verify(self._hash, password)
        except (VerificationError, InvalidHashError):
            return False

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

    def create_session(self, max_age: int = SESSION_MAX_AGE) -> str:
        sid = secrets.token_urlsafe(24)
        now = time.time()
        self._state.add_session(sid, now + max_age, now)
        return self._serializer.dumps({"sid": sid})

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
        sid = self._sid(token)
        if sid is None:
            return False
        expiry = self._state.session_expiry(sid)
        if expiry is None:
            return False
        if expiry < time.time():
            self._state.drop_session(sid)
            return False
        return True

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
            return
        if not self.is_valid(request.cookies.get(SESSION_COOKIE)):
            raise HTTPException(status_code=401, detail="not authenticated")
        if request.method in _UNSAFE:
            cookie = request.cookies.get(CSRF_COOKIE)
            header = request.headers.get(CSRF_HEADER)
            if not cookie or not header or not secrets.compare_digest(cookie, header):
                raise HTTPException(status_code=403, detail="invalid or missing CSRF token")


def require_auth(request: Request) -> None:
    request.app.state.auth.check(request)
