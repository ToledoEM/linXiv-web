from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import logs
from app.cli import CLIError, LinxivCLI
from app.main import create_app


def _stamp(delta: timedelta) -> str:
    t = datetime.now(UTC) - delta
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def _log_file(data_dir):
    return logs.log_dir(data_dir) / logs.FILE


def test_setup_writes_utc_lines_and_is_idempotent(settings):
    logs.setup(settings.data_dir, "info")
    logs.setup(settings.data_dir, "info")
    logging.getLogger("app.test").info("hello %s", "there")
    text = _log_file(settings.data_dir).read_text()
    assert text.count("hello there") == 1
    line = text.strip().splitlines()[-1]
    assert logs._STAMP.match(line + " ") or logs._STAMP.match(line)
    assert " INFO    app.test: hello there" in line


def test_level_filters_and_set_level(settings):
    logs.setup(settings.data_dir, "warning")
    logging.getLogger("app.test").info("quiet")
    logs.set_level("debug")
    logging.getLogger("app.test").debug("loud")
    text = _log_file(settings.data_dir).read_text()
    assert "quiet" not in text and "loud" in text
    assert logs.level_name() == "debug"
    logs.set_level("info")


def test_window_keeps_continuation_lines_and_reads_rotated_first(settings):
    folder = logs.log_dir(settings.data_dir)
    folder.mkdir(exist_ok=True)
    old, new = _stamp(timedelta(days=3)), _stamp(timedelta(minutes=5))
    (folder / f"{logs.FILE}.1").write_text(
        f"{old} ERROR   app: old boom\nTraceback old\n{new} ERROR   app: rotated new\n"
    )
    (folder / logs.FILE).write_text(f"{new} ERROR   app: boom\nTraceback (most recent)\n")
    lines, truncated = logs.read(settings.data_dir, "24h", 100)
    assert [line.split(": ", 1)[-1] for line in lines] == [
        "rotated new",
        "boom",
        "Traceback (most recent)",
    ]
    assert not truncated
    every, _ = logs.read(settings.data_dir, "all", 100)
    assert every[:2] == [f"{old} ERROR   app: old boom", "Traceback old"]
    tail, truncated = logs.read(settings.data_dir, "all", 2)
    assert truncated and tail[-1] == "Traceback (most recent)"


def test_redact_masks_secret_setting_values():
    assert logs.redact(["settings", "update", "--", "GEMINI_API_KEY", '"abc12345"']) == (
        "settings update -- GEMINI_API_KEY ***"
    )
    assert logs.redact(["settings", "update", "--", "ARXIV_MAILTO", "a@b.c"]).endswith("a@b.c")
    assert logs.redact(["paper", "get", "--", "x" * 300]).endswith("x" * 200 + "…")


def test_clear_empties_current_and_removes_rotated(settings):
    logs.setup(settings.data_dir, "info")
    logging.getLogger("app.test").info("before")
    (logs.log_dir(settings.data_dir) / f"{logs.FILE}.2").write_text("x\n")
    logs.clear(settings.data_dir)
    logging.getLogger("app.test").info("after")
    text = _log_file(settings.data_dir).read_text()
    assert "before" not in text and "after" in text
    assert [p.name for p in logs.files(settings.data_dir)] == [logs.FILE]


def test_routes_read_export_clear(client, settings):
    client.get("/api/nothing-here")
    r = client.get("/api/logs", params={"window": "1h"})
    assert r.status_code == 200
    body = r.json()
    assert any("GET /api/nothing-here 404" in line for line in body["lines"])
    assert body["level"] == "info"
    assert body["files"][0]["name"] == logs.FILE
    r = client.get("/api/logs/export", params={"window": "all"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert 'attachment; filename="linxiv-web-' in r.headers["content-disposition"]
    assert "GET /api/nothing-here 404" in r.text
    assert client.get("/api/logs", params={"window": "2y"}).status_code == 422
    assert client.delete("/api/logs").status_code == 200
    lines = client.get("/api/logs", params={"window": "all"}).json()["lines"]
    assert not any("nothing-here" in line for line in lines)


def test_logs_need_login(settings, fake):
    c = TestClient(create_app(replace(settings, password="hunter2"), fake))
    assert c.get("/api/logs").status_code == 401
    assert c.get("/api/logs/export").status_code == 401
    assert c.delete("/api/logs").status_code == 401


def test_upstream_5xx_detail_is_logged(client, fake, settings, monkeypatch):
    from fastapi import HTTPException

    from app.routes import metadata

    async def down(doi):
        raise HTTPException(status_code=502, detail="bioRxiv lookup failed (503)")

    monkeypatch.setattr(metadata, "_biorxiv", down)
    fake.on("paper", "get", result={"source_id": "doi:10.1101/x", "doi": "10.1101/x"})
    r = client.get("/api/papers/doi:10.1101/x/lookup", params={"source": "biorxiv"})
    assert r.status_code == 502
    text = _log_file(settings.data_dir).read_text()
    assert "GET /api/papers/doi:10.1101/x/lookup: bioRxiv lookup failed (503)" in text
    assert "WARNING app.access: GET /api/papers/doi:10.1101/x/lookup 502" in text


def test_job_polling_not_in_access_log(client, settings):
    client.get("/api/jobs")
    client.get("/api/jobs/999")
    client.post("/api/jobs/999/cancel")
    text = _log_file(settings.data_dir).read_text()
    assert "GET /api/jobs" not in text
    assert "POST /api/jobs/999/cancel" in text


def test_cli_failure_logged_with_redacted_args(settings, tmp_path):
    logs.setup(settings.data_dir, "debug")
    script = tmp_path / "fail.sh"
    script.write_text('#!/bin/sh\necho \'{"error": "boom"}\' >&2\nexit 1\n')
    script.chmod(0o755)
    with pytest.raises(CLIError):
        cli = LinxivCLI(str(script))
        asyncio.run(cli(["settings", "update", "--", "OPENAI_API_KEY", "sk-x"], 5))
    text = _log_file(settings.data_dir).read_text()
    assert "linxiv settings update -- OPENAI_API_KEY *** -> 502" in text
    assert "sk-x" not in text
    logs.set_level("info")
