from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.auth import CSRF_COOKIE, LOGIN_MAX_ATTEMPTS, SESSION_COOKIE
from app.main import create_app


def login(c, password="hunter2"):
    return c.post("/api/login", json={"password": password})


def test_open_when_no_password(client, fake):
    fake.on("stats", result={})
    assert client.get("/api/me").json() == {
        "auth_enabled": False,
        "setup_required": False,
        "authenticated": True,
        "password_source": None,
        "multi_user": False,
        "username": None,
        "role": "admin",
        "owner": True,
    }
    assert client.get("/api/stats").status_code == 200


def test_requires_login(auth_client, fake):
    fake.on("stats", result={})
    assert auth_client.get("/api/stats").status_code == 401
    assert auth_client.get("/api/health").status_code == 200
    assert auth_client.get("/api/me").json()["authenticated"] is False
    assert fake.calls == []


def test_wrong_password(auth_client):
    assert login(auth_client, "nope").status_code == 401


def test_login_then_csrf_on_writes(auth_client, fake):
    fake.on("stats", result={})
    fake.on("paper", "delete", result={})
    assert login(auth_client).status_code == 200
    assert auth_client.get("/api/stats").status_code == 200
    assert auth_client.delete("/api/papers/x").status_code == 403
    token = auth_client.cookies.get(CSRF_COOKIE)
    r = auth_client.delete("/api/papers/x", headers={"X-CSRF-Token": token})
    assert r.status_code == 200


def test_logout_revokes(auth_client, fake):
    fake.on("stats", result={})
    login(auth_client)
    from app.auth import SESSION_COOKIE

    session = auth_client.cookies.get(SESSION_COOKIE)
    auth_client.post("/api/logout", headers={"X-CSRF-Token": auth_client.cookies.get(CSRF_COOKIE)})
    auth_client.cookies.set(SESSION_COOKIE, session)
    assert auth_client.get("/api/stats").status_code == 401


def test_forged_cookie_rejected(auth_client):
    auth_client.cookies.set("lxw_session", "forged")
    assert auth_client.get("/api/stats").status_code == 401


def test_throttle(auth_client):
    for _ in range(LOGIN_MAX_ATTEMPTS):
        login(auth_client, "nope")
    assert login(auth_client).status_code == 429


def test_throttle_survives_restart(settings, fake):
    s = replace(settings, password="hunter2")
    first = TestClient(create_app(s, fake))
    for _ in range(LOGIN_MAX_ATTEMPTS):
        login(first, "nope")
    assert login(TestClient(create_app(s, fake))).status_code == 429
    assert (s.data_dir / "linxiv-web-state.db").stat().st_mode & 0o777 == 0o600


def test_throttle_keys_on_real_client_behind_proxy(settings, fake):
    s = replace(settings, password="hunter2", trusted_proxies=("10.0.0.2",))
    c = TestClient(create_app(s, fake), client=("10.0.0.2", 40000))
    bad = {"X-Forwarded-For": "192.168.1.50"}
    for _ in range(LOGIN_MAX_ATTEMPTS):
        c.post("/api/login", json={"password": "nope"}, headers=bad)
    assert c.post("/api/login", json={"password": "hunter2"}, headers=bad).status_code == 429
    good = {"X-Forwarded-For": "192.168.1.51"}
    assert c.post("/api/login", json={"password": "hunter2"}, headers=good).status_code == 200


def _restart(s, fake, old: TestClient) -> TestClient:
    """A new app on the same data dir, keeping the browser's cookies."""
    new = TestClient(create_app(s, fake))
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        new.cookies.set(name, old.cookies.get(name))
    return new


def test_session_survives_restart_with_stored_key(settings, fake):
    fake.on("stats", result={})
    s = replace(settings, password="hunter2", secret_key=None)
    first = TestClient(create_app(s, fake))
    assert login(first).status_code == 200
    assert _restart(s, fake, first).get("/api/stats").status_code == 200


def test_env_secret_key_replaces_stored_one(settings, fake):
    fake.on("stats", result={})
    s = replace(settings, password="hunter2", secret_key=None)
    first = TestClient(create_app(s, fake))
    login(first)
    other_key = replace(s, secret_key="another-key")
    assert _restart(other_key, fake, first).get("/api/stats").status_code == 401


def test_logout_revokes_across_restart(settings, fake):
    fake.on("stats", result={})
    s = replace(settings, password="hunter2")
    first = TestClient(create_app(s, fake))
    login(first)
    session = first.cookies.get(SESSION_COOKIE)
    first.post("/api/logout", headers={"X-CSRF-Token": first.cookies.get(CSRF_COOKIE)})
    again = _restart(s, fake, first)
    again.cookies.set(SESSION_COOKIE, session)
    assert again.get("/api/stats").status_code == 401


def test_sessions_stored_hashed_and_expire(settings):
    import sqlite3

    from app.state_db import StateDB

    db = StateDB(settings.data_dir)
    db.add_session("sid-1", expires=50.0, now=0.0)
    db.add_session("sid-2", expires=500.0, now=100.0)  # prunes sid-1
    assert db.session_expiry("sid-1") is None
    assert db.session_expiry("sid-2") == 500.0
    raw = sqlite3.connect(db.path).execute("SELECT sid_hash FROM sessions").fetchall()
    assert raw and all("sid-2" not in r[0] for r in raw)
    assert db.secret_key() == db.secret_key()


def test_throttle_prunes_old_failures(settings):
    from app.state_db import StateDB

    db = StateDB(settings.data_dir)
    db.add_failure("a", at=100.0, prune_before=0.0)
    db.add_failure("b", at=500.0, prune_before=400.0)
    assert db.failures_since("a", 0.0) == 0
    assert db.failures_since("b", 0.0) == 1
    db.clear_failures("b")
    assert db.failures_since("b", 0.0) == 0


def test_cross_origin_write_rejected_even_without_password(client, fake):
    fake.on("paper", "delete", result={})
    r = client.delete("/api/papers/x", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert (
        client.delete("/api/papers/x", headers={"Origin": "http://testserver"}).status_code == 200
    )


def _set_cookie(r, name):
    return next(h for h in r.headers.get_list("set-cookie") if h.startswith(f"{name}="))


def test_login_without_remember_sets_session_cookies(auth_client):
    from app.auth import SESSION_COOKIE

    r = login(auth_client)
    assert "max-age" not in _set_cookie(r, SESSION_COOKIE).lower()
    assert "max-age" not in _set_cookie(r, CSRF_COOKIE).lower()


def test_login_with_remember_sets_long_cookies(auth_client):
    from app.auth import SESSION_COOKIE

    r = auth_client.post("/api/login", json={"password": "hunter2", "remember": True})
    assert r.status_code == 200
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        assert f"max-age={90 * 86400}" in _set_cookie(r, name).lower()


def test_session_expiry_follows_remember(auth_client, fake, monkeypatch):
    import time

    from app.auth import SESSION_MAX_AGE

    fake.on("stats", result={})
    now = time.time()
    auth_client.post("/api/login", json={"password": "hunter2", "remember": True})
    # Past the plain 14-day lifetime, inside the 90-day remember window.
    monkeypatch.setattr(time, "time", lambda: now + SESSION_MAX_AGE + 3600)
    assert auth_client.get("/api/stats").status_code == 200
    monkeypatch.setattr(time, "time", lambda: now + 91 * 86400)
    assert auth_client.get("/api/stats").status_code == 401


def test_plain_session_expires_after_default_lifetime(auth_client, fake, monkeypatch):
    import time

    from app.auth import SESSION_MAX_AGE

    fake.on("stats", result={})
    now = time.time()
    login(auth_client)
    monkeypatch.setattr(time, "time", lambda: now + SESSION_MAX_AGE + 3600)
    assert auth_client.get("/api/stats").status_code == 401


def test_remember_days_env(monkeypatch):
    from app import settings as settings_mod

    monkeypatch.setenv("LINXIV_WEB_REMEMBER_DAYS", "30")
    assert settings_mod.load().remember_days == 30
    monkeypatch.setenv("LINXIV_WEB_REMEMBER_DAYS", "0")
    assert settings_mod.load().remember_days == 1


@pytest.fixture
def setup_client(settings, fake):
    return TestClient(create_app(replace(settings, host="0.0.0.0"), fake))


def test_setup_mode_blocks_api_until_password_set(setup_client, fake, settings):
    import os
    import stat

    from app.auth import auth_file

    fake.on("stats", result={})
    me = setup_client.get("/api/me").json()
    assert me == {
        "auth_enabled": True,
        "setup_required": True,
        "authenticated": False,
        "password_source": None,
        "multi_user": False,
        "username": None,
        "role": None,
        "owner": False,
    }
    r = setup_client.get("/api/stats")
    assert r.status_code == 403
    assert r.json()["detail"] == "first-run setup required"
    assert login(setup_client, "anything").status_code == 401

    assert setup_client.post("/api/setup", json={"password": "short"}).status_code == 422
    assert setup_client.post("/api/setup", json={"password": "correct horse"}).status_code == 200
    # Logged in straight away, with the usual CSRF cookie.
    assert setup_client.get("/api/stats").status_code == 200
    assert setup_client.get("/api/me").json()["setup_required"] is False
    path = auth_file(settings.data_dir)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert "correct horse" not in path.read_text()

    # First come, first served: the second attempt is refused.
    r = setup_client.post("/api/setup", json={"password": "another password"})
    assert r.status_code == 409


def test_stored_password_survives_restart(setup_client, fake, settings):
    fake.on("stats", result={})
    setup_client.post("/api/setup", json={"password": "correct horse"})
    again = TestClient(create_app(replace(settings, host="0.0.0.0"), fake))
    assert again.get("/api/me").json()["setup_required"] is False
    assert again.get("/api/stats").status_code == 401
    assert login(again, "wrong password").status_code == 401
    assert login(again, "correct horse").status_code == 200
    assert again.get("/api/stats").status_code == 200


def test_env_password_skips_setup(settings, fake):
    c = TestClient(create_app(replace(settings, host="0.0.0.0", password="hunter2"), fake))
    assert c.get("/api/me").json()["setup_required"] is False
    assert c.post("/api/setup", json={"password": "correct horse"}).status_code == 409


def test_loopback_without_password_has_no_setup(client):
    assert client.post("/api/setup", json={"password": "correct horse"}).status_code == 409


def test_setup_rejects_cross_origin(setup_client):
    r = setup_client.post(
        "/api/setup", json={"password": "correct horse"}, headers={"Origin": "http://evil.example"}
    )
    assert r.status_code == 403
    assert setup_client.get("/api/me").json()["setup_required"] is True
