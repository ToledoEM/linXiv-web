from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest

from app import update_check
from app.update_check import UpdateChecker, UpdateError, latest_tag

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def test_latest_tag_picks_highest_semver():
    assert latest_tag(["0.1.0", "sha-abc", "0.10.0", "v0.9.9", "latest", "0.2.0"]) == "0.10.0"
    assert latest_tag(["latest", "main"]) is None


def _store(fake, stored):
    def update(argv):
        stored[argv[-2]] = json.loads(argv[-1])
        return {}

    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=update)


async def _tags(_token):
    return ["0.1.0", "0.2.0"]


def _checker(fake, fetch=_tags, now=NOW):
    return UpdateChecker(fake, "0.1.0", 5, fetch=fetch, now=lambda: now)


def test_check_stores_result_and_view(fake):
    stored: dict = {"web_update_check": "weekly"}
    _store(fake, stored)
    view = asyncio.run(_checker(fake).check())
    assert view["latest"] == "0.2.0" and view["update_available"] is True
    assert view["mode"] == "weekly" and view["image"] == "ghcr.io/toledoem/linxiv-web"
    assert json.loads(stored["web_update_status"])["checked_at"] == "2026-10-10T12:00:00+00:00"


def test_check_error_keeps_last_latest(fake):
    async def private(_token):
        raise UpdateError("image not readable: the package is private")

    stored = {"web_update_status": json.dumps({"latest": "0.2.0"})}
    _store(fake, stored)
    view = asyncio.run(_checker(fake, fetch=private).check())
    assert view["error"].startswith("image not readable") and view["latest"] == "0.2.0"


def test_step_schedule(fake):
    stored: dict = {"web_update_check": "off"}
    _store(fake, stored)
    calls = []

    async def count(token):
        calls.append(token)
        return ["0.1.0"]

    c = _checker(fake, fetch=count)
    assert asyncio.run(c.step()) == update_check.OFF_POLL and calls == []
    stored["web_update_check"] = "daily"
    asyncio.run(c.step())  # never checked: due now
    assert len(calls) == 1
    wait = asyncio.run(c.step())  # just checked: next in a day, capped
    assert len(calls) == 1 and wait == update_check.MAX_WAIT


def test_fetch_tags_token_flow(monkeypatch):
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        if req.url.path == "/token":
            return httpx.Response(200, json={"token": "pull"})
        assert req.headers["authorization"] == "Bearer pull"
        return httpx.Response(200, json={"tags": ["0.3.0"]})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        update_check, "_client", lambda: real(transport=httpx.MockTransport(handler))
    )
    assert asyncio.run(update_check.fetch_tags("ghp_secret")) == ["0.3.0"]
    assert seen[0].headers["authorization"].startswith("Basic ")

    monkeypatch.setattr(
        update_check,
        "_client",
        lambda: real(transport=httpx.MockTransport(lambda r: httpx.Response(401))),
    )
    with pytest.raises(UpdateError, match="private"):
        asyncio.run(update_check.fetch_tags())


def test_update_routes(client, fake, monkeypatch):
    stored: dict = {}
    _store(fake, stored)
    monkeypatch.setattr(client.app.state.update_checker, "fetch", _tags)
    assert client.get("/api/update").json()["latest"] is None
    r = client.post("/api/update/check")
    assert r.status_code == 200 and r.json()["update_available"] is True
    assert client.get("/api/update").json()["latest"] == "0.2.0"


def test_settings_update_mode_and_token(client, fake):
    stored: dict = {}
    _store(fake, stored)
    r = client.patch(
        "/api/settings", json={"web_update_check": "weekly", "GHCR_TOKEN": "ghp_12345678"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["settings"]["web_update_check"] == "weekly"
    assert body["settings"]["GHCR_TOKEN"] == ""
    assert body["ghcr_token"] == {"set": True, "last4": "5678", "source": "settings"}
    assert client.patch("/api/settings", json={"web_update_check": "hourly"}).status_code == 422


def test_system_status_disk_and_issues(client, fake, dirs):
    stored = {"pdf_save_limit_mb": 1, "web_update_status": json.dumps({"latest": "9.0.0"})}
    _store(fake, stored)
    _data, pdfs = dirs
    (pdfs / "big.pdf").write_bytes(b"%PDF" + b"0" * 1024 * 1024)
    body = client.get("/api/system/status").json()
    assert [d["label"].split(" ")[0] for d in body["disk"]] == ["Data", "PDFs", "Logs"]
    assert all(d["total"] > 0 for d in body["disk"])
    levels = {i["level"]: i["message"] for i in body["issues"]}
    assert "PDF storage limit" in levels["error"]
    assert "9.0.0 is available" in levels["info"]


def test_system_status_cli_down(client, fake):
    from app.cli import CLIError

    fake.on("settings", "get", result=CLIError(502, "boom"))
    body = client.get("/api/system/status").json()
    assert body["issues"][0] == {"level": "error", "message": "linxiv CLI not responding: boom"}
