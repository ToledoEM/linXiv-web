"""Real linxiv binary, no network: run with LINXIV_BIN set (the Docker test target does)."""

from __future__ import annotations

import os
import shutil
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

BIN = os.environ.get("LINXIV_BIN")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not BIN or not shutil.which(BIN), reason="LINXIV_BIN not set"),
]


def test_real_cli_roundtrip(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    stats = c.get("/api/stats")
    assert stats.status_code == 200, stats.text
    assert stats.json()["paper_count"] == 0
    assert c.get("/api/papers").json() == []
    assert c.get("/api/pdfs").json() == {"pdfs": []}
    missing = c.get("/api/papers/9999.99999")
    assert missing.status_code == 404
    assert "not found" in missing.json()["detail"]
    assert (settings.data_dir / "papers.db").is_file()


def test_real_cli_settings_roundtrip(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    r = c.patch(
        "/api/settings",
        json={"pdf_save_limit_mb": 2048, "OPENALEX_MAILTO": "me@example.org"},
    )
    assert r.status_code == 200, r.text
    got = c.get("/api/settings").json()["settings"]
    assert got["pdf_save_limit_mb"] == 2048
    assert got["OPENALEX_MAILTO"] == "me@example.org"
    assert (settings.data_dir / "user_settings.json").is_file()
