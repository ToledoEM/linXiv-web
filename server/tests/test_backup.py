from __future__ import annotations

from pathlib import Path

from app.cli import CLIError
from app.jobs import Job

from .conftest import fixture

DB = b"SQLite format 3\x00" + b"\x00" * 100


def _write_backup(argv):
    dest = Path(argv[-1])
    dest.write_bytes(DB)
    return {"path": str(dest), "bytes": len(DB)}


def test_download_backup(client, fake):
    fake.on("backup", result=_write_backup)
    r = client.get("/api/backup")
    assert r.status_code == 200, r.text
    assert r.content == DB
    assert r.headers["content-disposition"].startswith('attachment; filename="linxiv-backup-')
    dest = Path(fake.calls[-1][-1])
    assert fake.calls[-1][:2] == ["backup", "--"]
    assert not dest.parent.exists()  # temp dir removed after sending


def test_download_backup_rejects_outside_path(client, fake, tmp_path):
    outside = tmp_path / "x.db"
    outside.write_bytes(DB)
    fake.on("backup", result={"path": str(outside), "bytes": 1})
    assert client.get("/api/backup").status_code == 502


def test_import_backup(client, fake):
    seen = {}

    def imp(argv):
        seen["path"] = Path(argv[-1])
        seen["data"] = seen["path"].read_bytes()
        return fixture("backup-import.json")

    fake.on("import", result=imp)
    r = client.post("/api/backup/import", files={"file": ("b.db", DB)})
    assert r.status_code == 200, r.text
    assert r.json()["pdf_refs_cleared"] == 2
    assert fake.calls[-1][:2] == ["import", "--"]
    assert seen["data"] == DB
    assert not seen["path"].exists()


def test_upload_validation(client, fake):
    for path in ("/api/backup/import", "/api/backup/restore"):
        assert client.post(path, files={"file": ("b.db", b"")}).status_code == 400
        assert client.post(path, files={"file": ("b.db", b"hello world")}).status_code == 400
        big = DB + b"\x00" * (1024 * 1024)
        assert client.post(path, files={"file": ("b.db", big)}).status_code == 413
    assert fake.calls == []


def test_cli_rejects_file(client, fake):
    fake.on("import", result=CLIError(502, "not a valid linXiv database: no PAPER table"))
    fake.on("restore", result=CLIError(502, "not a valid SQLite database: file is not a database"))
    assert client.post("/api/backup/import", files={"file": ("b.db", DB)}).status_code == 400
    assert client.post("/api/backup/restore", files={"file": ("b.db", DB)}).status_code == 400


def test_restore_backup(client, fake):
    fake.on("restore", result={"restored": "/data/papers.db"})
    r = client.post("/api/backup/restore", files={"file": ("b.db", DB)})
    assert r.status_code == 200, r.text
    assert fake.calls[-1][:2] == ["restore", "--"]


def test_restore_db_in_use(client, fake):
    msg = "database is in use by another linXiv process (app, CLI, or MCP server)"
    fake.on("restore", result=CLIError(502, msg))
    assert client.post("/api/backup/restore", files={"file": ("b.db", DB)}).status_code == 409


def test_restore_refused_while_job_runs(client, fake):
    client.app.state.jobs._jobs[1] = Job(id=1, kind="index-sources")
    r = client.post("/api/backup/restore", files={"file": ("b.db", DB)})
    assert r.status_code == 409
    assert "index-sources" in r.json()["detail"]
    assert fake.calls == []
