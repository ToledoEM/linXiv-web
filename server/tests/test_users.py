from __future__ import annotations

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app import activity
from app.__main__ import reset_password
from app.auth import CSRF_COOKIE, LOGIN_MAX_ATTEMPTS
from app.main import create_app

OWNER_PW = "owner-password"
ALICE_PW = "alice-password"


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": c.cookies.get(CSRF_COOKIE)}


def _login(c: TestClient, password: str, username: str | None = None) -> int:
    body = {"password": password}
    if username is not None:
        body["username"] = username
    return c.post("/api/login", json=body).status_code


@pytest.fixture
def make(settings, fake):
    fake.on("stats", result={})
    s = replace(settings, password=OWNER_PW)
    return lambda: TestClient(create_app(s, fake))


@pytest.fixture
def admin(make):
    """Owner logged in, multi-user mode on with owner `boss`."""
    c = make()
    assert _login(c, OWNER_PW) == 200
    r = c.post(
        "/api/admin/multi-user", json={"enabled": True, "username": "Boss"}, headers=_csrf(c)
    )
    assert r.status_code == 200
    assert r.json() == {"enabled": True, "owner_username": "boss"}
    return c


def _add(admin: TestClient, username="alice", password=ALICE_PW, role="user"):
    return admin.post(
        "/api/users",
        json={"username": username, "password": password, "role": role},
        headers=_csrf(admin),
    )


def test_single_user_mode_unchanged(make):
    c = make()
    assert _login(c, OWNER_PW, username="ignored") == 200
    me = c.get("/api/me").json()
    assert me["multi_user"] is False and me["role"] == "admin" and me["owner"] is True
    assert c.get("/api/users").json() == []
    # Accounts can't be made while the mode is off.
    assert _add(c).status_code == 409


def test_enable_needs_username_and_password(make, client):
    c = make()
    _login(c, OWNER_PW)
    r = c.post("/api/admin/multi-user", json={"enabled": True}, headers=_csrf(c))
    assert r.status_code == 400
    bad = c.post(
        "/api/admin/multi-user", json={"enabled": True, "username": "no spaces"}, headers=_csrf(c)
    )
    assert bad.status_code == 400
    # Loopback without any password: no accounts to speak of.
    off = client.post("/api/admin/multi-user", json={"enabled": True, "username": "x"})
    assert off.status_code == 409


def test_owner_logs_in_with_username_after_enable(admin, make):
    # The browser that switched the mode keeps its session.
    assert admin.get("/api/me").json()["username"] == "boss"
    c = make()
    assert _login(c, OWNER_PW) == 401  # username now required
    assert _login(c, OWNER_PW, "boss") == 200
    me = c.get("/api/me").json()
    assert me == {**me, "multi_user": True, "username": "boss", "role": "admin", "owner": True}


def test_create_user_and_login(admin, make):
    r = _add(admin, username="Alice")
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "alice" and body["role"] == "user"
    assert body["library"] == f"u{body['id']}" and body["owner"] is False
    assert "password_hash" not in body
    assert all("password_hash" not in u for u in admin.get("/api/users").json())
    c = make()
    assert _login(c, "wrong-password", "alice") == 401
    assert _login(c, ALICE_PW, "ALICE") == 200
    me = c.get("/api/me").json()
    assert me["username"] == "alice" and me["role"] == "user" and me["owner"] is False
    assert c.get("/api/stats").status_code == 200


def test_user_is_not_admin(admin, make):
    _add(admin)
    c = make()
    _login(c, ALICE_PW, "alice")
    assert c.get("/api/users").status_code == 403
    assert _add(c, username="eve", password="eve-password").status_code == 403
    r = c.post("/api/admin/multi-user", json={"enabled": False}, headers=_csrf(c))
    assert r.status_code == 403
    assert make().get("/api/users").status_code == 401


def test_duplicate_username_and_password_collision(admin):
    assert _add(admin).status_code == 201
    assert _add(admin, password="other-password").status_code == 409
    assert _add(admin, username="bob", password=ALICE_PW).status_code == 400
    # Same as the owner's server password.
    assert _add(admin, username="bob", password=OWNER_PW).status_code == 400
    assert _add(admin, username="bob", password="short").status_code == 422
    assert _add(admin, username="bob", password="bob-password", role="root").status_code == 400


def test_last_admin_and_owner_guards(admin):
    users = admin.get("/api/users").json()
    owner_id = users[0]["id"]
    r = admin.put(f"/api/users/{owner_id}", json={"role": "user"}, headers=_csrf(admin))
    assert r.status_code == 400
    assert admin.delete(f"/api/users/{owner_id}", headers=_csrf(admin)).status_code == 400
    assert admin.delete("/api/users/999", headers=_csrf(admin)).status_code == 404


def test_admin_cannot_delete_self(admin, make):
    second = _add(admin, username="ann", password="ann-password", role="admin").json()
    c = make()
    assert _login(c, "ann-password", "ann") == 200
    r = c.delete(f"/api/users/{second['id']}", headers=_csrf(c))
    assert r.status_code == 400
    # Another admin may.
    r = admin.delete(f"/api/users/{second['id']}", headers=_csrf(admin))
    assert r.status_code == 200
    assert r.json()["library_dir"].endswith(f"libraries/{second['library']}")
    assert c.get("/api/stats").status_code == 401


def test_password_reset_and_demote_end_sessions(admin, make):
    alice = _add(admin).json()
    c = make()
    _login(c, ALICE_PW, "alice")
    r = admin.put(
        f"/api/users/{alice['id']}", json={"password": "fresh-password"}, headers=_csrf(admin)
    )
    assert r.status_code == 200
    assert c.get("/api/stats").status_code == 401
    assert _login(c, ALICE_PW, "alice") == 401
    assert _login(c, "fresh-password", "alice") == 200
    # Promote then demote: role changes end sessions too, and apply at once.
    admin.put(f"/api/users/{alice['id']}", json={"role": "admin"}, headers=_csrf(admin))
    assert c.get("/api/users").status_code == 401
    _login(c, "fresh-password", "alice")
    assert c.get("/api/users").status_code == 200


def test_rename_conflict(admin):
    alice = _add(admin).json()
    _add(admin, username="bob", password="bob-password")
    r = admin.put(f"/api/users/{alice['id']}", json={"username": "bob"}, headers=_csrf(admin))
    assert r.status_code == 409
    r = admin.put(f"/api/users/{alice['id']}", json={"username": "carol"}, headers=_csrf(admin))
    assert r.json()["username"] == "carol"


def test_user_changes_own_password(admin, make):
    _add(admin)
    c, other = make(), make()
    _login(c, ALICE_PW, "alice")
    _login(other, ALICE_PW, "alice")
    bad = c.post(
        "/api/password", json={"current": "nope-nope", "new": "new-alice-pw"}, headers=_csrf(c)
    )
    assert bad.status_code == 403
    clash = c.post("/api/password", json={"current": ALICE_PW, "new": OWNER_PW}, headers=_csrf(c))
    assert clash.status_code == 400
    ok = c.post(
        "/api/password", json={"current": ALICE_PW, "new": "new-alice-pw"}, headers=_csrf(c)
    )
    assert ok.status_code == 200
    assert c.get("/api/stats").status_code == 200
    assert other.get("/api/stats").status_code == 401
    # The owner stays logged in.
    assert admin.get("/api/stats").status_code == 200


def test_throttle_scoped_by_username(admin, make):
    _add(admin)
    c = make()
    for _ in range(LOGIN_MAX_ATTEMPTS):
        _login(c, "wrong-password", "alice")
    assert _login(c, ALICE_PW, "alice") == 429
    # Same address, other account: not locked out.
    assert _login(c, OWNER_PW, "boss") == 200


def test_disable_drops_named_sessions(admin, make):
    _add(admin)
    c = make()
    _login(c, ALICE_PW, "alice")
    r = admin.post("/api/admin/multi-user", json={"enabled": False}, headers=_csrf(admin))
    assert r.json()["enabled"] is False
    assert c.get("/api/stats").status_code == 401
    assert _login(c, ALICE_PW, "alice") == 401
    assert admin.get("/api/stats").status_code == 200
    assert _login(make(), OWNER_PW) == 200
    # Back on: accounts are still there.
    r = admin.post("/api/admin/multi-user", json={"enabled": True}, headers=_csrf(admin))
    assert r.json() == {"enabled": True, "owner_username": "boss"}
    assert _login(c, ALICE_PW, "alice") == 200


def test_activity_records_actor_not_password(admin, settings):
    _add(admin)
    alice = admin.get("/api/users").json()[1]
    admin.put(
        f"/api/users/{alice['id']}", json={"password": "fresh-password"}, headers=_csrf(admin)
    )
    events = activity.read(settings.data_dir, 10)
    put = next(e for e in events if e["method"] == "PUT")
    assert put["actor"] == "boss" and put["fields"] == ["password"]
    raw = activity.path(settings.data_dir).read_text()
    assert "fresh-password" not in raw and ALICE_PW not in raw
    assert all(json.loads(line) for line in raw.splitlines())


def test_reset_password_cli_for_user(admin, make, settings, monkeypatch, capsys):
    _add(admin)
    c = make()
    _login(c, ALICE_PW, "alice")
    monkeypatch.setenv("PASSWORD", "cli-password")
    reset_password(settings, "alice")
    assert "for alice; 1 session(s)" in capsys.readouterr().out
    assert c.get("/api/stats").status_code == 401
    assert admin.get("/api/stats").status_code == 200
    assert _login(c, "cli-password", "alice") == 200
    with pytest.raises(SystemExit):
        reset_password(settings, "nobody")
