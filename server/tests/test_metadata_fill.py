from __future__ import annotations

import asyncio
import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app import metadata_fill
from app.main import create_app
from app.metadata_fill import completed, gaps

from .conftest import fixture

NEW = "doi:10.1038/nature14539"
PAPERS = [
    {
        "source_id": NEW,
        "title": "Deep learning of things",
        "authors": ["Unknown"],
        "published": "2015-05-27",
        "summary": "",
        "category": None,
        "doi": "10.1038/nature14539",
        "url": None,
        "tags": ["keep"],
    },
    {
        "source_id": "local:x",
        "title": "scan0001",
        "authors": [],
        "published": "2020-01-01",
        "summary": "",
        "category": None,
        "doi": None,
        "url": None,
        "tags": [],
    },
    {
        "source_id": "doi:10.1/old",
        "title": "An old paper with gaps",
        "authors": [],
        "published": None,
        "summary": "",
        "doi": "10.1/old",
        "tags": [],
    },
]


def _library(data, rows):
    db = sqlite3.connect(data / "papers.db")
    db.execute(
        "CREATE TABLE PAPER_ROOTS (SOURCE_FK INTEGER PRIMARY KEY, SOURCE_ID TEXT, "
        "DELETED_AT TIMESTAMP, CREATED_AT TIMESTAMP)"
    )
    for sid, created in rows:
        db.execute(
            "INSERT INTO PAPER_ROOTS (SOURCE_ID, CREATED_AT) VALUES (?, coalesce(?, datetime('now')))",
            (sid, created),
        )
    db.commit()
    db.close()


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(metadata_fill, "PACE_SECONDS", 0.0)


def _setup(settings, fake, stored=None):
    stored = stored if stored is not None else {}

    def update(argv):
        stored[argv[-2]] = json.loads(argv[-1])
        return {}

    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=update)
    fake.on("list", result=PAPERS)
    fake.on("doi", "resolve", result=fixture("doi-resolve.json"))
    fake.on("paper", "repair", result={})
    _library(
        settings.data_dir,
        [(NEW, None), ("local:x", None), ("doi:10.1/old", "2020-01-01 00:00:00")],
    )


def _run(c: TestClient) -> dict:
    job = c.post("/api/maintenance/complete-metadata/run").json()
    for _ in range(200):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_gaps():
    assert gaps(PAPERS[0], []) == ["authors", "abstract", "journal"]
    assert gaps(PAPERS[1], []) == ["title", "authors", "abstract", "journal", "doi"]
    arxiv = {**fixture("list.json")[0]}
    assert gaps(arxiv, []) == []  # arXiv: no journal or DOI expected


def test_completed_fills_only_empty_fields():
    found = {
        "title": "Other title",
        "authors": ["Yann LeCun"],
        "published": "2015-05-28",
        "summary": "An abstract",
        "category": "Nature",
        "doi": "10.1038/nature14539",
        "url": "https://doi.org/10.1038/nature14539",
    }
    got = completed(PAPERS[0], found, ["authors", "abstract", "journal"])
    assert got is not None
    assert got.title == "Deep learning of things"  # stored, kept
    assert got.published == "2015-05-27"
    assert (got.authors, got.summary, got.category) == (["Yann LeCun"], "An abstract", "Nature")
    assert got.url == "https://doi.org/10.1038/nature14539"
    assert completed(PAPERS[0], {"title": "x"}, ["abstract"]) is None  # nothing to fill


def test_run_completes_by_doi_and_lists_the_rest(settings, fake, fast):
    _setup(settings, fake)
    with TestClient(create_app(settings, fake)) as c:
        job = _run(c)
        assert job["state"] == "done", job
        assert job["result"] == {"new_papers": 2, "completed": 1, "to_review": 1}
        [repair] = [a for a in fake.calls if a[:2] == ["paper", "repair"]]
        assert repair[-2:] == ["--", NEW]
        assert "--title=Deep learning of things" in repair
        assert "--authors=Yann LeCun" in repair
        assert "--tags=keep" in repair
        # the old paper was never looked up
        assert not any("10.1/old" in a for call in fake.calls for a in call)

        got = c.get("/api/metadata-review").json()
        assert got["papers"] == [
            {
                "source_id": "local:x",
                "title": "scan0001",
                "missing": ["title", "authors", "abstract", "journal", "doi"],
            }
        ]
        # second run: nothing added since, no list call at all
        n = len(fake.calls)
        assert _run(c)["result"] == {"new_papers": 0, "completed": 0, "to_review": 0}
        assert not any(call == ["list"] for call in fake.calls[n:])

        assert c.post("/api/metadata-review/remove", json={"source_ids": ["local:x"]}).json() == {
            "ok": True
        }
        assert c.get("/api/metadata-review").json()["papers"] == []


def test_options_default_and_validation(settings, fake):
    _setup(settings, fake)
    with TestClient(create_app(settings, fake)) as c:
        got = c.get("/api/maintenance/complete-metadata/options").json()
        assert got["gaps"] == ["title", "authors", "date", "abstract", "journal", "doi"]
        assert got["sources"] == ["arxiv", "biorxiv", "crossref", "pubmed"]
        assert got["all_sources"] == ["arxiv", "biorxiv", "crossref", "pubmed"]
        url = "/api/maintenance/complete-metadata/options"
        assert c.put(url, json={"gaps": ["nope"], "sources": ["crossref"]}).status_code == 400
        assert c.put(url, json={"gaps": ["doi"], "sources": ["openalex"]}).status_code == 400
        assert c.put(url, json={"gaps": ["doi", "doi"], "sources": ["crossref"]}).status_code == 400
        assert c.put(url, json={"gaps": [], "sources": ["crossref"]}).status_code == 422
        r = c.put(url, json={"gaps": ["doi", "title"], "sources": ["pubmed", "crossref"]})
        assert r.status_code == 200, r.text
        # gaps come back in their fixed order, sources in the chosen one
        assert (r.json()["gaps"], r.json()["sources"]) == (["title", "doi"], ["pubmed", "crossref"])


def test_ticked_gaps_and_sources_drive_the_run(settings, fake, fast):
    _setup(settings, fake)
    with TestClient(create_app(settings, fake)) as c:
        body = {"gaps": ["title", "doi"], "sources": ["arxiv"]}
        assert c.put("/api/maintenance/complete-metadata/options", json=body).status_code == 200
        job = _run(c)
        # NEW misses authors, abstract and journal only: not counted now
        assert job["result"] == {"new_papers": 2, "completed": 0, "to_review": 1}
        # arXiv applies to arXiv papers only: no DOI source was asked
        assert not any(a[:2] in (["doi", "resolve"], ["paper", "repair"]) for a in fake.calls)
        [entry] = c.get("/api/metadata-review").json()["papers"]
    assert (entry["source_id"], entry["missing"]) == ("local:x", ["title", "doi"])


def test_match_by_id_follows_the_source_order(monkeypatch):
    from app.routes import metadata

    asked = []

    async def pubmed(term, key=""):
        asked.append("pubmed")
        return []

    async def crossref(call, doi):
        asked.append("crossref")
        return [{"doi": doi.upper(), "title": "Found"}]

    async def biorxiv(doi):
        asked.append("biorxiv")
        return []

    monkeypatch.setattr(metadata, "_pubmed", pubmed)
    monkeypatch.setattr(metadata, "_crossref_doi", crossref)
    monkeypatch.setattr(metadata, "_biorxiv", biorxiv)
    paper = {"source_id": "doi:10.1/x", "doi": "10.1/x"}
    hit = asyncio.run(metadata.match_by_id(None, paper, ["biorxiv", "pubmed", "crossref", "arxiv"]))
    assert hit == {"doi": "10.1/X", "title": "Found"}
    assert asked == ["pubmed", "crossref"]  # bioRxiv skipped: not a bioRxiv DOI
    asked.clear()
    assert asyncio.run(metadata.match_by_id(None, paper, ["arxiv"])) is None
    assert asked == []
