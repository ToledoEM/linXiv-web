from __future__ import annotations

import json
import os
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
    "projects": [{"id": 4, "name": "Old", "deleted_at": OLD}, {"id": 5, "deleted_at": NEW}],
}


def _app(settings, fake, stored):
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
    fake.on("trash", "hard-delete-project", result={"ok": True})
    return create_app(settings, fake)


def _run(c: TestClient) -> dict:
    job = c.post("/api/maintenance/cleanup/run").json()
    for _ in range(200):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("cleanup did not finish")


def _snapshots(data):
    names = ["papers.pre-restore", *(f"papers.pre-restore.{n}" for n in range(1, 5))]
    for i, name in enumerate(names):
        (data / name).write_bytes(b"db")
        os.utime(data / name, (1_000_000 + i, 1_000_000 + i))
    (data / "papers.pre-restore-wal").write_bytes(b"wal")
    return names


def test_cleanup_snapshots_and_old_trash(settings, fake):
    names = _snapshots(settings.data_dir)
    app = _app(settings, fake, {})
    with TestClient(app) as c:
        body = {"hour": 3, "nightly": [], "trash_days": 30}
        assert c.put("/api/maintenance/schedule", json=body).json()["trash_days"] == 30
        job = _run(c)
    assert job["result"] == {"snapshots_removed": 2, "papers_purged": 2, "projects_purged": 1}
    left = sorted(p.name for p in settings.data_dir.glob("papers.pre-restore*"))
    assert left == sorted(names[2:])  # the two oldest went, with the WAL beside one
    deleted = [a[-1] for a in fake.calls if a[:2] == ["trash", "hard-delete"]]
    assert deleted == ["arxiv:old", "arxiv:gone"]
    assert ["trash", "hard-delete-project", "--", "4"] in fake.calls
    assert ["trash", "hard-delete-project", "--", "5"] not in fake.calls


def test_cleanup_leaves_trash_by_default(settings, fake):
    with TestClient(_app(settings, fake, {})) as c:
        job = _run(c)
    assert job["result"] == {"snapshots_removed": 0, "papers_purged": 0, "projects_purged": 0}
    assert not any(a[:1] == ["trash"] for a in fake.calls)
