from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from app.routes import add
from app.routes.add import classify

from .conftest import fixture


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2204.12985", ("arxiv", "2204.12985")),
        ("arXiv:2204.12985v3", ("arxiv", "2204.12985")),
        ("hep-th/9901001", ("arxiv", "hep-th/9901001")),
        ("https://arxiv.org/abs/1706.03762v7", ("arxiv", "1706.03762")),
        ("https://arxiv.org/pdf/1706.03762v7.pdf", ("arxiv", "1706.03762")),
        ("https://export.arxiv.org/abs/math.AG/0101001", ("arxiv", "math.AG/0101001")),
        ("10.1038/nature14539", ("doi", "10.1038/nature14539")),
        ("doi: 10.1038/nature14539", ("doi", "10.1038/nature14539")),
        ("https://doi.org/10.1038/nature14539", ("doi", "10.1038/nature14539")),
        ("https://dx.doi.org/10.1000/a%2Fb", ("doi", "10.1000/a/b")),
        ("10.48550/arXiv.1706.03762", ("arxiv", "1706.03762")),
        ("https://example.org/paper.pdf", ("pdf", "https://example.org/paper.pdf")),
    ],
)
def test_classify(text, expected):
    assert classify(text) == expected


@pytest.mark.parametrize("text", ["attention is all you need", "ftp://x.org/a.pdf", "10.12/x"])
def test_classify_rejects(text):
    with pytest.raises(HTTPException) as e:
        classify(text)
    assert e.value.status_code == 400


def test_add_arxiv_uses_fetch(client, fake):
    fake.on("fetch", result="# Attention Is All You Need\n")
    fake.on("paper", "get", result=fixture("paper-get.json"))
    r = client.post("/api/add", json={"input": "https://arxiv.org/abs/1706.03762v7"})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "arxiv"
    assert fake.calls[0] == ["fetch", "--source", "arxiv", "--", "1706.03762"]


def test_add_doi_saves_then_gets(client, fake):
    fake.on("doi", "save", result={"saved": True, "metadata": {"source_id": "doi:10.1038/x"}})
    fake.on("paper", "get", result={"source_id": "doi:10.1038/x", "title": "Deep learning"})
    r = client.post("/api/add", json={"input": "https://doi.org/10.1038/x"})
    assert r.json() == {
        "kind": "doi",
        "paper": {"source_id": "doi:10.1038/x", "title": "Deep learning"},
    }
    assert fake.calls == [
        ["doi", "save", "--", "10.1038/x"],
        ["paper", "get", "--", "doi:10.1038/x"],
    ]


def _serve(monkeypatch, handler, addrs=("93.184.215.14",)):
    """Route add.py's HTTP client through `handler` and fake DNS."""

    async def resolve(host):
        return list(addrs) if not callable(addrs) else addrs(host)

    monkeypatch.setattr(add, "_resolve", resolve)
    monkeypatch.setattr(
        add,
        "_client",
        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_add_pdf_link_downloads_and_imports(client, fake, monkeypatch):
    seen = {}

    def handler(req):
        if req.url.path == "/go":
            return httpx.Response(302, headers={"location": "/paper.pdf"})
        return httpx.Response(200, content=b"%PDF-1.7 hello")

    def imp(argv):
        seen["bytes"] = Path(argv[-1]).read_bytes()
        return {"source_id": "local:x", "title": "X"}

    _serve(monkeypatch, handler)
    fake.on("pdf", "import", result=imp)
    r = client.post("/api/add", json={"input": "https://example.org/go"})
    assert r.status_code == 200, r.text
    assert r.json() == {"kind": "pdf", "paper": {"source_id": "local:x", "title": "X"}}
    assert seen["bytes"] == b"%PDF-1.7 hello"


@pytest.mark.parametrize("addr", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"])
def test_add_pdf_link_refuses_private_hosts(client, fake, monkeypatch, addr):
    _serve(monkeypatch, lambda req: httpx.Response(200, content=b"%PDF-"), addrs=(addr,))
    r = client.post("/api/add", json={"input": "https://internal.example/a.pdf"})
    assert r.status_code == 400
    assert "public" in r.json()["detail"]
    assert not fake.calls


def test_add_pdf_redirect_to_private_host_is_refused(client, fake, monkeypatch):
    def handler(req):
        return httpx.Response(302, headers={"location": "http://evil.internal/x.pdf"})

    _serve(
        monkeypatch,
        handler,
        addrs=lambda host: ["10.1.2.3"] if host == "evil.internal" else ["93.184.215.14"],
    )
    r = client.post("/api/add", json={"input": "https://example.org/a.pdf"})
    assert r.status_code == 400
    assert not fake.calls


def test_add_pdf_link_not_pdf_or_too_big(client, fake, monkeypatch):
    _serve(monkeypatch, lambda req: httpx.Response(200, content=b"<html>"))
    assert client.post("/api/add", json={"input": "https://e.org/a"}).status_code == 400
    # conftest caps uploads at 1 MB
    _serve(monkeypatch, lambda req: httpx.Response(200, content=b"%PDF-" + b"0" * (2 << 20)))
    assert client.post("/api/add", json={"input": "https://e.org/a"}).status_code == 413
    _serve(monkeypatch, lambda req: httpx.Response(404))
    assert client.post("/api/add", json={"input": "https://e.org/a"}).status_code == 502
    assert not fake.calls
