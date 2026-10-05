from __future__ import annotations

from app.cli import CLIError

from .conftest import fixture

SID = "arxiv:1706.03762"


def test_new(client, fake):
    fake.on("versions", "new", result=fixture("versions-new.json"))
    r = client.get("/api/versions/new")
    assert r.json()["new_versions"][0]["version"] == 7
    assert fake.calls[-1] == ["versions", "new"]


def test_check_default_and_limit(client, fake):
    fake.on("versions", "check", result=fixture("versions-check-hit.json"))
    assert client.post("/api/versions/check").json()["checked"] == 1
    assert fake.calls[-1] == ["versions", "check", "--limit=20"]
    client.post("/api/versions/check", json={"limit": 100})
    assert fake.calls[-1] == ["versions", "check", "--limit=100"]
    for bad in ({"limit": 0}, {"limit": 101}, {"limit": "5"}, {"x": 1}):
        assert client.post("/api/versions/check", json=bad).status_code == 422
    assert len(fake.calls) == 2


def test_ack(client, fake):
    fake.on("versions", "ack", result={"ok": True})
    assert client.post(f"/api/versions/{SID}/ack").json() == {"ok": True}
    assert fake.calls[-1] == ["versions", "ack", "--", SID]


def test_ack_twice_is_ok_but_unknown_paper_is_not(client, fake):
    fake.on("versions", "ack", result=CLIError(502, "no new version flagged for this paper"))
    r = client.post(f"/api/versions/{SID}/ack")
    assert r.json() == {"ok": True, "already_acknowledged": True}
    fake.on("versions", "ack", result=CLIError(404, "Paper nope:1 not found"))
    assert client.post("/api/versions/nope:1/ack").status_code == 404
