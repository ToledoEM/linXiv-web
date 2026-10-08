from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..auth import (
    CSRF_COOKIE,
    PASSWORD_MAX,
    PASSWORD_MIN,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
)

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    password: str
    # Ticked: persistent cookies for remember_days. Unticked: browser-session cookies.
    remember: bool = False


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    auth = request.app.state.auth
    if not auth.enabled:
        return {"ok": True}
    client = request.client.host if request.client else "unknown"
    if auth.throttled(client):
        raise HTTPException(status_code=429, detail="too many login attempts, try again later")
    if not auth.verify_password(body.password):
        auth.record_failure(client)
        raise HTTPException(status_code=401, detail="invalid password")
    auth.clear_failures(client)
    _start_session(auth, response, body.remember)
    return {"ok": True}


def _start_session(auth, response: Response, remember: bool) -> None:
    max_age = auth.remember_max_age if remember else SESSION_MAX_AGE
    cookie = {"samesite": "strict", "secure": auth.cookie_secure}
    if remember:
        cookie["max_age"] = max_age
    response.set_cookie(SESSION_COOKIE, auth.create_session(max_age), httponly=True, **cookie)
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
    return {
        "auth_enabled": auth.enabled,
        "setup_required": auth.setup_required,
        "authenticated": (not auth.enabled) or auth.is_valid(request.cookies.get(SESSION_COOKIE)),
    }
