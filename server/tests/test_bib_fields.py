"""BibTeX fields and metadata source: read from the sources, stored on save,
returned with the paper, written in exports, kept in step with the CLI."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from app import bib_store, bibtex
from app.routes import metadata

from .conftest import fixture

SID = "doi:10.1038/nature14539"
BODY = {
    "title": "Deep learning",
    "authors": ["Yann LeCun"],
    "published": "2015-05-27",
    "summary": "",
    "category": "Nature",
    "doi": "10.1038/nature14539",
    "url": "",
    "tags": [],
}


@dataclass
class Lib:
    data_dir: Path


def _stored(settings, sid):
    return asyncio.run(bib_store.get(Lib(settings.data_dir), sid))


def _api(monkeypatch, by_url: dict):
    seen = []

    async def get_json(url, params=None):
        seen.append((url, params))
        return by_url.get(url)

    monkeypatch.setattr(metadata, "_get_json", get_json)
    return seen


# -- reading the fields from each source --------------------------------------


def test_crossref_fields():
    got = metadata.crossref_fields(fixture("crossref-work.json")["message"])
    assert got == {
        "entry_type": "inproceedings",
        "booktitle": "Proceedings of the 25th ACM SIGKDD",
        "editor": "Ann Editor and Committee",
        "pages": "2623--2631",
        "month": "jul",
        "publisher": "ACM",
        "address": "New York, NY, USA",
        "isbn": "9781450362016",
    }
    article = {
        "type": "journal-article",
        "volume": "521",
        "issue": "7553",
        "ISSN": ["0028-0836", "1476-4687"],
        "published-print": {"date-parts": [[2015, 5]]},
    }
    assert metadata.crossref_fields(article) == {
        "entry_type": "article",
        "volume": "521",
        "number": "7553",
        "month": "may",
        "issn": "0028-0836",
    }
    thesis = {"type": "dissertation", "institution": [{"name": "MIT"}]}
    assert metadata.crossref_fields(thesis) == {"entry_type": "phdthesis", "school": "MIT"}
    report = {"type": "report", "publisher": "NASA"}
    assert metadata.crossref_fields(report)["institution"] == "NASA"
    book = {"type": "book", "container-title": ["Lecture Notes"], "edition-number": "2"}
    assert metadata.crossref_fields(book) == {
        "entry_type": "book",
        "series": "Lecture Notes",
        "edition": "2",
    }
    assert metadata.crossref_fields({"type": "something-new"}) == {"entry_type": "misc"}
    assert metadata.crossref_fields(None) == {}


def test_crossref_bib_sends_mailto(monkeypatch):
    url = f"{metadata.CROSSREF}/works/10.1145/3292500.3330701"
    seen = _api(monkeypatch, {url: fixture("crossref-work.json")})
    got = asyncio.run(metadata.crossref_bib("https://doi.org/10.1145/3292500.3330701", "a@b.c"))
    assert got["entry_type"] == "inproceedings"
    assert seen == [(url, {"mailto": "a@b.c"})]
    assert asyncio.run(metadata.crossref_bib(None)) is None
    assert asyncio.run(metadata.crossref_bib("10.1/none")) is None


def test_openalex_work_and_fields(monkeypatch):
    url = f"{metadata.OPENALEX}/works/W3177828909"
    seen = _api(monkeypatch, {url: fixture("openalex-work.json")})
    got = asyncio.run(metadata.openalex_work("openalex:W3177828909", "a@b.c"))
    assert seen == [(url, {"mailto": "a@b.c"})]
    assert got["ref"] == "openalex:W3177828909"
    assert got["authors"] == ["John Jumper", "Richard Evans"]
    assert got["summary"] == "Proteins are essential"
    assert (got["category"], got["doi"]) == ("Nature", "10.1038/s41586-021-03819-2")
    assert got["bib"] == {
        "entry_type": "article",
        "volume": "596",
        "number": "7873",
        "pages": "583--589",
        "month": "jul",
        "publisher": "Nature Portfolio",
        "issn": "0028-0836",
    }
    assert asyncio.run(metadata.openalex_work("not an id")) is None
    assert asyncio.run(metadata.openalex_work("W1")) is None  # API has nothing
    conf = {
        "type": "article",
        "biblio": {"first_page": "7", "last_page": "7"},
        "primary_location": {"source": {"type": "conference", "display_name": "NeurIPS"}},
    }
    assert metadata.openalex_fields(conf) == {
        "entry_type": "inproceedings",
        "booktitle": "NeurIPS",
        "pages": "7",
    }
    assert metadata.openalex_fields(None) == {}
    assert metadata._openalex_abstract(None) is None


def test_arxiv_bib_from_search_and_ids():
    assert metadata.arxiv_bib("arxiv:1706.03762v7", "cs.CL", "2017-06-12") == {
        "entry_type": "misc",
        "month": "jun",
        "eprint": "1706.03762",
        "archive_prefix": "arXiv",
        "primary_class": "cs.CL",
    }
    got = metadata.arxiv_bib("https://arxiv.org/abs/hep-th/9901001v2", None, "1999")
    assert got == {"entry_type": "misc", "eprint": "hep-th/9901001", "archive_prefix": "arXiv"}


def test_lookup_arxiv_and_biorxiv_candidates_carry_bib(client, fake, monkeypatch):
    fake.on("paper", "get", result={"source_id": "arxiv:2204.12985", "title": "Q"})
    fake.on("search", result=fixture("search-arxiv-id.json"))
    r = client.get("/api/papers/arxiv:2204.12985/lookup", params={"source": "arxiv"}).json()
    bib = r["candidates"][0]["bib"]
    assert (bib["eprint"], bib["archive_prefix"], bib["primary_class"]) == (
        "2204.12985",
        "arXiv",
        "quant-ph",
    )


def test_get_json_handles_failures(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/ok":
            return httpx.Response(200, json={"a": 1})
        if req.url.path == "/list":
            return httpx.Response(200, json=[1])
        if req.url.path == "/text":
            return httpx.Response(200, content=b"nope")
        if req.url.path == "/down":
            raise httpx.ConnectError("down")
        return httpx.Response(404)

    monkeypatch.undo()  # drop the conftest stub: this tests the real function
    monkeypatch.setattr(
        metadata, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    get = metadata._get_json
    assert asyncio.run(get("https://x.test/ok")) == {"a": 1}
    for path in ("list", "text", "down", "missing"):
        assert asyncio.run(get(f"https://x.test/{path}")) is None


def test_mailto_prefers_env(monkeypatch):
    monkeypatch.delenv("CROSSREF_MAILTO", raising=False)
    assert metadata.mailto_from({"CROSSREF_MAILTO": " me@x.org "}, "CROSSREF_MAILTO") == "me@x.org"
    monkeypatch.setenv("CROSSREF_MAILTO", "env@x.org")
    assert metadata.mailto_from({}, "CROSSREF_MAILTO") == "env@x.org"


# -- saving, reading back, exporting --------------------------------------------


def test_save_stores_bib_and_source(client, fake, settings):
    fake.on("paper", "repair", result={"source_id": SID})
    fake.on("paper", "get", result={"source_id": SID, "title": "Deep learning"})
    body = {
        **BODY,
        "bib": {"volume": "521", "pages": "436--444", "month": "5"},
        "metadata_source": {"source": "pubmed", "ref": "pubmed:26017442"},
    }
    assert client.put(f"/api/papers/{SID}/metadata", json=body).status_code == 200
    got = client.get(f"/api/papers/{SID}").json()
    assert got["bib"] == {"volume": "521", "pages": "436--444", "month": "may"}
    assert got["metadata_source"] == {"source": "pubmed", "ref": "pubmed:26017442"}
    # a hand edit (no source) keeps the source; a null clears a field
    body = {**BODY, "bib": {"volume": None, "number": "7553"}}
    assert client.put(f"/api/papers/{SID}/metadata", json=body).status_code == 200
    got = _stored(settings, SID)
    assert got["bib"] == {"number": "7553", "pages": "436--444", "month": "may"}
    assert got["metadata_source"]["source"] == "pubmed"
    # neither bib nor source: the store is left alone
    assert client.put(f"/api/papers/{SID}/metadata", json=BODY).status_code == 200
    assert _stored(settings, SID)["bib"]["number"] == "7553"


def test_save_fetches_fields_for_search_candidates(client, fake, settings, monkeypatch):
    fake.on("paper", "repair", result={"source_id": SID})
    fake.on("settings", "get", result={})
    crossref = f"{metadata.CROSSREF}/works/10.1038/nature14539"
    openalex = f"{metadata.OPENALEX}/works/W3177828909"
    _api(monkeypatch, {crossref: {"message": {"type": "journal-article", "volume": "521"}}})
    body = {**BODY, "metadata_source": {"source": "crossref", "ref": "doi:10.1038/nature14539"}}
    assert client.put(f"/api/papers/{SID}/metadata", json=body).status_code == 200
    assert _stored(settings, SID)["bib"] == {"entry_type": "article", "volume": "521"}
    _api(monkeypatch, {openalex: fixture("openalex-work.json")})
    body = {**BODY, "metadata_source": {"source": "openalex", "ref": "openalex:W3177828909"}}
    assert client.put(f"/api/papers/{SID}/metadata", json=body).status_code == 200
    assert _stored(settings, SID)["bib"]["volume"] == "596"
    arxiv = "arxiv:1706.03762"
    body = {**BODY, "category": "cs.CL", "metadata_source": {"source": "arxiv", "ref": arxiv}}
    assert client.put(f"/api/papers/{arxiv}/metadata", json=body).status_code == 200
    assert _stored(settings, arxiv)["bib"]["eprint"] == "1706.03762"


def test_save_bib_fill_only_keeps_stored_fields(client, fake, settings, monkeypatch):
    """Batch edit, candidate with no fields read yet: only null fields are filled,
    the saved record's source is still recorded."""
    fake.on("paper", "repair", result={"source_id": SID})
    fake.on("settings", "get", result={})
    asyncio.run(bib_store.upsert(Lib(settings.data_dir), SID, {"volume": "9"}, "pubmed", "x"))
    crossref = f"{metadata.CROSSREF}/works/10.1038/nature14539"
    _api(monkeypatch, {crossref: {"message": {"type": "journal-article", "volume": "521"}}})
    body = {
        **BODY,
        "bib_fill_only": True,
        "metadata_source": {"source": "crossref", "ref": "doi:10.1038/nature14539"},
    }
    assert client.put(f"/api/papers/{SID}/metadata", json=body).status_code == 200
    got = _stored(settings, SID)
    assert got["bib"] == {"entry_type": "article", "volume": "9"}
    assert got["metadata_source"] == {"source": "crossref", "ref": "doi:10.1038/nature14539"}


@pytest.mark.parametrize(
    "bad",
    [
        {"bib": {"journal": "x"}},
        {"bib": {"volume": "a\x01"}},
        {"bib": {"note": "x" * (bib_store.MAX_VALUE + 1)}},
        {"metadata_source": {"source": "nowhere", "ref": None}},
    ],
)
def test_save_rejects_bad_bib(client, fake, bad):
    assert client.put(f"/api/papers/{SID}/metadata", json={**BODY, **bad}).status_code == 422


def test_export_writes_stored_fields(client, fake, settings):
    asyncio.run(
        bib_store.upsert(
            Lib(settings.data_dir),
            "a",
            {"entry_type": "inproceedings", "booktitle": "Proc", "pages": "1--2", "month": "jul"},
        )
    )
    paper = {"source_id": "a", "title": "Alpha", "authors": ["A B"], "published": "2019-07-01"}
    fake.on("list", result=[{**paper, "category": "ACM"}])
    out = client.post("/api/export/bibtex", json={"ids": ["a"]}).text
    assert out.startswith("@inproceedings{b2019alpha,")
    assert "  booktitle = {Proc}" in out and "journal" not in out
    assert "  month = jul,\n" in out or "  month = jul\n" in out
    assert "  pages = {1--2}" in out


def test_entry_bib_options():
    paper = {"source_id": "doi:10.1/x", "title": "T", "category": "Venue"}
    out = bibtex.entry(paper, "k", {"entry_type": "incollection"})
    assert out.startswith("@incollection{k,") and "  booktitle = {Venue}" in out
    arxiv = {"source_id": "arxiv:1706.03762", "title": "T", "category": "cs.CL"}
    out = bibtex.entry(arxiv, "k", {"eprint": "other", "archive_prefix": "arXiv", "note": "A&B"})
    assert out.count("eprint") == 1 and "eprint = {1706.03762}" in out
    assert "  note = {A\\&B}" in out


# -- add, import, merge, delete, backup ------------------------------------------


def test_add_records_source(client, fake, settings, monkeypatch):
    fake.on("doi", "save", result={"saved": True, "metadata": {"source_id": SID}})
    fake.on("paper", "get", result={"source_id": SID, "doi": "10.1038/nature14539"})
    fake.on("settings", "get", result={})
    crossref = f"{metadata.CROSSREF}/works/10.1038/nature14539"
    _api(monkeypatch, {crossref: {"message": {"type": "journal-article", "volume": "521"}}})
    client.post("/api/add", json={"input": "10.1038/nature14539"})
    got = _stored(settings, SID)
    assert got["bib"]["volume"] == "521"
    assert got["metadata_source"] == {"source": "crossref", "ref": "doi:10.1038/nature14539"}
    fake.on("fetch", result="# Attention (arXiv prints a Markdown summary)")
    fake.on(
        "paper",
        "get",
        result={"source_id": "arxiv:1706.03762", "category": "cs.CL", "published": "2017-06-12"},
    )
    client.post("/api/add", json={"input": "1706.03762"})
    got = _stored(settings, "arxiv:1706.03762")
    assert got["metadata_source"]["source"] == "arxiv"
    assert got["bib"]["eprint"] == "1706.03762"


def test_bibtex_import_stores_entry_fields(client, fake, settings):
    bib = b"""@article{a, title={Deep Learning}, doi={10.1038/nature14539}, volume={521}}
@misc{b, eprint={1706.03762v7}, archivePrefix={arXiv}, title={Attention}, note={NeurIPS}}
@book{c, title={A Local Book}, publisher={Pub}, address={City}}
"""
    sids = [SID, "arxiv:1706.03762", "local:book", "local:none"]
    fake.on("bibtex", "import", result={"saved_count": 4, "source_ids": sids})
    fake.on(
        "list",
        result=[
            {"source_id": "local:book", "title": "A local book"},
            {"source_id": "local:none", "title": "Something else"},
        ],
    )
    r = client.post("/api/import/bibtex", files={"file": ("refs.bib", bib)})
    assert r.status_code == 200, r.text
    assert _stored(settings, SID)["bib"] == {"entry_type": "article", "volume": "521"}
    assert _stored(settings, SID)["metadata_source"]["source"] == "bibtex"
    assert _stored(settings, "arxiv:1706.03762")["bib"]["note"] == "NeurIPS"
    assert _stored(settings, "local:book")["bib"]["address"] == "City"
    assert _stored(settings, "local:none")["bib"] == {}


def test_hard_delete_drops_row(client, fake, settings):
    lib = Lib(settings.data_dir)
    asyncio.run(bib_store.upsert(lib, "local:t", {"volume": "1"}))
    fake.on("trash", "list", result={"papers": [{"source_id": "local:t"}]})
    fake.on("trash", "hard-delete", result={"ok": True})
    assert client.delete("/api/trash/papers/local:t").status_code == 200
    assert _stored(settings, "local:t")["bib"] == {}


def test_backup_copies_bib_file(settings, fake):
    from fastapi.testclient import TestClient

    from app.main import create_app

    asyncio.run(bib_store.upsert(Lib(settings.data_dir), "a", {"volume": "1"}))
    stored: dict = {}
    fake.on("settings", "get", result=lambda _: stored)

    def backup(argv):
        Path(argv[-1]).write_bytes(b"db")
        return {"path": argv[-1]}

    fake.on("backup", result=backup)
    with TestClient(create_app(settings, fake)) as c:
        job = c.post("/api/maintenance/backup/run").json()
        for _ in range(200):
            job = c.get(f"/api/jobs/{job['id']}").json()
            if job["state"] != "running":
                break
    folder = settings.data_dir / "maintenance" / "backups"
    names = sorted(p.name for p in folder.iterdir())
    assert len(names) == 2 and names[0].startswith("bib-") and names[1].startswith("papers-")
    assert names[0].removeprefix("bib-") == names[1].removeprefix("papers-")
