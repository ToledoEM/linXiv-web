from __future__ import annotations

import csv
import io
import json

from app import activity


def _events(settings) -> list[dict]:
    return activity.read(settings.data_dir, 100)


def test_writes_recorded_reads_not(client, fake, settings):
    fake.on("paper", "delete", result={})
    fake.on("stats", result={})
    client.get("/api/stats")
    client.delete("/api/papers/arxiv:2401.00001")
    [e] = _events(settings)
    assert e["method"] == "DELETE"
    assert e["route"] == "/api/papers/{source_id:path}"
    assert e["target"] == {"source_id": "arxiv:2401.00001"}
    assert e["status"] == 200
    assert e["at"].endswith("Z")


def test_settings_change_records_names_not_values(client, fake, settings):
    stored: dict = {}
    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result={})
    secret = "sk-test-SECRET-0123456789"
    client.patch("/api/settings", json={"OPENAI_API_KEY": secret, "ai_enabled": True})
    [e] = _events(settings)
    assert e["fields"] == ["OPENAI_API_KEY", "ai_enabled"]
    assert secret not in activity.path(settings.data_dir).read_text()


def test_failed_login_recorded_without_password(auth_client, settings):
    auth_client.post("/api/login", json={"password": "wrong-guess-123"})
    [e] = _events(settings)
    assert (e["route"], e["status"]) == ("/api/login", 401)
    assert "wrong-guess" not in activity.path(settings.data_dir).read_text()


def test_clear_needs_phrase_and_records_itself(client, fake, settings):
    fake.on("paper", "delete", result={})
    client.delete("/api/papers/x")
    bad = client.request("DELETE", "/api/activity", json={"confirm": "yes"})
    assert bad.status_code == 400
    ok = client.request("DELETE", "/api/activity", json={"confirm": activity.CLEAR_PHRASE})
    assert ok.status_code == 200
    [e] = _events(settings)
    assert (e["method"], e["route"], e["status"]) == ("DELETE", "/api/activity", 200)


def test_read_newest_first_and_csv(client, fake, settings):
    fake.on("paper", "delete", result={})
    for sid in ("a", "b"):
        client.delete(f"/api/papers/{sid}")
    events = client.get("/api/activity").json()["events"]
    assert [e["target"]["source_id"] for e in events] == ["b", "a"]
    r = client.get("/api/activity/export")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert [json.loads(row["target"])["source_id"] for row in rows] == ["b", "a"]


def test_rotation_keeps_one_old_file(settings, monkeypatch):
    monkeypatch.setattr(activity, "MAX_BYTES", 200)
    for i in range(10):
        activity.record(settings.data_dir, {"method": "POST", "route": f"/api/x{i}"})
    p = activity.path(settings.data_dir)
    assert p.with_name(activity.FILE + ".1").exists()
    assert p.stat().st_size <= 200
    assert _events(settings)[0]["route"] == "/api/x9"
    assert p.stat().st_mode & 0o777 == 0o600


def test_write_failure_never_raises(settings, monkeypatch):
    def broken(*a, **k):
        raise OSError("read-only file system")

    monkeypatch.setattr(activity.os, "open", broken)
    activity.record(settings.data_dir, {"method": "POST"})  # no exception
