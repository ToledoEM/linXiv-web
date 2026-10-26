from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.cli import CLIError
from app.main import create_app

OLD = (datetime.now(UTC) - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%S")
NEW = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
TRASH = {
    "papers": [
        {"source_id": "arxiv:old", "deleted_at": OLD},
        {"source_id": "arxiv:gone", "deleted_at": OLD},
        {"source_id": "arxiv:recent", "deleted_at": NEW},
    ],
    "projects": [{"id": 4, "name": "Old", "deleted_at": OLD}],
}


def _app(settings, fake):
    stored: dict = {}

    def update(argv):
        stored[argv[-2]] = json.loads(argv[-1])
        return {}

    def hard_delete(argv):
        if argv[-1] == "arxiv:gone":  # deleted, then "not found" (older linxiv)
            raise CLIError(404, "Paper arxiv:gone not found")
        return {"ok": True}

    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=update)
    fake.on("trash", "list", result=TRASH)
    fake.on("trash", "hard-delete", result=hard_delete)
    return create_app(settings, fake)


def _run(c: TestClient) -> dict:
    job = c.post("/api/maintenance/empty-trash/run").json()
    for _ in range(200):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("empty trash did not finish")


def test_empty_trash_deletes_old_papers_only(settings, fake):
    with TestClient(_app(settings, fake)) as c:
        body = {"hour": 3, "nightly": [], "trash_days": 30}
        assert c.put("/api/maintenance/schedule", json=body).json()["trash_days"] == 30
        job = _run(c)
    assert job["result"] == {"papers_purged": 2}
    deleted = [a[-1] for a in fake.calls if a[:2] == ["trash", "hard-delete"]]
    assert deleted == ["arxiv:old", "arxiv:gone"]
    assert not any(a[:2] == ["trash", "hard-delete-project"] for a in fake.calls)


def test_empty_trash_off_by_default(settings, fake):
    with TestClient(_app(settings, fake)) as c:
        job = _run(c)
    assert job["result"] == {"papers_purged": 0}
    assert not any(a[:1] == ["trash"] for a in fake.calls)


def test_trash_days_range(settings, fake):
    with TestClient(_app(settings, fake)) as c:
        for days, code in ((0, 200), (1, 200), (120, 200), (121, 422), (-1, 422)):
            body = {"hour": 3, "nightly": [], "trash_days": days}
            assert c.put("/api/maintenance/schedule", json=body).status_code == code, days
