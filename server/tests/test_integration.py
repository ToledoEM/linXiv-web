"""Real linxiv binary, no network: run with LINXIV_BIN set (the Docker test target does)."""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
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


def test_real_cli_trash_roundtrip(settings, tmp_path):
    """Offline: a BibTeX entry without DOI/arXiv id imports as a local paper."""
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = tmp_path / "one.bib"
    bib.write_text("@misc{trashme, title={Trash Me}, author={Doe, Jane}, year={2020}}\n")
    env = {**os.environ, "LINXIV_DATA_DIR": str(settings.data_dir)}
    subprocess.run([BIN, "bibtex", "import", str(bib)], env=env, capture_output=True, check=True)
    sid = "local:trashme"
    assert c.delete(f"/api/papers/{sid}").status_code == 200
    assert [p["source_id"] for p in c.get("/api/trash").json()["papers"]] == [sid]
    assert c.post(f"/api/trash/papers/{sid}/restore").status_code == 200
    assert c.get(f"/api/papers/{sid}").status_code == 200
    assert c.delete(f"/api/papers/{sid}").status_code == 200
    r = c.delete(f"/api/trash/papers/{sid}")
    assert r.status_code == 200, r.text
    assert c.get("/api/trash").json()["papers"] == []
    assert c.get(f"/api/papers/{sid}").status_code == 404


def test_real_cli_bibtex_and_zotero_import(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = b"@misc{imp1, title={Imported One}, author={Doe, Jane}, year={2021}}\n"
    r = c.post("/api/import/bibtex", files={"file": ("a.bib", bib)})
    assert r.status_code == 200, r.text
    assert r.json() == {"saved_count": 1, "source_ids": ["local:imp1"]}
    csl = b'[{"id": "z1", "type": "article-journal", "title": "Zotero One"}]'
    r = c.post("/api/import/zotero", files={"file": ("z.json", csl)})
    assert r.status_code == 200, r.text
    assert r.json()["saved_count"] == 1
    assert len(c.get("/api/papers").json()) == 2


def test_real_cli_author_list(settings, tmp_path):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = (
        b"@misc{au1, title={One}, author={Doe, Jane and Roe, Rich}, year={2021}}\n"
        b"@misc{au2, title={Two}, author={Doe, Jane}, year={2022}}\n"
    )
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    authors = {a["full_name"]: a["paper_count"] for a in c.get("/api/authors").json()}
    assert len(authors) == 2 and max(authors.values()) == 2
    multi = c.get("/api/authors", params={"hide_single": "true"}).json()
    assert [a["paper_count"] for a in multi] == [2]


def test_real_cli_projects(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    r = c.post(
        "/api/projects",
        json={"name": "-P", "description": "-d", "color_hex": "#4f86f7", "project_tags": ["A"]},
    )
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    [p] = c.get("/api/projects").json()
    assert (p["name"], p["description"], p["project_tags"]) == ("-P", "-d", ["A"])
    r = c.patch(f"/api/projects/{pid}", json={"name": "Q", "project_tags": []})
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["project_tags"]) == ("Q", [])
    assert c.post(f"/api/projects/{pid}/archive").status_code == 200
    assert c.get("/api/projects").json() == []
    assert [p["id"] for p in c.get("/api/projects?status=archived").json()] == [pid]
    assert c.post(f"/api/projects/{pid}/restore").status_code == 200
    assert c.delete(f"/api/projects/{pid}").status_code == 200
    assert [p["id"] for p in c.get("/api/trash").json()["projects"]] == [pid]
    assert c.post("/api/projects/9999/archive").status_code == 404


def test_real_cli_project_papers(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = (
        b"@misc{pp1, title={One}, author={Doe, Jane}, year={2021}}\n"
        b"@misc{pp2, title={Two}, author={Doe, Jane}, year={2022}}\n"
    )
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    pid = c.post("/api/projects", json={"name": "P"}).json()["id"]
    r = c.post(
        f"/api/projects/{pid}/papers", json={"source_ids": ["local:pp2", "local:pp1", "x:y"]}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["added"], r.json()["failed"]) == (["local:pp2", "local:pp1"], ["x:y"])
    papers = c.get(f"/api/projects/{pid}/papers").json()
    assert [p["source_id"] for p in papers] == ["local:pp2", "local:pp1"]
    assert c.delete(f"/api/projects/{pid}/papers/local:pp2").status_code == 200
    assert c.get(f"/api/projects/{pid}").json()["source_ids"] == ["local:pp1"]
    assert c.get("/api/projects/9999/papers").status_code == 404


def test_real_cli_project_export(settings, tmp_path):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = b"@misc{ex1, title={Export Me}, author={Doe, Jane}, year={2021}}\n"
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    pid = c.post("/api/projects", json={"name": "Ex Port"}).json()["id"]
    c.post(f"/api/projects/{pid}/papers", json={"source_ids": ["local:ex1"]})
    r = c.get(f"/api/projects/{pid}/export", params={"format": "bibtex"})
    assert r.status_code == 200, r.text
    assert "Export Me" in r.text
    assert 'filename="ex_port.bib"' in r.headers["content-disposition"]
    r = c.get(f"/api/projects/{pid}/export", params={"pdfs": "true"})
    assert r.status_code == 200, r.text
    (tmp_path / "p.lxproj").write_bytes(r.content)
    with zipfile.ZipFile(tmp_path / "p.lxproj") as z:
        assert "manifest.json" in z.namelist()
    for fmt in ("obsidian", "zotero"):
        assert c.get(f"/api/projects/{pid}/export", params={"format": fmt}).status_code == 200
