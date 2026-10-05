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
