from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from app.main import create_app


def test_security_headers(client):
    h = client.get("/api/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "SAMEORIGIN"
    assert "camera=()" in h["permissions-policy"]
    assert "frame-ancestors 'self'" in h["content-security-policy"]
    assert "strict-transport-security" not in h


def test_hsts_when_enabled(settings, fake):
    c = TestClient(create_app(replace(settings, hsts=True), fake))
    assert c.get("/api/health").headers["strict-transport-security"] == "max-age=31536000"


def test_unexpected_error_is_json_without_internals(settings, fake):
    def boom(_argv):
        raise RuntimeError("secret internal detail")

    fake.on("stats", result=boom)
    c = TestClient(create_app(settings, fake), raise_server_exceptions=False)
    r = c.get("/api/stats")
    assert r.status_code == 500
    assert r.json() == {"detail": "internal server error"}
    assert "secret" not in r.text
