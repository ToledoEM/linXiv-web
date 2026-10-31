from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.duplicates import groups_of
from app.main import create_app
from app.pdf_layout import safe_file_name

SCHEMA = """
CREATE TABLE PAPER_ROOTS (SOURCE_FK INTEGER PRIMARY KEY, SOURCE_ID TEXT, DELETED_AT TIMESTAMP);
CREATE TABLE PAPER (PAPER_ID INTEGER PRIMARY KEY, SOURCE_ID TEXT, VERSION INTEGER, TITLE TEXT,
                    HAS_PDF BOOL, SOURCE_FK INTEGER);
CREATE TABLE PAPER_META (PAPER_ID INTEGER PRIMARY KEY, PDF_PATH TEXT);
"""


def _library(data: Path, pdfs: Path, papers: list[tuple[str, int, bytes | None, bool]]) -> None:
    """papers: (source_id, version, pdf bytes or None, trashed)."""
    db = sqlite3.connect(data / "papers.db")
    db.executescript(SCHEMA)
    roots: dict[str, int] = {}
    for pid, (sid, version, pdf, trashed) in enumerate(papers, 1):
        if sid not in roots:
            roots[sid] = len(roots) + 1
            db.execute(
                "INSERT INTO PAPER_ROOTS VALUES (?, ?, ?)",
                (roots[sid], sid, "2026-01-01" if trashed else None),
            )
        path = None
        if pdf is not None:
            path = pdfs / safe_file_name(sid, version)
            path.write_bytes(pdf)
        db.execute(
            "INSERT INTO PAPER VALUES (?, ?, ?, ?, ?, ?)",
            (pid, sid, version, f"Title {sid}", pdf is not None, roots[sid]),
        )
        db.execute("INSERT INTO PAPER_META VALUES (?, ?)", (pid, str(path) if path else None))
    db.commit()
    db.close()


SAME = b"%PDF-1.4 same"
PAPERS = [
    ("doi:10.1/a", 1, SAME, False),
    ("local:abc", 1, SAME, False),
    ("arxiv:1", 1, b"%PDF-1.4 v", False),
    ("arxiv:1", 2, b"%PDF-1.4 v", False),  # versions of one paper: not duplicates
    ("local:old", 1, SAME, True),  # in the trash: left out
    ("doi:10.1/none", 1, None, False),
]


def _scan(c: TestClient) -> dict:
    job = c.post("/api/maintenance/duplicates/run").json()
    for _ in range(200):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("scan did not finish")


def _store(fake):
    stored: dict = {}

    def update(argv):
        stored[argv[-2]] = json.loads(argv[-1])
        return {}

    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=update)


def test_scan_groups_identical_files(settings, fake):
    data, pdfs = settings.data_dir, settings.pdf_dir
    _library(data, pdfs, PAPERS)
    _store(fake)
    with TestClient(create_app(settings, fake)) as c:
        job = _scan(c)
        assert job["state"] == "done", job
        assert job["result"] == {"pdfs": 4, "hashed": 4, "duplicate_groups": 1}
        got = c.get("/api/duplicates").json()
        assert got["scanned_at"]
        [group] = got["groups"]
        assert [p["source_id"] for p in group["papers"]] == ["doi:10.1/a", "local:abc"]
        assert group["papers"][0] == {
            "source_id": "doi:10.1/a",
            "version": 1,
            "title": "Title doi:10.1/a",
            "file": "doi_10.1_av1.pdf",
            "size": len(SAME),
        }
        # unchanged files come from the cache
        assert _scan(c)["result"]["hashed"] == 0


def test_merge_and_dismiss(settings, fake):
    _library(
        settings.data_dir,
        settings.pdf_dir,
        [*PAPERS, ("local:x", 1, b"%PDF x", False), ("local:y", 1, b"%PDF x", False)],
    )
    _store(fake)
    fake.on("paper", "merge", result={"winner": "doi:10.1/a"})
    with TestClient(create_app(settings, fake)) as c:
        _scan(c)
        assert len(c.get("/api/duplicates").json()["groups"]) == 2
        bad = c.post("/api/duplicates/merge", json={"winner": "local:x", "loser": "local:abc"})
        assert bad.status_code == 404
        assert (
            c.post(
                "/api/duplicates/merge", json={"winner": "local:x", "loser": "local:x"}
            ).status_code
            == 400
        )
        r = c.post("/api/duplicates/merge", json={"winner": "doi:10.1/a", "loser": "local:abc"})
        assert r.status_code == 200, r.text
        assert fake.calls[-1] == ["paper", "merge", "--", "doi:10.1/a", "local:abc"]
        assert [g["papers"][0]["source_id"] for g in r.json()["groups"]] == ["local:x"]
        r = c.post("/api/duplicates/dismiss", json={"source_ids": ["local:y", "local:x"]})
        assert r.status_code == 200 and r.json()["groups"] == []
        # a later scan keeps the dismissed group hidden
        _scan(c)
        assert [
            [p["source_id"] for p in g["papers"]] for g in c.get("/api/duplicates").json()["groups"]
        ] == [["doi:10.1/a", "local:abc"]]


def test_no_library_yet(settings, fake):
    _store(fake)
    with TestClient(create_app(settings, fake)) as c:
        assert _scan(c)["result"] == {"pdfs": 0, "hashed": 0, "duplicate_groups": 0}
        assert c.get("/api/duplicates").json()["groups"] == []


def test_groups_of_ignores_versions_of_one_paper():
    files = [
        {"source_id": "a", "version": 1, "title": "", "file": "a1", "size": 1, "sha256": "h"},
        {"source_id": "a", "version": 2, "title": "", "file": "a2", "size": 1, "sha256": "h"},
    ]
    assert groups_of(files, set()) == []


def test_export_tsv_lists_groups_one_row_per_paper(settings, fake):
    _library(settings.data_dir, settings.pdf_dir, PAPERS)
    _store(fake)
    with TestClient(create_app(settings, fake)) as c:
        empty = c.get("/api/duplicates/export.tsv")
        assert empty.status_code == 200
        assert empty.text == "group\tsha256\tsource_id\tversion\ttitle\tfile\tsize\n"
        _scan(c)
        r = c.get("/api/duplicates/export.tsv")
    assert r.headers["content-type"].startswith("text/tab-separated-values")
    assert 'filename="duplicates-root.tsv"' in r.headers["content-disposition"]
    header, *rows = [line.split("\t") for line in r.text.strip().split("\n")]
    assert header == ["group", "sha256", "source_id", "version", "title", "file", "size"]
    assert [(row[0], row[2]) for row in rows] == [("1", "doi:10.1/a"), ("1", "local:abc")]
    assert rows[0][4] == "Title doi:10.1/a" and rows[0][6] == str(len(SAME))
    assert len(rows[0][1]) == 64  # sha256 hex
