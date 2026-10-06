from __future__ import annotations

import json

import httpx

from app.cli import CLIError
from app.routes import metadata

from .conftest import FIXTURES, fixture

SID = "doi:10.1038/nature14539"
BODY = {
    "title": " Deep learning ",
    "authors": ["Yann LeCun", "-Dash Person"],
    "published": "2015-05-27",
    "summary": "  An abstract\nwith lines ",
    "category": "Nature",
    "doi": "10.1038/nature14539",
    "url": "",
}


def test_save_sends_full_record_and_keeps_tags(client, fake):
    fake.on("paper", "get", result={"source_id": SID, "tags": ["keep", "-x"]})
    fake.on("paper", "repair", result={"source_id": SID, "title": "Deep learning"})
    r = client.put(f"/api/papers/{SID}/metadata", json=BODY)
    assert r.status_code == 200, r.text
    assert fake.calls[-1] == [
        "paper",
        "repair",
        "--title=Deep learning",
        "--authors=Yann LeCun",
        "--authors=-Dash Person",
        "--published=2015-05-27",
        "--summary=An abstract\nwith lines",
        "--category=Nature",
        "--doi=10.1038/nature14539",
        "--tags=keep",
        "--tags=-x",
        "--",
        SID,
    ]


def test_save_validation(client, fake):
    bad = [
        {**BODY, "title": "  "},
        {**BODY, "authors": []},
        {**BODY, "authors": [" "]},
        {**BODY, "authors": ["a\nb"]},
        {**BODY, "published": "2015-5-1"},
        {**BODY, "summary": "x" * 100_001},
        {**BODY, "doi": "a\tb"},
        {**BODY, "extra": 1},
    ]
    fake.on("paper", "get", result={"source_id": SID, "tags": []})
    for body in bad:
        assert client.put(f"/api/papers/{SID}/metadata", json=body).status_code in (400, 422), body
    assert not any(c[:2] == ["paper", "repair"] for c in fake.calls)


def test_save_unknown_paper(client, fake):
    fake.on("paper", "get", result=CLIError(404, "Paper x:y not found"))
    assert client.put("/api/papers/x:y/metadata", json=BODY).status_code == 404


def test_lookup_crossref_by_doi(client, fake):
    fake.on("paper", "get", result={"source_id": SID, "doi": "10.1038/nature14539", "title": "D"})
    fake.on("doi", "resolve", result=fixture("doi-resolve.json"))
    r = client.get(f"/api/papers/{SID}/lookup", params={"source": "crossref"}).json()
    assert r["match"] == "doi"
    [c] = r["candidates"]
    assert (c["title"], c["doi"], c["category"], c["source"]) == (
        "Deep learning",
        "10.1038/nature14539",
        "Nature",
        "crossref",
    )
    assert fake.calls[-1] == ["doi", "resolve", "--", "10.1038/nature14539"]


def test_lookup_title_search(client, fake):
    fake.on("paper", "get", result={"source_id": "local:x", "doi": None, "title": "AlphaFold"})
    fake.on("search", result=fixture("search-crossref.json"))
    r = client.get("/api/papers/local:x/lookup", params={"source": "crossref"}).json()
    assert r["match"] == "title"
    assert r["candidates"][0]["doi"] == "10.1038/s41586-021-03819-2"
    assert fake.calls[-1] == ["search", "--source", "crossref", "--max", "5", "--", "AlphaFold"]


def test_lookup_arxiv_by_id(client, fake):
    fake.on("paper", "get", result={"source_id": "arxiv:2204.12985", "title": "Q"})
    fake.on("search", result=fixture("search-arxiv-id.json"))
    r = client.get("/api/papers/arxiv:2204.12985/lookup", params={"source": "arxiv"}).json()
    assert r["match"] == "arxiv"
    assert r["candidates"][0]["category"] == "quant-ph"
    assert fake.calls[-1][-1] == "id:2204.12985"


def _ncbi(monkeypatch, esearch_ids_by_term: dict, seen: list):
    xml = (FIXTURES / "pubmed-efetch.xml").read_bytes()

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url)
        assert req.url.host == "eutils.ncbi.nlm.nih.gov"
        if req.url.path.endswith("esearch.fcgi"):
            ids = esearch_ids_by_term.get(req.url.params["term"], [])
            return httpx.Response(200, json={"esearchresult": {"idlist": ids}})
        return httpx.Response(200, content=xml)

    monkeypatch.setattr(
        metadata, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


def test_lookup_pubmed_parses_xml(client, fake, monkeypatch):
    seen: list = []
    _ncbi(monkeypatch, {"10.1038/nature14539[doi]": ["26017442", "111"]}, seen)
    fake.on("paper", "get", result={"source_id": SID, "doi": "10.1038/nature14539", "title": "D"})
    r = client.get(f"/api/papers/{SID}/lookup", params={"source": "pubmed"}).json()
    assert r["match"] == "doi"
    a, b = r["candidates"]
    assert a == {
        "source": "pubmed",
        "ref": "pubmed:26017442",
        "title": "Deep learning",
        "authors": ["Yann LeCun", "AI Consortium"],
        "published": "2015-05-28",
        "summary": "BACKGROUND: Layers 2 learn.\n\nRESULTS: It works.",
        "category": "Nature",
        "doi": "10.1038/nature14539",
        "url": "https://pubmed.ncbi.nlm.nih.gov/26017442/",
    }
    assert (b["published"], b["doi"], b["authors"]) == ("2014-11-01", "10.1/abc", ["Solo"])
    assert seen[-1].params["id"] == "26017442,111"


def test_lookup_pubmed_falls_back_to_title(client, fake, monkeypatch):
    seen: list = []
    _ncbi(monkeypatch, {"Deep learning[title]": ["111"]}, seen)
    fake.on("paper", "get", result={"source_id": SID, "doi": "10.9/none", "title": "Deep learning"})
    r = client.get(f"/api/papers/{SID}/lookup", params={"source": "pubmed"}).json()
    assert r["match"] == "title"
    assert len(r["candidates"]) == 2  # fixture holds both articles
    assert [u.params["term"] for u in seen[:2]] == ["10.9/none[doi]", "Deep learning[title]"]


def test_lookup_pubmed_errors(client, fake, monkeypatch):
    def down(req):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(
        metadata, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(down))
    )
    fake.on("paper", "get", result={"source_id": SID, "doi": None, "title": "T"})
    r = client.get(f"/api/papers/{SID}/lookup", params={"source": "pubmed"})
    assert r.status_code == 502
    assert "PubMed" in r.json()["detail"]
    assert client.get(f"/api/papers/{SID}/lookup", params={"source": "x"}).status_code == 422


def test_lookup_route_not_swallowed_by_library(client, fake):
    fake.on("paper", "get", result={"source_id": "a/b", "doi": None, "title": ""})
    r = client.get("/api/papers/arxiv:hep-th/9901001/lookup", params={"source": "openalex"})
    assert r.status_code == 400  # no title: reached the lookup route, not paper get
    assert fake.calls == [["paper", "get", "--", "arxiv:hep-th/9901001"]]
    assert json.loads(r.text)["detail"] == "paper has no title to search by"


def _biorxiv(monkeypatch, replies: dict, seen: list):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url)
        assert req.url.host == "api.biorxiv.org"
        server = req.url.raw_path.decode().split("/")[2]
        body = replies.get(server)
        if isinstance(body, int):
            return httpx.Response(body)
        return httpx.Response(
            200, json=body or {"messages": [{"status": "no posts found"}], "collection": []}
        )

    monkeypatch.setattr(
        metadata, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


def test_lookup_biorxiv_latest_version(client, fake, monkeypatch):
    seen: list = []
    _biorxiv(monkeypatch, {"biorxiv": fixture("biorxiv-details.json")}, seen)
    doi = "10.1101/2020.03.22.002386"
    fake.on("paper", "get", result={"source_id": f"doi:{doi}", "doi": doi, "title": "X"})
    r = client.get(f"/api/papers/doi:{doi}/lookup", params={"source": "biorxiv"}).json()
    assert r["match"] == "doi"
    (c,) = r["candidates"]
    assert c["source"] == "biorxiv"
    assert c["ref"] == f"biorxiv:{doi}v3"
    assert c["published"] == "2020-03-22"  # first version's posting date
    assert c["authors"] == ["D. E. Gordon", "G. M. Jang", "M. Bouhaddou"]
    assert c["url"] == f"https://www.biorxiv.org/content/{doi}v3"
    assert c["category"] == "systems biology" and c["doi"] == doi
    assert [u.raw_path.decode() for u in seen] == [f"/details/biorxiv/{doi}"]


def test_lookup_medrxiv_fallback_and_not_found(client, fake, monkeypatch):
    seen: list = []
    med = fixture("biorxiv-details.json")
    _biorxiv(monkeypatch, {"medrxiv": med}, seen)
    doi = "10.1101/2020.02.11.20021493"
    fake.on("paper", "get", result={"source_id": f"doi:{doi}", "doi": doi, "title": "X"})
    (c,) = client.get(f"/api/papers/doi:{doi}/lookup", params={"source": "biorxiv"}).json()[
        "candidates"
    ]
    assert c["ref"].startswith("medrxiv:") and c["url"].startswith("https://www.medrxiv.org/")
    assert [u.raw_path.decode().split("/")[2] for u in seen] == ["biorxiv", "medrxiv"]

    _biorxiv(monkeypatch, {}, [])
    r = client.get(f"/api/papers/doi:{doi}/lookup", params={"source": "biorxiv"}).json()
    assert r == {"match": "doi", "candidates": []}


def test_lookup_biorxiv_needs_doi_and_encodes_it(client, fake, monkeypatch):
    fake.on("paper", "get", result={"source_id": SID, "doi": None, "title": "T"})
    r = client.get(f"/api/papers/{SID}/lookup", params={"source": "biorxiv"})
    assert r.status_code == 400 and "needs a DOI" in r.json()["detail"]

    seen: list = []
    _biorxiv(monkeypatch, {}, seen)
    fake.on("paper", "get", result={"source_id": SID, "doi": "10.1101/a?b#c", "title": "T"})
    client.get(f"/api/papers/{SID}/lookup", params={"source": "biorxiv"})
    assert seen and all(u.host == "api.biorxiv.org" for u in seen)
    assert seen[0].raw_path.decode() == "/details/biorxiv/10.1101/a%3Fb%23c"

    seen.clear()
    fake.on("paper", "get", result={"source_id": SID, "doi": "10.1101/../../pub", "title": "T"})
    r = client.get(f"/api/papers/{SID}/lookup", params={"source": "biorxiv"}).json()
    assert r["candidates"] == [] and seen == []


def test_lookup_biorxiv_errors(client, fake, monkeypatch):
    _biorxiv(monkeypatch, {"biorxiv": 503}, [])
    fake.on("paper", "get", result={"source_id": SID, "doi": "10.1101/x", "title": "T"})
    r = client.get(f"/api/papers/{SID}/lookup", params={"source": "biorxiv"})
    assert r.status_code == 502 and "bioRxiv" in r.json()["detail"]
