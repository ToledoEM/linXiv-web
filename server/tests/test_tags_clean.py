from __future__ import annotations

import json
import sqlite3
import time

from fastapi.testclient import TestClient

from app.cli import CLIError
from app.main import create_app

SCHEMA = """
CREATE TABLE TAG(TAG_FK INTEGER PRIMARY KEY AUTOINCREMENT, TAG TEXT);
CREATE TABLE PAPER_TO_TAG(PTT_FK INTEGER PRIMARY KEY, PAPER_ID INTEGER, TAG_FK INTEGER);
CREATE TABLE PROJECT_TO_TAG(PROJECT_TO_TAG_FK INTEGER PRIMARY KEY, PROJECT_FK INTEGER,
                            TAG_FK INTEGER);
"""

# id: label, then which ones a paper / project carries.
TAGS = {1: "used", 2: "empty", 3: "Untagged", 4: "reading-list", 5: "raced", 6: "refused"}


def _db(path, papers=(1,), projects=(4,)):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO TAG VALUES (?, ?)", TAGS.items())
    conn.executemany(
        "INSERT INTO PAPER_TO_TAG (PAPER_ID, TAG_FK) VALUES (1, ?)", [(t,) for t in papers]
    )
    conn.executemany(
        "INSERT INTO PROJECT_TO_TAG (PROJECT_FK, TAG_FK) VALUES (1, ?)", [(t,) for t in projects]
    )
    conn.commit()
    conn.close()


def _run(c, op):
    job = c.post(f"/api/maintenance/{op}/run").json()
    for _ in range(200):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["state"] != "running":
            break
        time.sleep(0.02)
    return job


def test_clean_tags_removes_only_tags_without_papers_or_projects(settings, fake):
    db = settings.data_dir / "papers.db"
    _db(db)
    stored: dict = {}

    def update(argv):
        stored[argv[-2]] = json.loads(argv[-1])
        return {}

    deleted: list[str] = []

    def delete(argv):
        tag_id = argv[-1]
        if tag_id == "2":
            # A paper picks up "raced" while the op works through the list.
            conn = sqlite3.connect(db)
            conn.execute("INSERT INTO PAPER_TO_TAG (PAPER_ID, TAG_FK) VALUES (2, 5)")
            conn.commit()
            conn.close()
        if tag_id == "6":
            raise CLIError(404, "tag not found")
        deleted.append(tag_id)
        return {"deleted_tag_id": int(tag_id)}

    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=update)
    fake.on("tag", "delete", result=delete)
    with TestClient(create_app(settings, fake)) as c:
        job = _run(c, "clean-tags")
        ops = {o["id"]: o for o in c.get("/api/maintenance").json()["ops"]}
    assert not job["errors"], job
    assert job["result"] == {"tags_removed": 1, "skipped": 2}
    assert deleted == ["2"]  # used, Untagged and the project tag are never tried
    tried = [a[-1] for a in fake.calls if a[:2] == ["tag", "delete"]]
    assert tried == ["2", "6"]  # "raced" was linked again before its turn
    assert ops["clean-tags"]["destructive"] is True


def test_clean_tags_without_database_does_nothing(settings, fake):
    stored: dict = {}
    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=lambda argv: stored.update({argv[-2]: argv[-1]}) or {})
    with TestClient(create_app(settings, fake)) as c:
        job = _run(c, "clean-tags")
    assert job["result"] == {"tags_removed": 0, "skipped": 0}
    assert not [a for a in fake.calls if a[:2] == ["tag", "delete"]]
