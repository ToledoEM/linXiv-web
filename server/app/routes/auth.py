from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..auth import (
    CSRF_COOKIE,
    PASSWORD_MAX,
    PASSWORD_MIN,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    current_user,
    require_auth,
)

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    password: str
    # Required in multi-user mode, ignored otherwise.
    username: str | None = Field(default=None, max_length=64)
    # Ticked: persistent cookies for remember_days. Unticked: browser-session cookies.
    remember: bool = False


def _scope(request: Request, username: str | None) -> str:
    # Real client address behind trusted proxies (app/netguard.py) + attempted
    # username: one noisy address can't lock others out, a guess at one account
    # stays bounded (CatalogueCanvas rule).
    client = getattr(request.state, "client_ip", None) or "unknown"
    return f"{client}|{(username or '').strip().lower()}"


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    auth = request.app.state.auth
    if not auth.enabled:
        return {"ok": True}
    multi = auth.multi_user()
    scope = _scope(request, body.username if multi else None)
    if auth.throttled(scope):
        raise HTTPException(status_code=429, detail="too many login attempts, try again later")
    user = auth.verify_login(body.username, body.password)
    if user is None:
        auth.record_failure(scope)
        detail = "invalid username or password" if multi else "invalid password"
        raise HTTPException(status_code=401, detail=detail)
    auth.clear_failures(scope)
    _start_session(auth, response, body.remember, user["id"])
    return {"ok": True, "username": user["username"], "role": user["role"]}


def _start_session(auth, response: Response, remember: bool, user_id: int | None = None) -> None:
    max_age = auth.remember_max_age if remember else SESSION_MAX_AGE
    cookie = {"samesite": "strict", "secure": auth.cookie_secure}
    if remember:
        cookie["max_age"] = max_age
    token = auth.create_session(max_age, user_id)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **cookie)
    # Readable by JS so the client can echo it in the X-CSRF-Token header.
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(24), httponly=False, **cookie)


class SetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


@router.post("/setup")
def setup(body: SetupRequest, request: Request, response: Response):
    """First-run setup: the first visitor sets the admin password and is logged in."""
    auth = request.app.state.auth
    auth.check_origin(request)
    if not auth.complete_setup(body.password):
        raise HTTPException(status_code=409, detail="setup is already complete")
    _start_session(auth, response, remember=False)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    request.app.state.auth.revoke(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    auth = request.app.state.auth
    user = auth.identity(request.cookies.get(SESSION_COOKIE)) if auth.enabled else None
    if not auth.enabled and not auth.setup_required:
        user = {"username": None, "role": "admin"}
    return {
        "auth_enabled": auth.enabled,
        "setup_required": auth.setup_required,
        "authenticated": user is not None,
        "password_source": auth.login_from,
        "multi_user": auth.multi_user(),
        "username": user["username"] if user else None,
        "role": user["role"] if user else None,
        # The owner logs in with the server password; others with their own.
        "owner": bool(user) and user.get("library", "root") == "root",
    }


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    current: str = Field(max_length=PASSWORD_MAX)
    new: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    remember: bool = False


@router.post("/password", dependencies=[Depends(require_auth)])
def change_password(body: PasswordChange, request: Request, response: Response):
    """Change the caller's own password; their other browsers are logged out."""
    auth = request.app.state.auth
    user = current_user(request)
    if user.get("library", "root") != "root":
        return _change_own(auth, user, body, request, response)
    if auth.login_from == "env":
        raise HTTPException(
            status_code=409,
            detail="the password comes from LINXIV_WEB_PASSWORD(_HASH); change it there",
        )
    if auth.login_from != "stored":
        raise HTTPException(status_code=409, detail="no password is set")
    scope = _scope(request, user["username"])
    if auth.throttled(scope):
        raise HTTPException(status_code=429, detail="too many attempts, try again later")
    if not auth.verify_password(body.current):
        auth.record_failure(scope)
        raise HTTPException(status_code=403, detail="current password is wrong")
    if auth.multi_user() and auth.password_collides(body.new, user["id"]):
        raise HTTPException(status_code=400, detail="password must differ from other users")
    auth.change_password(body.new)
    _start_session(auth, response, body.remember, user["id"])
    return {"ok": True}


def _change_own(auth, user: dict, body: PasswordChange, request: Request, response: Response):
    scope = _scope(request, user["username"])
    if auth.throttled(scope):
        raise HTTPException(status_code=429, detail="too many attempts, try again later")
    if auth.verify_login(user["username"], body.current) is None:
        auth.record_failure(scope)
        raise HTTPException(status_code=403, detail="current password is wrong")
    if auth.password_collides(body.new, user["id"]):
        raise HTTPException(status_code=400, detail="password must differ from other users")
    auth.set_user_password(user["id"], body.new)
    _start_session(auth, response, body.remember, user["id"])
    return {"ok": True}


@router.post("/sessions/revoke-others", dependencies=[Depends(require_auth)])
def revoke_others(request: Request):
    """Log out every other browser; this one stays logged in."""
    auth = request.app.state.auth
    return {"revoked": auth.revoke_others(request.cookies.get(SESSION_COOKIE))}
