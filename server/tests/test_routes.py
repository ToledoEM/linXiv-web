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
