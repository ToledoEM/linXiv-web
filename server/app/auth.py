"""Single-admin login: argon2 password check, signed session cookie, CSRF double-submit.

Sessions live in process memory (one uvicorn worker), so logout revokes the
token and a restart logs everyone out. When no password is configured, auth is
off; `__main__` refuses to bind off loopback in that case.
"""

from __future__ import annotations

import secrets
import time
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .settings import Settings

SESSION_COOKIE = "lxw_session"
CSRF_COOKIE = "lxw_csrf"
CSRF_HEADER = "x-csrf-token"
SESSION_MAX_AGE = 60 * 60 * 24 * 14
LOGIN_WINDOW = 300
LOGIN_MAX_ATTEMPTS = 5
_UNSAFE = ("POST", "PUT", "PATCH", "DELETE")


class Auth:
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.auth_enabled
        self.cookie_secure = settings.cookie_secure
        self._hasher = PasswordHasher()
        self._hash = settings.password_hash
        if not self._hash and settings.password:
            self._hash = self._hasher.hash(settings.password)
        key = settings.secret_key or secrets.token_hex(32)
        self._serializer = URLSafeTimedSerializer(key, salt="linxiv-web-session")
        self._sessions: dict[str, float] = {}
        self._failures: dict[str, list[float]] = {}

    # --- password + throttle ---

    def verify_password(self, password: str) -> bool:
        if not self._hash:
            return False
        try:
            return self._hasher.verify(self._hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def throttled(self, client: str) -> bool:
        cutoff = time.time() - LOGIN_WINDOW
        recent = [t for t in self._failures.get(client, []) if t >= cutoff]
        self._failures[client] = recent
        return len(recent) >= LOGIN_MAX_ATTEMPTS

    def record_failure(self, client: str) -> None:
        self._failures.setdefault(client, []).append(time.time())

    def clear_failures(self, client: str) -> None:
        self._failures.pop(client, None)

    # --- sessions ---

    def create_session(self) -> str:
        sid = secrets.token_urlsafe(24)
        self._sessions[sid] = time.time() + SESSION_MAX_AGE
        return self._serializer.dumps({"sid": sid})

    def _sid(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            data = self._serializer.loads(token, max_age=SESSION_MAX_AGE)
        except BadSignature:
            return None
        return data.get("sid") if isinstance(data, dict) else None

    def is_valid(self, token: str | None) -> bool:
        sid = self._sid(token)
        if sid is None:
            return False
        expiry = self._sessions.get(sid)
        if expiry is None or expiry < time.time():
            self._sessions.pop(sid, None)
            return False
        return True

    def revoke(self, token: str | None) -> None:
        sid = self._sid(token)
        if sid:
            self._sessions.pop(sid, None)

    # --- request guard ---

    def check(self, request: Request) -> None:
        # Always on, even without a password: stops a foreign page from driving
        # a loopback-only instance through the browser.
        if request.method in _UNSAFE:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.url.netloc:
                raise HTTPException(status_code=403, detail="cross-origin request rejected")
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
