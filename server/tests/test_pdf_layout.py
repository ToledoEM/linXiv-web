from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from app import pdf_layout as pl
from app.jobs import Job

PDF = b"%PDF-1.4 test"


def _db(data: Path, rows: list[tuple]) -> Path:
    """Minimal PAPER/PAPER_META with the columns pdf_layout reads and writes."""
    db = data / "papers.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE PAPER (PAPER_ID INTEGER PRIMARY KEY, SOURCE_ID TEXT, VERSION INTEGER,"
        " CATEGORY TEXT, HAS_PDF INTEGER);"
        "CREATE TABLE PAPER_META (PAPER_ID INTEGER, PUBLISHED TEXT, JOURNAL_REF TEXT, PDF_PATH TEXT);"
    )
    for i, (sid, ver, cat, pub, jref, path, has) in enumerate(rows, 1):
        conn.execute("INSERT INTO PAPER VALUES (?,?,?,?,?)", (i, sid, ver, cat, has))
        conn.execute("INSERT INTO PAPER_META VALUES (?,?,?,?)", (i, pub, jref, path))
    conn.commit()
    conn.close()
    return db


def _paths(db: Path) -> dict[str, str]:
    with sqlite3.connect(db) as c:
        q = "SELECT p.SOURCE_ID, m.PDF_PATH FROM PAPER p JOIN PAPER_META m USING (PAPER_ID)"
        return dict(c.execute(q).fetchall())


@pytest.fixture
def lib(dirs):
    data, _ = dirs
    pdf_dir = data / "pdfs"  # symlink to the real folder, like the container
    for name in ("arxiv_1706.03762v7.pdf", "doi_10.1038_xv1.pdf", "local_av1.pdf"):
        (pdf_dir / name).write_bytes(PDF)
    db = _db(
        data,
        [
            (
                "arxiv:1706.03762",
                7,
                "cs.CL",
                "2017-06-12",
                None,
                str(pdf_dir / "arxiv_1706.03762v7.pdf"),
                1,
            ),
            ("doi:10.1038/x", 1, "Nature / Bio: Tech?", "2024-08-01", None, None, 1),
            ("local:a", 1, "", "0001-01-01", "", str(pdf_dir / "local_av1.pdf"), 1),
            ("doi:10.9/gone", 1, "J", "2020-01-01", None, "/elsewhere/gone.pdf", 1),
        ],
    )
    return pl.PdfLayout(db, pdf_dir), db, pdf_dir


def test_folder_names_and_subdirs():
    assert pl.folder_name("Nature / Bio: Tech?", "x") == "Nature Bio Tech"
    assert pl.folder_name(" ../.. ", "x") == "x"
    assert pl.folder_name("a" * 200, "x") == "a" * pl.MAX_FOLDER
    assert pl.subdir("year/journal", "2017-06-12", "J") == Path("2017/J")
    assert pl.subdir("journal/year", None, "J") == Path("J/Unknown year")
    assert pl.subdir("none", "2017", "J") == Path()
    assert pl.safe_file_name("doi:10.1038/x", 1) == "doi_10.1038_xv1.pdf"


def test_plan_year_journal(lib):
    tool, _, _ = lib
    s = tool.summary(tool.plan("year/journal"))
    assert s["to_move"] == 3 and s["missing"] == 1 and s["conflicts"] == []
    to = {r["source_id"]: r["to"] for r in s["sample"]}
    assert to == {
        "arxiv:1706.03762": "2017/arXiv/arxiv_1706.03762v7.pdf",
        "doi:10.1038/x": "2024/Nature Bio Tech/doi_10.1038_xv1.pdf",
        "local:a": "Unknown year/Unknown journal/local_av1.pdf",
    }


def test_apply_moves_and_updates_db_then_flattens(lib):
    tool, db, pdf_dir = lib
    job = Job(id=1, kind="pdf-layout")
    asyncio.run(pl.apply(tool, "year/journal", job, asyncio.Lock()))
    assert job.result["moved"] == 3 and job.result["failed"] == 0
    paths = _paths(db)
    assert paths["doi:10.1038/x"] == str(pdf_dir / "2024/Nature Bio Tech/doi_10.1038_xv1.pdf")
    assert Path(paths["doi:10.1038/x"]).read_bytes() == PDF
    assert not (pdf_dir / "doi_10.1038_xv1.pdf").exists()
    assert paths["doi:10.9/gone"] == "/elsewhere/gone.pdf"  # missing file untouched
    # re-planning the same layout is a no-op
    assert tool.summary(tool.plan("year/journal"))["to_move"] == 0

    job = Job(id=2, kind="pdf-layout")
    asyncio.run(pl.apply(tool, "none", job, None))
    assert job.result["moved"] == 3
    assert _paths(db)["arxiv:1706.03762"] == str(pdf_dir / "arxiv_1706.03762v7.pdf")
    assert sorted(p.name for p in pdf_dir.iterdir()) == [
        "arxiv_1706.03762v7.pdf",
        "doi_10.1038_xv1.pdf",
        "local_av1.pdf",
    ]  # empty year/journal folders pruned


def test_db_failure_moves_file_back(lib, monkeypatch):
    tool, _, pdf_dir = lib
    move = next(m for m in tool.plan("year")["moves"] if m.source_id == "local:a")

    def broken():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(tool, "_connect", broken)
    with pytest.raises(sqlite3.OperationalError):
        tool.move_one(move)
    assert (pdf_dir / "local_av1.pdf").is_file()
    assert not move.dst.exists()


def test_conflict_and_escape_are_refused(lib):
    tool, _, pdf_dir = lib
    (pdf_dir / "2017").mkdir()
    (pdf_dir / "2017" / "arxiv_1706.03762v7.pdf").write_bytes(b"other")
    s = tool.summary(tool.plan("year"))
    assert len(s["conflicts"]) == 1 and "already exists" in s["conflicts"][0]
    m = tool.plan("journal")["moves"][0]
    m.dst = pdf_dir.parent / "outside.pdf"
    with pytest.raises(ValueError):
        tool.move_one(m)


def test_storage_counts_subfolders(dirs):
    _, pdfs = dirs
    (pdfs / "a.pdf").write_bytes(b"x" * 10)
    (pdfs / "2020").mkdir()
    (pdfs / "2020" / "b.pdf").write_bytes(b"x" * 5)
    assert pl.storage_bytes(pdfs) == 15


def test_routes(client, fake, dirs):
    data, pdfs = dirs
    (pdfs / "local_av1.pdf").write_bytes(PDF)
    _db(data, [("local:a", 1, "Genetics", "2013-01-01", None, str(data / "pdfs/local_av1.pdf"), 1)])
    r = client.get("/api/pdfs/layout/preview", params={"layout": "journal"})
    assert r.status_code == 200, r.text
    assert r.json()["sample"][0]["to"] == "Genetics/local_av1.pdf"
    assert client.get("/api/pdfs/layout/preview", params={"layout": "decade"}).status_code == 422
    fake.on("settings", "update", result={})
    with __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(client.app) as c:
        job = c.post("/api/jobs/pdf-layout", json={"layout": "journal"}).json()
        for _ in range(100):
            job = c.get(f"/api/jobs/{job['id']}").json()
            if job["state"] != "running":
                break
            asyncio.run(asyncio.sleep(0.02))
    assert job["state"] == "done" and job["result"]["moved"] == 1
    assert (pdfs / "Genetics" / "local_av1.pdf").is_file()
    assert ["settings", "update", "--", "web_pdf_folder_layout", "journal"] in fake.calls
