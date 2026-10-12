from __future__ import annotations

from app.cli import CLIError
from app.routes.pdfs import pdf_url_for

from .conftest import fixture


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_search_builds_argv_with_separator(client, fake):
    fake.on("search", result=fixture("search.json"))
    r = client.get("/api/search", params={"q": "--help", "source": "openalex", "max": 3})
    assert r.status_code == 200
    assert fake.calls[-1] == ["search", "--source", "openalex", "--max", "3", "--", "--help"]


def test_search_rejects_bad_source_and_control_chars(client, fake):
    assert client.get("/api/search", params={"q": "x", "source": "evil"}).status_code == 422
    assert client.get("/api/search", params={"q": "a\x00b"}).status_code == 400
    assert fake.calls == []


def test_list_passes_paging(client, fake):
    fake.on("list", result=fixture("list.json"))
    r = client.get("/api/papers", params={"limit": 5, "category": "cs.CL", "dir": "asc"})
    assert r.json()[0]["source_id"] == "arxiv:1706.03762"
    assert fake.calls[-1] == [
        "list",
        "--sort",
        "published",
        "--limit",
        "5",
        "--offset",
        "0",
        "--category",
        "cs.CL",
        "--dir",
        "asc",
    ]


def test_list_filters_by_text_and_tag(client, fake):
    papers = fixture("list.json")
    papers[0]["tags"] = ["nlp"]
    fake.on("list", result=papers)
    assert len(client.get("/api/papers", params={"q": "vaswani"}).json()) == 1
    assert client.get("/api/papers", params={"q": "diffusion"}).json() == []
    assert len(client.get("/api/papers", params={"tag": "nlp"}).json()) == 1
    assert client.get("/api/papers", params={"tag": "cv"}).json() == []
    assert "--limit" not in fake.calls[-1]


def test_list_filters_untagged(client, fake):
    base = fixture("list.json")[0]
    papers = [
        {**base, "source_id": "arxiv:1", "tags": ["nlp"]},
        {**base, "source_id": "arxiv:2", "tags": []},
        {**base, "source_id": "arxiv:3", "tags": None},
    ]
    fake.on("list", result=papers)
    r = client.get("/api/papers", params={"untagged": "true"})
    assert [p["source_id"] for p in r.json()] == ["arxiv:2", "arxiv:3"]
    assert "--limit" not in fake.calls[-1]
    assert client.get("/api/papers", params={"untagged": "true", "tag": "nlp"}).status_code == 400


def test_tag_counts(client, fake):
    base = fixture("list.json")[0]
    papers = [
        {**base, "source_id": "arxiv:1", "tags": ["nlp", "cv"]},
        {**base, "source_id": "arxiv:2", "tags": ["nlp"]},
        {**base, "source_id": "arxiv:3", "tags": []},
        {**base, "source_id": "arxiv:4", "tags": ["bio"]},
    ]
    fake.on("list", result=papers)
    fake.on("tag", "list-all", result=["bio", "cv", "nlp", "orphan"])
    r = client.get("/api/tags/counts")
    assert r.status_code == 200
    assert r.json() == {
        "tags": [
            {"tag": "nlp", "count": 2},
            {"tag": "bio", "count": 1},
            {"tag": "cv", "count": 1},
            {"tag": "orphan", "count": 0},
        ],
        "untagged": 1,
        "total": 4,
    }
    assert ["list"] in fake.calls


def test_list_filters_by_pdf_and_pages_in_python(client, fake):
    base = fixture("list.json")[0]
    papers = [{**base, "source_id": f"arxiv:{i}", "has_pdf": i % 2 == 0} for i in range(6)]
    fake.on("list", result=papers)
    has = client.get("/api/papers", params={"pdf": "has"}).json()
    assert [p["source_id"] for p in has] == ["arxiv:0", "arxiv:2", "arxiv:4"]
    none = client.get("/api/papers", params={"pdf": "none", "limit": 1, "offset": 1}).json()
    assert [p["source_id"] for p in none] == ["arxiv:3"]
    assert "--limit" not in fake.calls[-1]
    assert client.get("/api/papers", params={"pdf": "maybe"}).status_code == 422


def test_fulltext_uses_paper_search(client, fake):
    fake.on("paper", "search", result=[])
    client.get("/api/papers", params={"q": "softmax", "fulltext": "true"})
    assert fake.calls[-1] == ["paper", "search", "--limit", "50", "--", "softmax"]


def test_get_paper_with_slash_id(client, fake):
    fake.on("paper", "get", result={"source_id": "arxiv:hep-th/9901001"})
    r = client.get("/api/papers/arxiv:hep-th/9901001")
    assert r.status_code == 200
    assert fake.calls[-1] == ["paper", "get", "--", "arxiv:hep-th/9901001"]


def test_cli_not_found_is_404(client, fake):
    fake.on("paper", "get", result=CLIError(404, "Paper x not found"))
    r = client.get("/api/papers/x")
    assert r.status_code == 404
    assert r.json()["detail"] == "Paper x not found"


def test_fetch_arxiv_markdown_then_get(client, fake):
    fake.on("fetch", result="# Attention Is All You Need")
    fake.on("paper", "get", result=fixture("paper-get.json"))
    r = client.post("/api/papers/1706.03762/fetch")
    assert r.json()["title"] == "Attention Is All You Need"
    assert fake.calls == [
        ["fetch", "--source", "arxiv", "--", "1706.03762"],
        ["paper", "get", "--", "1706.03762"],
    ]


def test_fetch_json_source_uses_returned_id(client, fake):
    fake.on("fetch", result='{"source_id": "openalex:W1"}')
    fake.on("paper", "get", result={"source_id": "openalex:W1"})
    client.post("/api/papers/W1/fetch", params={"source": "openalex"})
    assert fake.calls[-1] == ["paper", "get", "--", "openalex:W1"]


def test_delete_paper(client, fake):
    fake.on("paper", "delete", result={"deleted": "arxiv:1706.03762"})
    assert client.delete("/api/papers/arxiv:1706.03762").json()["deleted"] == "arxiv:1706.03762"


def test_versions_route_not_swallowed_by_get(client, fake):
    fake.on("paper", "versions", result={"versions": []})
    client.get("/api/papers/arxiv:1706.03762/versions")
    assert fake.calls[-1] == ["paper", "versions", "--", "arxiv:1706.03762"]


def test_tags(client, fake):
    fake.on("tag", result=fixture("tag-list.json"))
    client.get("/api/papers/arxiv:1706.03762/tags")
    assert fake.calls[-1] == ["tag", "list", "--", "arxiv:1706.03762"]
    client.post("/api/papers/arxiv:1706.03762/tags", json={"tags": ["nlp", "-v"]})
    assert fake.calls[-1] == ["tag", "add", "--", "arxiv:1706.03762", "nlp", "-v"]
    client.delete("/api/papers/arxiv:1706.03762/tags", params=[("tag", "nlp"), ("tag", "x")])
    assert fake.calls[-1] == ["tag", "remove", "--", "arxiv:1706.03762", "nlp", "x"]
    assert client.post("/api/papers/a/tags", json={"tags": []}).status_code == 422


def test_stats_and_pdf_list(client, fake):
    fake.on("stats", result=fixture("stats.json"))
    fake.on("pdf", "list", result=fixture("pdf-list.json"))
    assert client.get("/api/stats").json()["paper_count"] == 1
    assert client.get("/api/pdfs").json()["pdfs"][0]["size_bytes"] == 2215244


def _pdf_rows(n):
    return {
        "pdfs": [
            {"source_id": f"local:p{i}", "title": f"P{i}", "version": 1, "size_bytes": i * 10}
            for i in range(n)
        ]
    }


def test_pdf_list_views(client, fake):
    fake.on("pdf", "list", result=_pdf_rows(30))
    by_size = client.get("/api/pdfs", params={"view": "size", "limit": 10}).json()
    assert [p["size_bytes"] for p in by_size["pdfs"]] == [i * 10 for i in range(29, 19, -1)]
    assert by_size["total"] == 30
    rand = client.get("/api/pdfs", params={"view": "random", "limit": 20}).json()["pdfs"]
    assert len(rand) == 20 and len({p["source_id"] for p in rand}) == 20
    fake.on(
        "list",
        result=[{"source_id": f"local:p{i}", "tags": ["x"] if i % 2 else []} for i in range(30)],
    )
    untagged = client.get("/api/pdfs", params={"view": "untagged"}).json()["pdfs"]
    assert [p["source_id"] for p in untagged] == [f"local:p{i}" for i in range(0, 20, 2)]
    assert len(client.get("/api/pdfs").json()["pdfs"]) == 30


def test_pdf_list_limit_bounds(client, fake):
    fake.on("pdf", "list", result=_pdf_rows(3))
    assert client.get("/api/pdfs", params={"limit": 9}).status_code == 422
    assert client.get("/api/pdfs", params={"limit": 101}).status_code == 422
    assert client.get("/api/pdfs", params={"view": "odd"}).status_code == 422
    assert len(client.get("/api/pdfs", params={"view": "random", "limit": 10}).json()["pdfs"]) == 3


# --- PDFs ---


def test_view_pdf_through_symlinked_dir(client, fake, dirs):
    data, pdfs = dirs
    (pdfs / "arxiv_1706.03762v7.pdf").write_bytes(b"%PDF-1.4 test")
    fake.on("pdf", "path", result={"path": str(data / "pdfs" / "arxiv_1706.03762v7.pdf")})
    r = client.get("/api/papers/arxiv:1706.03762/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.content == b"%PDF-1.4 test"


def test_view_pdf_outside_storage_is_403(client, fake, tmp_path):
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(b"%PDF-")
    fake.on("pdf", "path", result={"path": str(outside)})
    assert client.get("/api/papers/x/pdf").status_code == 403


def test_view_pdf_none_is_404(client, fake):
    fake.on("pdf", "path", result={"path": None})
    assert client.get("/api/papers/x/pdf").status_code == 404


def test_download_derives_arxiv_url(client, fake):
    fake.on("paper", "get", result=fixture("paper-get.json"))
    fake.on("pdf", "download", result={"path": "/data/pdfs/a.pdf"})
    assert client.post("/api/papers/arxiv:1706.03762/pdf").status_code == 200
    assert fake.calls[-1] == [
        "pdf",
        "download",
        "--",
        "arxiv:1706.03762",
        "https://arxiv.org/pdf/1706.03762v7",
    ]


def test_download_rejects_non_http(client, fake):
    r = client.post("/api/papers/x/pdf", json={"url": "file:///etc/passwd"})
    assert r.status_code == 400
    assert fake.calls == []


def test_download_without_known_url_is_400(client, fake):
    fake.on("paper", "get", result={"source": "openalex", "url": "https://openalex.org/W1"})
    assert client.post("/api/papers/W1/pdf").status_code == 400


def test_pdf_url_for():
    assert pdf_url_for({"source": "arxiv", "source_id": "arxiv:2204.12985", "version": 2}) == (
        "https://arxiv.org/pdf/2204.12985v2"
    )
    assert (
        pdf_url_for({"source": "openalex", "url": "https://x.org/a.PDF"}) == "https://x.org/a.PDF"
    )
    assert pdf_url_for({"source": "crossref", "url": "https://doi.org/10.1/x"}) is None


def test_delete_pdf(client, fake):
    fake.on("pdf", "delete", result={"deleted": True})
    client.delete("/api/papers/arxiv:1706.03762/pdf")
    assert fake.calls[-1] == ["pdf", "delete", "--", "arxiv:1706.03762"]


def test_import_pdf_runs_cli_and_removes_tmp(client, fake):
    seen = {}

    def record(args):
        from pathlib import Path

        seen["path"] = Path(args[-1])
        seen["exists"] = seen["path"].is_file()
        return {"source_id": "arxiv:1706.03762", "title": "T"}

    fake.on("pdf", "import", result=record)
    r = client.post(
        "/api/pdfs/import", files={"file": ("p.pdf", b"%PDF-1.4 body", "application/pdf")}
    )
    assert r.status_code == 200
    assert fake.calls[-1][:3] == ["pdf", "import", "--"]
    assert seen["exists"] and not seen["path"].exists()


def test_import_rejects_non_pdf_and_oversize(client, fake):
    r = client.post("/api/pdfs/import", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 400
    big = b"%PDF-" + b"0" * (2 * 1024 * 1024)
    r = client.post("/api/pdfs/import", files={"file": ("x.pdf", big, "application/pdf")})
    assert r.status_code == 413
    assert fake.calls == []


def _lib(fake, deep):
    papers = [
        {
            "source_id": "arxiv:1",
            "title": "Attention",
            "summary": "",
            "tags": ["ml"],
            "has_pdf": True,
        },
        {"source_id": "arxiv:2", "title": "Other", "summary": "uses softmax gating", "tags": []},
        {"source_id": "arxiv:3", "title": "Third", "summary": "", "tags": ["ml"], "has_pdf": False},
        {"source_id": "arxiv:4", "title": "Fourth", "summary": "", "tags": [], "has_pdf": True},
    ]
    fake.on("list", result=papers)
    fake.on("paper", "search", result=deep)


def test_search_merges_fulltext_and_notes(client, fake):
    _lib(fake, [{"source_id": "arxiv:3"}, {"source_id": "arxiv:2"}, {"source_id": "gone:9"}])
    r = client.get("/api/papers", params={"q": "softmax"})
    assert r.status_code == 200, r.text
    rows = [(p["source_id"], p.get("deep_match", False)) for p in r.json()]
    # list order kept; abstract match is a plain match; deep-only hit flagged; unknown id dropped
    assert rows == [("arxiv:2", False), ("arxiv:3", True)]
    assert ["paper", "search", "--limit", "200", "--", "softmax"] in fake.calls


def test_search_deep_hits_respect_filters(client, fake):
    _lib(fake, [{"source_id": "arxiv:3"}, {"source_id": "arxiv:4"}])
    r = client.get("/api/papers", params={"q": "quokka", "tag": "ml", "pdf": "none"})
    assert [p["source_id"] for p in r.json()] == ["arxiv:3"]


def test_short_query_skips_deep_search(client, fake):
    _lib(fake, [{"source_id": "arxiv:4"}])
    r = client.get("/api/papers", params={"q": "tt"})
    assert [p["source_id"] for p in r.json()] == ["arxiv:1"]
    assert not [c for c in fake.calls if c[:2] == ["paper", "search"]]


def test_deep_search_failure_keeps_plain_hits(client, fake):
    _lib(fake, None)
    fake.on("paper", "search", result=CLIError(502, "fts index unavailable"))
    r = client.get("/api/papers", params={"q": "attention"})
    assert r.status_code == 200
    assert [p["source_id"] for p in r.json()] == ["arxiv:1"]
    assert r.headers["X-Deep-Search-Error"] == "fts index unavailable"


def _insitu(settings) -> list[dict]:
    """The in-situ fixture with its /data/pdfs paths moved under the test data dir."""
    papers = fixture("list-insitu.json")
    for p in papers:
        p["pdf_path"] = p["pdf_path"].replace("/data/pdfs", f"{settings.data_dir}/pdfs", 1)
    return papers


def test_list_and_get_add_pdf_file_and_title_flag(client, fake, settings):
    papers = _insitu(settings)
    papers[0]["title"] = "Abstract"
    papers.append({"source_id": "local:nopdf", "title": "A paper without a PDF", "pdf_path": None})
    fake.on("list", result=papers)
    rows = {p["source_id"]: p for p in client.get("/api/papers").json()}
    genetics = rows["doi:10.1016/j.ajhg.2026.03.011"]
    assert genetics["pdf_file"] == "Mendelay_database/1995/Some_Real_Title_of_a_genetics_paper.pdf"
    assert genetics["title_suspect"] is True  # "Abstract"
    attention = rows["arxiv:1706.03762"]
    assert attention["pdf_file"] == "Mendelay_database/2017/Attention_is_all_you_need.pdf"
    assert attention["title_suspect"] is False
    assert rows["arxiv:2201.01470"]["pdf_file"] == "phd/review1.pdf"
    assert rows["arxiv:2201.01470"]["title_suspect"] is False  # no title in "review1"
    assert (rows["local:nopdf"]["pdf_file"], rows["local:nopdf"]["title_suspect"]) == (None, False)
    # the filtered (paged in Python) branch is annotated too
    hit = client.get("/api/papers", params={"q": "vaswani"}).json()
    assert [p["pdf_file"] for p in hit] == [attention["pdf_file"]]

    paper = fixture("paper-get-insitu.json")
    paper["pdf_path"] = paper["pdf_path"].replace("/data/pdfs", f"{settings.data_dir}/pdfs", 1)
    fake.on("paper", "get", result=paper)
    got = client.get("/api/papers/arxiv:1706.03762").json()
    assert (got["pdf_file"], got["title_suspect"]) == (attention["pdf_file"], False)
