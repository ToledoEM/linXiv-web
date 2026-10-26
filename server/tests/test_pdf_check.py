from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.pdf_layout import safe_file_name

from .test_duplicates import _library, _store


def test_pdf_check_reports_missing_and_unlinked(settings, fake):
    data, pdfs = settings.data_dir, settings.pdf_dir
    _library(
        data,
        pdfs,
        [
            ("doi:10.1/ok", 1, b"%PDF ok", False),
            ("doi:10.1/gone", 1, b"%PDF gone", False),
            ("local:trashed-gone", 1, b"%PDF t", True),
            ("local:trashed-kept", 1, b"%PDF k", True),
            ("doi:10.1/nopdf", 1, None, False),
        ],
    )
    (pdfs / safe_file_name("doi:10.1/gone", 1)).unlink()
    (pdfs / safe_file_name("local:trashed-gone", 1)).unlink()
    (pdfs / "2021").mkdir()
    (pdfs / "2021" / "stray.pdf").write_bytes(b"%PDF stray")
    (pdfs / "notes.txt").write_text("not a pdf")
    _store(fake)
    with TestClient(create_app(settings, fake)) as c:
        job = c.post("/api/maintenance/pdf-check/run").json()
        for _ in range(200):
            job = c.get(f"/api/jobs/{job['id']}").json()
            if job["state"] != "running":
                break
            time.sleep(0.02)
        assert job["result"] == {"pdfs_checked": 4, "missing_files": 1, "unlinked_files": 1}
        [report] = c.get("/api/maintenance/pdf-check").json()["libraries"]
    assert report["library"] == "root" and report["checked_at"]
    assert report["missing"] == [
        {"source_id": "doi:10.1/gone", "version": 1, "title": "Title doi:10.1/gone"}
    ]
    assert report["unlinked"] == [{"file": "2021/stray.pdf", "size": len(b"%PDF stray")}]


def test_pdf_check_report_empty_before_any_run(client):
    assert client.get("/api/maintenance/pdf-check").json() == {"libraries": []}
