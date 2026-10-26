from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.maintenance import Maintenance
from app.maintenance_ops import OPS

DB = b"SQLite format 3\x00 backup"


def _app(settings, fake):
    stored: dict = {}

    def update(argv):
        stored[argv[-2]] = json.loads(argv[-1])
        return {}

    def backup(argv):
        Path(argv[-1]).write_bytes(DB)
        return {"path": argv[-1]}

    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=update)
    fake.on("backup", result=backup)
    app = create_app(settings, fake)
    clock = {"t": datetime(2026, 10, 26, 3, 0, tzinfo=UTC)}

    def now():
        clock["t"] += timedelta(minutes=1)
        return clock["t"]

    app.state.maintenance = Maintenance(app, OPS, now=now)
    return app


def _run(c: TestClient) -> dict:
    job = c.post("/api/maintenance/backup/run").json()
    for _ in range(200):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("backup did not finish")


def test_backups_kept_listed_downloaded_deleted(settings, fake):
    with TestClient(_app(settings, fake)) as c:
        body = {"hour": 3, "nightly": [], "keep_backups": 2}
        assert c.put("/api/maintenance/schedule", json=body).status_code == 200
        assert _run(c)["result"] == {"backed_up": 1, "removed": 0}
        _run(c)
        assert _run(c)["result"] == {"backed_up": 1, "removed": 1}
        listed = c.get("/api/maintenance/backups").json()["backups"]
        assert [b["library"] for b in listed] == ["root", "root"]
        names = [b["name"] for b in listed]
        assert names == sorted(names, reverse=True)
        assert all(b["size"] == len(DB) for b in listed)
        folder = settings.data_dir / "maintenance" / "backups"
        assert sorted(p.name for p in folder.iterdir()) == sorted(names)

        r = c.get(f"/api/maintenance/backups/root/{names[0]}")
        assert r.status_code == 200 and r.content == DB
        assert c.get("/api/maintenance/backups/root/papers.db").status_code == 404
        assert c.get(f"/api/maintenance/backups/u9/{names[0]}").status_code == 404
        assert c.get("/api/maintenance/backups/root/papers-20200101-000000.db").status_code == 404
        assert c.delete(f"/api/maintenance/backups/root/{names[1]}").json() == {"ok": True}
        assert [b["name"] for b in c.get("/api/maintenance/backups").json()["backups"]] == [
            names[0]
        ]


def test_backup_fails_when_cli_writes_nothing(settings, fake):
    app = _app(settings, fake)
    fake.on("backup", result={"path": "/nowhere.db"})
    with TestClient(app) as c:
        job = _run(c)
    assert job["errors"] == [{"source_id": "root", "error": "linxiv backup wrote no file"}]
