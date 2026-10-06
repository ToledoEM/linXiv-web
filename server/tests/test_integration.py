"""Real linxiv binary, no network: run with LINXIV_BIN set (the Docker test target does)."""

from __future__ import annotations

import json
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


def test_real_cli_author_edit_merge(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = (
        b"@misc{am1, title={One}, author={Doe, Jane and Roe, Rich}, year={2021}}\n"
        b"@misc{am2, title={Two}, author={Doe, Jane}, year={2022}}\n"
    )
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    ids = {a["full_name"]: a["author_id"] for a in c.get("/api/authors").json()}
    jane, rich = ids["Jane Doe"], ids["Rich Roe"]
    assert len(c.get(f"/api/authors/{jane}").json()["papers"]) == 2

    orcid = {"orcid": "0000-0002-1825-0097"}
    assert c.patch(f"/api/authors/{jane}", json={**orcid, "first_name": "Jane"}).status_code == 200
    assert c.patch(f"/api/authors/{rich}", json=orcid).status_code == 200
    got = c.get(f"/api/authors/{jane}").json()
    assert (got["orcid"], got["first_name"]) == ("0000-0002-1825-0097", "Jane")
    found = c.get(f"/api/authors/{jane}/merge-candidates").json()
    assert [a["author_id"] for a in found["candidates"]] == [rich]
    assert found["name_candidates"] == []

    assert c.delete(f"/api/authors/{jane}").status_code == 409
    merged = c.post(f"/api/authors/{jane}/merge", json={"duplicate_ids": [rich, 99999]}).json()
    assert merged["merged_ids"] == [rich]
    assert c.get(f"/api/authors/{rich}").status_code == 404
    assert c.get("/api/authors/99999/merge-candidates").status_code == 404


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


def test_real_cli_notes(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = b"@misc{nt1, title={Noted}, author={Doe, Jane}, year={2021}}\n"
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    pid = c.post("/api/projects", json={"name": "N"}).json()["id"]
    r = c.post("/api/notes", json={"source_id": "local:nt1", "title": "-T", "content": "-a\nb"})
    assert r.status_code == 200, r.text
    nid = r.json()["id"]
    r = c.post("/api/notes", json={"source_id": "local:nt1", "content": "p", "project_id": pid})
    assert r.json()["project_id"] == pid
    notes = c.get("/api/notes", params={"paper": "local:nt1"}).json()
    assert [(n["title"], n["content"]) for n in notes] == [("-T", "-a\nb"), ("", "p")]
    assert [n["content"] for n in c.get("/api/notes", params={"project": pid}).json()] == ["p"]
    r = c.patch(f"/api/notes/{nid}", json={"content": "new"})
    assert (r.json()["title"], r.json()["content"]) == ("-T", "new")
    assert c.delete(f"/api/notes/{nid}").status_code == 200
    assert c.delete(f"/api/notes/{nid}").status_code == 404
    bad = c.post("/api/notes", json={"source_id": "x:y", "content": "z"})
    assert bad.status_code == 404


def test_real_cli_metadata_repair_keeps_tags(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = b"@misc{rp1, title={Old Title}, author={Doe, Jane}, year={2020}}\n"
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    assert c.post("/api/papers/local:rp1/tags", json={"tags": ["keep"]}).status_code == 200
    body = {
        "title": "New $x$ Title",
        "authors": ["Jane Doe", "-Dash Person"],
        "published": "2021-03-04",
        "summary": "Abs\nline",
        "category": "Journal",
        "doi": "10.1234/rp1",
        "url": "",
    }
    r = c.put("/api/papers/local:rp1/metadata", json=body)
    assert r.status_code == 200, r.text
    p = c.get("/api/papers/local:rp1").json()
    assert p["title"] == "New $x$ Title"
    assert p["authors"] == ["Jane Doe", "-Dash Person"]
    assert p["published"] == "2021-03-04"
    assert (p["summary"], p["category"]) == ("Abs\nline", "Journal")
    assert (p["doi"], p["url"]) == ("10.1234/rp1", None)
    assert p["tags"] == ["keep"]
    bad = c.put("/api/papers/local:rp1/metadata", json={**body, "published": "2021-02-30"})
    assert bad.status_code == 400, bad.text


def test_real_cli_versions_offline(settings):
    """No arXiv papers saved, so nothing is polled or flagged."""
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    assert c.get("/api/versions/new").json() == {"new_versions": []}
    bib = b"@misc{vv1, title={V}, author={Doe, Jane}, year={2021}}\n"
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    r = c.post("/api/versions/local:vv1/ack")
    assert r.json() == {"ok": True, "already_acknowledged": True}
    assert c.post("/api/versions/nope:1/ack").status_code == 404


def test_real_cli_sources_offline(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = b"@misc{src1, title={S}, author={Doe, Jane}, year={2021}}\n"
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    assert c.get("/api/sources/pending").json() == {"pending": 0, "arxiv_papers": 0}
    r = c.post("/api/papers/local:src1/source")
    assert r.status_code == 400, r.text
    assert "arXiv" in r.json()["detail"]


def test_real_cli_orcid_backfill_offline(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = b"@misc{ob1, title={No DOI}, author={Doe, Jane}, year={2021}}\n"
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    r = c.post("/api/orcid/backfill", json={"limit": 5})
    assert r.status_code == 200, r.text
    assert r.json() == {"checked": 0, "updated": [], "errored": 0}
    assert c.post("/api/orcid/backfill", json={"limit": 0}).status_code == 422


def test_real_cli_feed_offline(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    assert c.get("/api/feed").json() == {"configured": False}
    patch = {"home_feed_url": "http://127.0.0.1:9/feed", "rss_cache_retention_days": 7}
    got = c.patch("/api/settings", json=patch).json()["settings"]
    assert (got["home_feed_url"], got["rss_cache_retention_days"]) == ("http://127.0.0.1:9/feed", 7)
    r = c.get("/api/feed")
    assert r.status_code == 502 and "private address" in r.json()["detail"]

    rule = c.post("/api/feed/rules", json={"field": "TITLE", "keywords": "quantum, graph"}).json()
    rules = c.get("/api/feed/rules").json()["rules"]
    assert [(x["rule_id"], x["keywords"], x["action"]) for x in rules] == [
        (rule["rule_id"], "quantum,graph", "DENY")
    ]
    assert c.delete(f"/api/feed/rules/{rule['rule_id']}").json() == {"ok": True}
    assert c.delete(f"/api/feed/rules/{rule['rule_id']}").status_code == 404
    body = {"arxiv_id": "2610.03647", "version": 1, "permanent": True}
    assert c.post("/api/feed/dismiss", json=body).json() == {"ok": True}


def test_real_cli_backup_restore_import(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = b"@misc{bk1, title={Keep Me}, author={Doe, Jane}, year={2021}}\n"
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    r = c.get("/api/backup")
    assert r.status_code == 200, r.text
    snapshot = r.content
    assert snapshot.startswith(b"SQLite format 3\x00")

    # Hard-delete the paper, then restore the snapshot: it comes back.
    sid = "local:bk1"
    assert c.delete(f"/api/papers/{sid}").status_code == 200
    assert c.delete(f"/api/trash/papers/{sid}").status_code == 200
    assert c.get(f"/api/papers/{sid}").status_code == 404
    r = c.post("/api/backup/restore", files={"file": ("b.db", snapshot)})
    assert r.status_code == 200, r.text
    assert c.get(f"/api/papers/{sid}").status_code == 200
    assert (settings.data_dir / "papers.pre-restore").is_file()

    # Hard-delete again; an insert-only import brings it back too.
    assert c.delete(f"/api/papers/{sid}").status_code == 200
    assert c.delete(f"/api/trash/papers/{sid}").status_code == 200
    r = c.post("/api/backup/import", files={"file": ("b.db", snapshot)})
    assert r.status_code == 200, r.text
    assert r.json()["papers"] >= 1
    assert c.get(f"/api/papers/{sid}").status_code == 200

    bad = b"SQLite format 3\x00" + b"\x00" * 200
    assert c.post("/api/backup/restore", files={"file": ("b.db", bad)}).status_code == 400


def test_real_cli_annotations(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = b"@misc{an1, title={Annotated}, author={Doe, Jane}, year={2021}}\n"
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    sid = "local:an1"
    anchor = {
        "v": 1,
        "version": 1,
        "page": 1,
        "color": "#ffd400",
        "quote": "Some text",
        "rects": [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.02}],
    }
    r = c.post("/api/annotations", json={"source_id": sid, "anchor": anchor, "comment": "hi"})
    assert r.status_code == 200, r.text
    ann_id = r.json()["id"]
    assert c.patch(f"/api/annotations/{ann_id}", json={"comment": "edited"}).status_code == 200
    r = c.patch(f"/api/annotations/{ann_id}", json={"color": "#54b9f5", "source_id": sid})
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    listed = c.get("/api/annotations", params={"paper": sid}).json()
    assert [a["id"] for a in listed] == [new_id]
    stored = json.loads(listed[0]["anchor"])
    got = (stored["color"], stored["quote"], listed[0]["comment"])
    assert got == ("#54b9f5", "Some text", "edited")
    assert c.delete(f"/api/annotations/{new_id}").status_code == 200
    assert c.get("/api/annotations", params={"paper": sid}).json() == []


def test_real_cli_graph(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = (
        b"@misc{g1, title={One}, author={Doe, Jane and Roe, Rich}, year={2021}, keywords={ml}}\n"
        b"@misc{g2, title={Two}, author={Doe, Jane}, year={2022}}\n"
    )
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    v = c.get("/api/graph").json()
    assert sorted(p["label"] for p in v["papers"]) == ["One", "Two"]
    authors = {a["label"]: a["paper_count"] for a in v["authors"]}
    assert authors == {"Jane Doe": 2, "Rich Roe": 1}
    assert len([e for e in v["edges"] if e["target"].startswith("author::")]) == 3
    single = c.get("/api/graph", params={"exclude_single_authors": "true"}).json()
    assert [a["label"] for a in single["authors"]] == ["Jane Doe"]


def test_real_cli_library_search_includes_notes(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    bib = (
        b"@misc{ls1, title={Plain Title}, author={Doe, Jane}, year={2021}}\n"
        b"@misc{ls2, title={Abstract Holder}, author={Roe, Rich}, year={2022},"
        b" abstract={We study the wombat population.}}\n"
    )
    assert c.post("/api/import/bibtex", files={"file": ("a.bib", bib)}).status_code == 200
    note = {"source_id": "local:ls1", "title": "reading", "content": "compare with quokka data"}
    assert c.post("/api/notes", json=note).status_code == 200
    hits = c.get("/api/papers", params={"q": "quokka"}).json()
    assert [(p["source_id"], p.get("deep_match")) for p in hits] == [("local:ls1", True)]
    abstract = c.get("/api/papers", params={"q": "wombat"}).json()
    assert [p["source_id"] for p in abstract] == ["local:ls2"]
    assert not abstract[0].get("deep_match")


def test_real_cli_search_history_settings(settings):
    c = TestClient(create_app(replace(settings, linxiv_bin=BIN)))
    got = c.get("/api/settings").json()["settings"]
    assert (got["search_history_enabled"], got["search_history_max"]) == (True, 200)
    body = {"search_history_enabled": False, "search_history_max": 25}
    got = c.patch("/api/settings", json=body).json()["settings"]
    assert (got["search_history_enabled"], got["search_history_max"]) == (False, 25)
