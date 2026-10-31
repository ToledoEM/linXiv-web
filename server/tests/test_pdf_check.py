from __future__ import annotations

import os
import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.pdf_layout import safe_file_name

from .test_duplicates import _library, _store

PAPERS = [
    ("doi:10.1/ok", 1, b"%PDF ok", False),
    ("doi:10.1/ok", 2, b"%PDF ok2", False),  # second version: extra file of one paper
    ("doi:10.1/gone", 1, b"%PDF gone", False),
    ("local:trashed-gone", 1, b"%PDF t", True),
    ("local:trashed-kept", 1, b"%PDF k", True),
    ("doi:10.1/nopdf", 1, None, False),
]
OLD = time.time() - 2 * 3600


def _setup(settings):
    data, pdfs = settings.data_dir, settings.pdf_dir
    _library(data, pdfs, PAPERS)
    (pdfs / safe_file_name("doi:10.1/gone", 1)).unlink()
    (pdfs / safe_file_name("local:trashed-gone", 1)).unlink()
    (pdfs / "2021").mkdir()
    (pdfs / "2021" / "stray.pdf").write_bytes(b"%PDF stray")
    (pdfs / "notes.txt").write_text("not a pdf")
    (pdfs / "dup").mkdir()
    (pdfs / "dup" / "copy.pdf").write_bytes(b"%PDF copy")
    for f in (pdfs / "2021" / "stray.pdf", pdfs / "dup" / "copy.pdf"):
        os.utime(f, (OLD, OLD))
    return pdfs


def _wait(c, job):
    for _ in range(200):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_pdf_check_reports_missing_unlinked_and_breakdown(settings, fake):
    _setup(settings)
    _store(fake)
    with TestClient(create_app(settings, fake)) as c:
        job = _wait(c, c.post("/api/maintenance/pdf-check/run").json())
        assert job["result"] == {"pdfs_checked": 5, "missing_files": 1, "unlinked_files": 2}
        [report] = c.get("/api/maintenance/pdf-check").json()["libraries"]
        assert report["library"] == "root" and report["checked_at"]
        assert report["missing"] == [
            {"source_id": "doi:10.1/gone", "version": 1, "title": "Title doi:10.1/gone"}
        ]
        assert [u["file"] for u in report["unlinked"]] == ["2021/stray.pdf", "dup/copy.pdf"]
        assert report["unlinked"][0]["size"] == len(b"%PDF stray")
        assert report["unlinked"][0]["modified"]
        assert report["papers"] == 3  # trashed roots left out
        assert report["papers_with_pdf"] == 1
        assert report["extra_versions"] == 1
        assert report["trashed_pdfs"] == 1
        disk = report["disk"]
        assert (disk["files"], disk["pdf_files"], disk["other_files"]) == (6, 5, 1)
        assert disk["skipped_files"] == 0
        folders = {f["folder"]: f for f in disk["by_folder"]}
        assert list(folders) == [".", "2021", "dup"]
        assert (folders["."]["files"], folders["."]["pdfs"]) == (4, 3)
        assert folders["dup"]["unlinked"] == 1

        # Skip dup/: counted, never listed as unlinked.
        r = c.put("/api/maintenance/pdf-check/options", json={"skip": ["dup", "orphans", "dup"]})
        assert r.json() == {"skip": ["dup"], "always": ["orphans"]}
        _wait(c, c.post("/api/maintenance/pdf-check/run").json())
        [report] = c.get("/api/maintenance/pdf-check").json()["libraries"]
        assert [u["file"] for u in report["unlinked"]] == ["2021/stray.pdf"]
        assert report["disk"]["skipped_files"] == 1
        assert report["skip"] == ["dup", "orphans"]

        csv = c.get("/api/maintenance/pdf-check/root/unlinked.csv")
        assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
        lines = csv.text.strip().splitlines()
        assert lines[0] == "file,size,modified" and lines[1].startswith("2021/stray.pdf,10,")
        assert c.get("/api/maintenance/pdf-check/nope/unlinked.csv").status_code == 404


def test_pdf_check_options_reject_paths(client):
    for bad in (["a/b"], [".."], ["."], [""], [" x"], ["a\\b"]):
        r = client.put("/api/maintenance/pdf-check/options", json={"skip": bad})
        assert r.status_code == 400, bad
    r = client.put("/api/maintenance/pdf-check/options", json={"skip": [str(i) for i in range(21)]})
    assert r.status_code == 422


def test_move_orphans_moves_only_old_unlinked_files(settings, fake):
    pdfs = _setup(settings)
    (pdfs / "fresh.pdf").write_bytes(b"%PDF fresh")  # just written: an import may own it
    (pdfs / "orphans" / "2021").mkdir(parents=True)
    (pdfs / "orphans" / "2021" / "stray.pdf").write_bytes(b"%PDF older orphan")
    _store(fake)
    with TestClient(create_app(settings, fake)) as c:
        c.put("/api/maintenance/pdf-check/options", json={"skip": ["dup"]})
        job = _wait(c, c.post("/api/maintenance/pdf-check/root/move-orphans").json())
        assert job["kind"] == "pdf-orphans" and job["state"] == "done", job
        assert job["result"] == {"moved": 1, "skipped_recent": 1, "failed": 0}
        [report] = c.get("/api/maintenance/pdf-check").json()["libraries"]
        assert [u["file"] for u in report["unlinked"]] == ["fresh.pdf"]
        assert c.post("/api/maintenance/pdf-check/nope/move-orphans").status_code == 404
    assert not (pdfs / "2021").exists()  # emptied folder pruned
    assert (pdfs / "orphans" / "2021" / "stray (2).pdf").read_bytes() == b"%PDF stray"
    assert (pdfs / "orphans" / "2021" / "stray.pdf").read_bytes() == b"%PDF older orphan"
    assert (pdfs / "dup" / "copy.pdf").exists()  # skipped folder untouched
    assert (pdfs / safe_file_name("doi:10.1/ok", 1)).exists()  # linked file untouched
    assert (pdfs / safe_file_name("local:trashed-kept", 1)).exists()  # trashed paper owns it


def test_move_orphans_refused_while_a_job_runs(settings, fake):
    _setup(settings)
    _store(fake)
    with TestClient(create_app(settings, fake)) as c:
        jobs = c.app.state.jobs
        jobs.running = lambda kind, library=None: type("J", (), {"kind": "pdf-layout"})()
        r = c.post("/api/maintenance/pdf-check/root/move-orphans")
    assert r.status_code == 409 and "pdf-layout" in r.json()["detail"]


def test_pdf_check_report_empty_before_any_run(client):
    assert client.get("/api/maintenance/pdf-check").json() == {"libraries": []}
