from __future__ import annotations

from app.auth import CSRF_COOKIE, LOGIN_MAX_ATTEMPTS


def login(c, password="hunter2"):
    return c.post("/api/login", json={"password": password})


def test_open_when_no_password(client, fake):
    fake.on("stats", result={})
    assert client.get("/api/me").json() == {"auth_enabled": False, "authenticated": True}
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
