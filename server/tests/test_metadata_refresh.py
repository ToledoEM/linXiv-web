from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import bib_store, metadata_refresh
from app.main import create_app
from app.metadata_refresh import in_scope, is_preprint, options_from, refreshed
from app.routes import metadata

from .conftest import fixture

DOI_SID = "doi:10.1038/nature14539"
TODAY = date(2026, 11, 1)
PAPERS = [
    {
        "source_id": DOI_SID,
        "title": "Deep learning",
        "authors": ["Y. LeCun"],
        "published": "2015-05-27",
        "summary": "old abstract",
        "category": "Nature",
        "doi": "10.1038/nature14539",
        "url": "https://keep.me/x",
        "tags": ["keep"],
    },
    {
        "source_id": "arxiv:2204.12985",
        "title": "Quantum thing",
        "authors": ["A"],
        "published": "2022-04-27",
        "summary": "s",
        "category": "quant-ph",
        "doi": None,
        "url": None,
        "tags": [],
    },
    {
        "source_id": "local:bib",
        "title": "From a bib file",
        "authors": ["B"],
        "published": "2026-01-01",
        "summary": "",
        "category": None,
        "doi": None,
        "url": None,
        "tags": [],
    },
    {
        "source_id": "local:none",
        "title": "No source recorded",
        "authors": ["C"],
        "published": "2026-02-01",
        "tags": [],
    },
]


@dataclass
class Lib:
    data_dir: Path


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(metadata_refresh, "PACE_SECONDS", 0.0)


def _seed(settings):
    lib = Lib(settings.data_dir)

    async def go():
        await bib_store.upsert(lib, DOI_SID, {"volume": "1"}, "crossref", "doi:10.1038/nature14539")
        await bib_store.upsert(lib, "arxiv:2204.12985", {}, "arxiv", "arxiv:2204.12985")
        await bib_store.upsert(lib, "local:bib", {"note": "n"}, "bibtex", "local:bib")
        await bib_store.upsert(lib, "local:gone", {"note": "n"}, "crossref", "doi:10.1/gone")

    asyncio.run(go())
    return lib


def _setup(settings, fake, scope=None):
    stored = {}
    if scope:
        stored["web_maint_refresh"] = json.dumps({"scope": scope})

    def update(argv):
        stored[argv[-2]] = json.loads(argv[-1])
        return {}

    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=update)
    fake.on("list", result=PAPERS)
    fake.on("trash", "list", result={"papers": []})
    fake.on("doi", "resolve", result=fixture("doi-resolve.json"))
    fake.on("search", result=fixture("search-arxiv-id.json"))
    fake.on("paper", "repair", result={})
    return stored


def _run(c: TestClient) -> dict:
    job = c.post("/api/maintenance/metadata-refresh/run").json()
    for _ in range(300):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_scope_and_preprints():
    assert is_preprint({"source_id": "arxiv:1"})
    assert is_preprint({"source_id": "doi:x", "doi": "10.1101/2020.01.01.1"})
    assert is_preprint({"source_id": "doi:x", "category": "medRxiv"})
    assert not is_preprint({"source_id": "doi:x", "doi": "10.1038/x", "category": "Nature"})
    old = {"source_id": "doi:x", "published": "2015-01-01"}
    assert not in_scope(old, "recent_or_preprint", TODAY)
    assert in_scope(old, "all", TODAY)
    assert in_scope({"source_id": "doi:x", "published": "2026-03-01"}, "recent_or_preprint", TODAY)
    assert not in_scope({"source_id": "doi:x", "published": None}, "recent_or_preprint", TODAY)
    assert options_from({}) == {"scope": "recent_or_preprint"}
    assert options_from({"web_maint_refresh": json.dumps({"scope": "all"})}) == {"scope": "all"}
    assert options_from({"web_maint_refresh": json.dumps({"scope": "x"})})["scope"] != "x"


def test_refreshed_rules():
    paper = PAPERS[0]
    assert refreshed(paper, {"source": "crossref", "title": "Deep learning"}) is None
    got = refreshed(
        paper,
        {
            "source": "crossref",
            "title": "Deep Learning",
            "summary": "new abstract",
            "published": "2015-01-01",  # year only: the fuller stored date stays
            "url": "https://doi.org/x",  # the link stays
        },
    )
    assert (got.title, got.summary, got.published, got.url) == (
        "Deep Learning",
        "new abstract",
        "2015-05-27",
        "https://keep.me/x",
    )
    # an arXiv subject code never replaces a journal
    got = refreshed(paper, {"source": "arxiv", "category": "cs.LG", "summary": "new"})
    assert (got.category, got.summary) == ("Nature", "new")
    # a record that would not save
    assert refreshed(paper, {"source": "crossref", "published": "May 2015"}) is None
    # a stored record that would not save: any valid result is a change
    broken = {**paper, "published": None}
    assert refreshed(broken, {"source": "crossref", "published": "2015-05-27"}) is not None


def test_run_refreshes_recorded_sources(settings, fake, fast, monkeypatch):
    _setup(settings, fake, scope="all")
    lib = _seed(settings)
    crossref = f"{metadata.CROSSREF}/works/10.1038/nature14539"

    async def get_json(url, params=None):
        return (
            {"message": {"type": "journal-article", "volume": "521"}} if url == crossref else None
        )

    monkeypatch.setattr(metadata, "_get_json", get_json)
    with TestClient(create_app(settings, fake)) as c:
        job = _run(c)
    assert job["state"] == "done", job
    assert job["result"] == {
        "checked": 2,
        "updated": 2,
        "unchanged": 0,
        "not_found": 0,
        "not_refreshable": 1,
    }
    repairs = [call for call in fake.calls if call[:2] == ["paper", "repair"]]
    assert repairs and repairs[0][-1] == DOI_SID and "--tags=keep" in repairs[0]
    rows = asyncio.run(bib_store.all_rows(lib))
    assert "local:gone" not in rows  # pruned: no longer in the library
    assert rows[DOI_SID]["bib"] == {"entry_type": "article", "volume": "521"}
    assert rows["arxiv:2204.12985"]["bib"]["primary_class"] == "quant-ph"
    assert rows["local:bib"]["metadata_source"]["source"] == "bibtex"


def test_run_scope_and_not_found(settings, fake, fast):
    _setup(settings, fake)  # default scope: recent or preprint
    fake.on("search", result=[])
    _seed(settings)
    with TestClient(create_app(settings, fake)) as c:
        job = _run(c)
    # the 2015 Nature paper is out of scope; the arXiv one is not found
    assert job["result"]["checked"] == 1
    assert job["result"]["not_found"] == 1
    report = json.loads((settings.data_dir / "maintenance" / metadata_refresh.REPORT).read_text())
    assert report["not_found"][0]["source_id"] == "arxiv:2204.12985"


def test_run_openalex_and_errors(settings, fake, fast, monkeypatch):
    _setup(settings, fake, scope="all")
    lib = Lib(settings.data_dir)
    asyncio.run(bib_store.upsert(lib, DOI_SID, {}, "openalex", "openalex:W3177828909"))
    asyncio.run(bib_store.upsert(lib, "arxiv:2204.12985", {}, "arxiv", "arxiv:2204.12985"))
    from app.cli import CLIError

    fake.on("search", result=CLIError(502, "arXiv down"))
    work = fixture("openalex-work.json")

    async def get_json(url, params=None):
        return work if url.endswith("/works/W3177828909") else None

    monkeypatch.setattr(metadata, "_get_json", get_json)
    with TestClient(create_app(settings, fake)) as c:
        job = _run(c)
    assert job["result"]["updated"] == 1
    assert job["errors"][0]["source_id"] == "arxiv:2204.12985"
    assert asyncio.run(bib_store.get(lib, DOI_SID))["bib"]["volume"] == "596"


def test_run_nothing_recorded_skips_cli(settings, fake):
    _setup(settings, fake)
    with TestClient(create_app(settings, fake)) as c:
        job = _run(c)
    assert job["result"]["checked"] == 0
    assert ["list"] not in fake.calls


def test_options_routes(settings, fake):
    stored = _setup(settings, fake)
    with TestClient(create_app(settings, fake)) as c:
        got = c.get("/api/maintenance/metadata-refresh/options").json()
        assert got == {"scope": "recent_or_preprint", "all_scopes": ["all", "recent_or_preprint"]}
        r = c.put("/api/maintenance/metadata-refresh/options", json={"scope": "all"})
        assert r.json()["scope"] == "all"
        assert json.loads(stored["web_maint_refresh"]) == {"scope": "all"}
        bad = c.put("/api/maintenance/metadata-refresh/options", json={"scope": "some"})
        assert bad.status_code == 400


def test_trash_unreadable_skips_prune(settings, fake, fast):
    from app.cli import CLIError

    _setup(settings, fake, scope="all")
    fake.on("trash", "list", result=CLIError(502, "no"))
    lib = _seed(settings)
    with TestClient(create_app(settings, fake)) as c:
        _run(c)
    assert "local:gone" in asyncio.run(bib_store.all_rows(lib))
