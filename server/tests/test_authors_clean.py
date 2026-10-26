from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from app.cli import CLIError
from app.main import create_app

AUTHORS = [
    {"author_id": 1, "full_name": "Ashish Vaswani", "paper_count": 3},
    {"author_id": 2, "full_name": "Nobody Left", "paper_count": 0},
    {"author_id": 3, "full_name": "Raced Back", "paper_count": 0},
]


def test_clean_authors_removes_only_authors_without_papers(settings, fake):
    stored: dict = {}

    def update(argv):
        stored[argv[-2]] = json.loads(argv[-1])
        return {}

    def delete(argv):
        if argv[-1] == "3":  # linked again since the list was read
            raise CLIError(409, "author 3 is linked to 1 paper")
        return {"ok": True}

    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=update)
    fake.on("author", "list", result=AUTHORS)
    fake.on("author", "delete", result=delete)
    with TestClient(create_app(settings, fake)) as c:
        job = c.post("/api/maintenance/clean-authors/run").json()
        for _ in range(200):
            job = c.get(f"/api/jobs/{job['id']}").json()
            if job["state"] != "running":
                break
            time.sleep(0.02)
        ops = {o["id"]: o for o in c.get("/api/maintenance").json()["ops"]}
    assert job["result"] == {"authors_removed": 1, "skipped": 1}
    assert not job["errors"]
    deleted = [a[-1] for a in fake.calls if a[:2] == ["author", "delete"]]
    assert deleted == ["2", "3"]
    assert ops["clean-authors"]["destructive"] is True
    assert ops["empty-trash"]["destructive"] is True
    assert "cleanup" not in ops
