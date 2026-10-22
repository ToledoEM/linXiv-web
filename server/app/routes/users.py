"""Server Admin: multi-user switch and account management (admin only).

Follows CatalogueCanvas `routers/users.py`: unique lowercase usernames, no two
accounts share a password, the last admin can't be demoted or deleted. Each new
account gets its own library key `u<id>`; deleting an account keeps that library
on disk. A password, role or account change ends the account's sessions at once.
"""

from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..activity import note_fields
from ..auth import PASSWORD_MAX, PASSWORD_MIN, ROLES, USERNAME_RE, public_user, require_admin
from ..state_db import OWNER_LIBRARY

router = APIRouter(prefix="/api", tags=["users"], dependencies=[Depends(require_admin)])

_USERNAME = re.compile(USERNAME_RE)


def _out(user: dict) -> dict:
    return {**public_user(user), "created_at": user["created_at"], "owner": _is_owner(user)}


def _is_owner(user: dict) -> bool:
    return user["library"] == OWNER_LIBRARY


def _username(value: str) -> str:
    name = value.strip().lower()
    if not _USERNAME.fullmatch(name):
        raise HTTPException(
            status_code=400, detail="username: 1 to 32 of a-z, 0-9, dot, dash, underscore"
        )
    return name


def _role(value: str) -> str:
    if value not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {', '.join(ROLES)}")
    return value


def _library_dir(request: Request, key: str) -> str:
    return str(request.app.state.libraries.dir_for(key))


# --- multi-user switch ---


class MultiUser(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool
    # The owner's username; needed the first time the mode is switched on.
    username: str | None = Field(default=None, max_length=64)


@router.get("/admin/multi-user")
def get_multi_user(request: Request):
    auth = request.app.state.auth
    owner = auth.state.owner()
    return {"enabled": auth.multi_user(), "owner_username": owner["username"] if owner else None}


@router.post("/admin/multi-user")
def set_multi_user(body: MultiUser, request: Request):
    auth = request.app.state.auth
    if not auth.enabled:
        raise HTTPException(status_code=409, detail="set a server password first")
    state = auth.state
    if body.enabled:
        owner = state.owner()
        if body.username is not None or owner is None:
            if body.username is None:
                raise HTTPException(status_code=400, detail="admin username required")
            try:
                state.create_owner(_username(body.username))
            except sqlite3.IntegrityError:
                raise HTTPException(status_code=409, detail="username already exists") from None
        state.set_multi_user(True)
    else:
        user = request.state.user
        if user.get("library") != OWNER_LIBRARY:
            raise HTTPException(
                status_code=403, detail="only the server owner can turn multi-user mode off"
            )
        state.set_multi_user(False)
        # Only the owner can log in in single-user mode.
        state.drop_sessions_except_owner()
    return get_multi_user(request)


# --- accounts ---


def _require_on(request: Request) -> None:
    if not request.app.state.auth.multi_user():
        raise HTTPException(status_code=409, detail="multi-user mode is off")


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str = Field(max_length=64)
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    role: str = "user"


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    role: str | None = None


@router.get("/users")
def list_users(request: Request):
    return [_out(u) for u in request.app.state.auth.state.list_users()]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, request: Request):
    _require_on(request)
    auth = request.app.state.auth
    name = _username(body.username)
    role = _role(body.role)
    if auth.state.user_by_name(name):
        raise HTTPException(status_code=409, detail="username already exists")
    if auth.password_collides(body.password, exclude_id=None):
        raise HTTPException(status_code=400, detail="password must differ from other users")
    try:
        user_id = auth.state.create_user(name, auth.hash_password(body.password), role)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="username already exists") from None
    note_fields(request, ["username", "role"])
    return _out(_get(request, user_id))


def _get(request: Request, user_id: int) -> dict:
    user = request.app.state.auth.state.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request):
    _require_on(request)
    auth = request.app.state.auth
    state = auth.state
    user = _get(request, user_id)
    name = _username(body.username) if body.username is not None else None
    role = _role(body.role) if body.role is not None else None
    if role is not None and role != user["role"]:
        if _is_owner(user):
            raise HTTPException(status_code=400, detail="the server owner stays admin")
        if user["role"] == "admin" and state.count_admins() <= 1:
            raise HTTPException(status_code=400, detail="cannot demote the last admin")
    if name is not None and name != user["username"]:
        other = state.user_by_name(name)
        if other and other["id"] != user_id:
            raise HTTPException(status_code=409, detail="username already exists")
    if body.password is not None and auth.password_collides(body.password, exclude_id=user_id):
        raise HTTPException(status_code=400, detail="password must differ from other users")
    if body.password is not None and _is_owner(user) and auth.login_from != "stored":
        raise HTTPException(
            status_code=409,
            detail="the owner password comes from LINXIV_WEB_PASSWORD(_HASH); change it there",
        )
    try:
        state.update_user(user_id, username=name, role=role)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="username already exists") from None
    if body.password is not None:
        if _is_owner(user):
            auth.change_password(body.password)
        else:
            auth.set_user_password(user_id, body.password)
    elif role is not None and role != user["role"]:
        state.drop_user_sessions(user_id)
    # Field names only: the activity log records *that* the password changed.
    note_fields(request, [k for k, v in body.model_dump().items() if v is not None])
    return _out(_get(request, user_id))


@router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request):
    _require_on(request)
    state = request.app.state.auth.state
    user = _get(request, user_id)
    if _is_owner(user):
        raise HTTPException(status_code=400, detail="the server owner can't be deleted")
    if user_id == request.state.user.get("id"):
        raise HTTPException(status_code=400, detail="you can't delete your own account")
    if user["role"] == "admin" and state.count_admins() <= 1:
        raise HTTPException(status_code=400, detail="cannot delete the last admin")
    state.delete_user(user_id)
    # The account goes; its library stays on disk for the admin to keep or remove.
    return {"ok": True, "library_dir": _library_dir(request, user["library"])}
