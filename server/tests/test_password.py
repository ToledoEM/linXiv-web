from __future__ import annotations

from dataclasses import replace

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.__main__ import reset_password
from app.auth import CSRF_COOKIE, write_stored_hash
from app.main import create_app

OLD = "old-password-1"
NEW = "new-password-2"


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": c.cookies.get(CSRF_COOKIE)}


def _login(c: TestClient, password: str) -> int:
    return c.post("/api/login", json={"password": password}).status_code


@pytest.fixture
def stored(settings, fake):
    """App whose password was set by first-run setup (stored file)."""
    write_stored_hash(settings.data_dir, PasswordHasher().hash(OLD))
    fake.on("stats", result={})
    return lambda: TestClient(create_app(settings, fake))


def test_me_reports_password_source(stored, settings, fake):
    assert stored().get("/api/me").json()["password_source"] == "stored"
    env = TestClient(create_app(replace(settings, password="x" * 8), fake))
    assert env.get("/api/me").json()["password_source"] == "env"


def test_change_password_logs_out_other_browsers(stored):
    me, other = stored(), stored()
    assert _login(me, OLD) == 200 and _login(other, OLD) == 200
    r = me.post("/api/password", json={"current": OLD, "new": NEW}, headers=_csrf(me))
    assert r.status_code == 200
    assert me.get("/api/stats").status_code == 200  # fresh session for this browser
    assert other.get("/api/stats").status_code == 401
    fresh = stored()
    assert _login(fresh, OLD) == 401
    assert _login(fresh, NEW) == 200


def test_change_password_checks_current_and_length(stored):
    me = stored()
    _login(me, OLD)
    bad = me.post("/api/password", json={"current": "nope", "new": NEW}, headers=_csrf(me))
    assert bad.status_code == 403
    short = me.post("/api/password", json={"current": OLD, "new": "short"}, headers=_csrf(me))
    assert short.status_code == 422
    # No CSRF header: refused before anything changes.
    assert me.post("/api/password", json={"current": OLD, "new": NEW}).status_code == 403


def test_change_password_refused_for_env_password(settings, fake):
    c = TestClient(create_app(replace(settings, password=OLD), fake))
    _login(c, OLD)
    r = c.post("/api/password", json={"current": OLD, "new": NEW}, headers=_csrf(c))
    assert r.status_code == 409
    assert "LINXIV_WEB_PASSWORD" in r.json()["detail"]


def test_change_password_refused_without_password(client):
    r = client.post("/api/password", json={"current": "", "new": NEW})
    assert r.status_code == 409


def test_revoke_others_keeps_this_browser(stored):
    me, other = stored(), stored()
    _login(me, OLD)
    _login(other, OLD)
    r = me.post("/api/sessions/revoke-others", headers=_csrf(me))
    assert r.json() == {"revoked": 1}
    assert me.get("/api/stats").status_code == 200
    assert other.get("/api/stats").status_code == 401


def test_reset_password_cli(stored, settings, monkeypatch, capsys):
    running = stored()
    _login(running, OLD)
    monkeypatch.setenv("PASSWORD", NEW)
    reset_password(settings)
    assert "1 session(s) logged out" in capsys.readouterr().out
    # Same running server: old session gone, new password works at once.
    assert running.get("/api/stats").status_code == 401
    assert _login(running, OLD) == 401
    assert _login(running, NEW) == 200


def test_reset_password_cli_rejects_short(settings, monkeypatch):
    monkeypatch.setenv("PASSWORD", "short")
    with pytest.raises(SystemExit):
        reset_password(settings)
