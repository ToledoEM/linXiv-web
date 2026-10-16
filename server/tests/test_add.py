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
        ("10.1038/nature14539;", ("doi", "10.1038/nature14539")),
        ("https://doi.org/10.1038/nature14539;", ("doi", "10.1038/nature14539")),
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


def test_add_pdf_link_connects_to_checked_address(client, fake, monkeypatch):
    seen = []

    def handler(req):
        seen.append((str(req.url), req.headers["host"], req.extensions.get("sni_hostname")))
        if req.url.path == "/go":
            return httpx.Response(302, headers={"location": "https://cdn.example.net/p.pdf"})
        return httpx.Response(200, content=b"%PDF-1.7")

    dns = {"example.org": ["93.184.215.14"], "cdn.example.net": ["2606:2800:21f:cb07::1"]}
    _serve(monkeypatch, handler, addrs=lambda host: dns[host])
    fake.on("pdf", "import", result={"source_id": "local:x"})
    r = client.post("/api/add", json={"input": "https://u:p@example.org:8443/go?x=1"})
    assert r.status_code == 200, r.text
    assert seen == [
        ("https://93.184.215.14:8443/go?x=1", "example.org:8443", "example.org"),
        ("https://[2606:2800:21f:cb07::1]/p.pdf", "cdn.example.net", "cdn.example.net"),
    ]


def test_add_pdf_link_resolves_once_per_hop(client, fake, monkeypatch):
    """A rebinding DNS answer after the check is never used."""
    answers = iter([["93.184.215.14"], ["127.0.0.1"]])
    hosts = []

    def handler(req):
        hosts.append(req.url.host)
        return httpx.Response(200, content=b"%PDF-1.7")

    _serve(monkeypatch, handler, addrs=lambda host: next(answers))
    fake.on("pdf", "import", result={"source_id": "local:x"})
    r = client.post("/api/add", json={"input": "https://rebind.example/a.pdf"})
    assert r.status_code == 200, r.text
    assert hosts == ["93.184.215.14"]


def test_add_pdf_link_not_pdf_or_too_big(client, fake, monkeypatch):
    _serve(monkeypatch, lambda req: httpx.Response(200, content=b"<html>"))
    assert client.post("/api/add", json={"input": "https://e.org/a"}).status_code == 400
    # conftest caps uploads at 1 MB
    _serve(monkeypatch, lambda req: httpx.Response(200, content=b"%PDF-" + b"0" * (2 << 20)))
    assert client.post("/api/add", json={"input": "https://e.org/a"}).status_code == 413
    _serve(monkeypatch, lambda req: httpx.Response(404))
    assert client.post("/api/add", json={"input": "https://e.org/a"}).status_code == 502
    assert not fake.calls


# ---- publisher article links (linXiv v0.7.0 recognize.rs vectors) ----


@pytest.mark.parametrize(
    ("url", "doi", "pdf_url"),
    [
        (
            "https://journals.aps.org/prl/pdf/10.1103/PhysRevLett.128.073601",
            "10.1103/PhysRevLett.128.073601",
            "https://journals.aps.org/prl/pdf/10.1103/PhysRevLett.128.073601",
        ),
        (
            "https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.128.073601",
            "10.1103/PhysRevLett.128.073601",
            "https://journals.aps.org/prl/pdf/10.1103/PhysRevLett.128.073601",
        ),
        (
            "journals.aps.org/prl/pdf/10.1103/PhysRevLett.128.073601",
            "10.1103/PhysRevLett.128.073601",
            "https://journals.aps.org/prl/pdf/10.1103/PhysRevLett.128.073601",
        ),
        (
            "https://onlinelibrary.wiley.com/doi/epdf/10.1002/anie.202100001",
            "10.1002/anie.202100001",
            "https://onlinelibrary.wiley.com/doi/pdf/10.1002/anie.202100001",
        ),
        (
            "https://pubs.acs.org/doi/pdf/10.1021/jacs.1c00001",
            "10.1021/jacs.1c00001",
            "https://pubs.acs.org/doi/pdf/10.1021/jacs.1c00001",
        ),
        (
            "https://www.tandfonline.com/doi/full/10.1080/00268976.2021.1900001",
            "10.1080/00268976.2021.1900001",
            "https://www.tandfonline.com/doi/pdf/10.1080/00268976.2021.1900001",
        ),
        (
            "https://dl.acm.org/doi/10.1145/3290605.3300234",
            "10.1145/3290605.3300234",
            "https://dl.acm.org/doi/pdf/10.1145/3290605.3300234",
        ),
        (
            "https://epubs.siam.org/doi/abs/10.1137/20M1234567",
            "10.1137/20M1234567",
            "https://epubs.siam.org/doi/pdf/10.1137/20M1234567",
        ),
        (
            "https://journals.sagepub.com/doi/pdf/10.1177/0956797620000001",
            "10.1177/0956797620000001",
            "https://journals.sagepub.com/doi/pdf/10.1177/0956797620000001",
        ),
        (
            "https://www.science.org/doi/10.1126/science.abc1234",
            "10.1126/science.abc1234",
            "https://www.science.org/doi/pdf/10.1126/science.abc1234",
        ),
        (
            "https://www.pnas.org/doi/full/10.1073/pnas.2000001117?af=R#sec-1",
            "10.1073/pnas.2000001117",
            "https://www.pnas.org/doi/pdf/10.1073/pnas.2000001117",
        ),
        (
            "https://iopscience.iop.org/article/10.1088/1742-6596/1234/1/012345/pdf",
            "10.1088/1742-6596/1234/1/012345",
            "https://iopscience.iop.org/article/10.1088/1742-6596/1234/1/012345/pdf",
        ),
        (
            "https://iopscience.iop.org/article/10.1088/1742-6596/1234/1/012345/meta",
            "10.1088/1742-6596/1234/1/012345",
            "https://iopscience.iop.org/article/10.1088/1742-6596/1234/1/012345/pdf",
        ),
        (
            "https://iopscience.iop.org/article/10.1088/1742-6596/1234/1/012345",
            "10.1088/1742-6596/1234/1/012345",
            "https://iopscience.iop.org/article/10.1088/1742-6596/1234/1/012345/pdf",
        ),
        (
            "https://link.springer.com/content/pdf/10.1007/s00220-020-03456-7.pdf?pdf=button",
            "10.1007/s00220-020-03456-7",
            "https://link.springer.com/content/pdf/10.1007/s00220-020-03456-7.pdf?pdf=button",
        ),
        (
            "https://link.springer.com/article/10.1007/s00220-020-03456-7",
            "10.1007/s00220-020-03456-7",
            "https://link.springer.com/content/pdf/10.1007/s00220-020-03456-7.pdf",
        ),
        (
            "https://link.springer.com/chapter/10.1007/978-3-030-12345-6_7",
            "10.1007/978-3-030-12345-6_7",
            "https://link.springer.com/content/pdf/10.1007/978-3-030-12345-6_7.pdf",
        ),
        (
            "https://www.nature.com/articles/s41586-020-2649-2",
            "10.1038/s41586-020-2649-2",
            "https://www.nature.com/articles/s41586-020-2649-2.pdf",
        ),
        (
            "https://www.nature.com/articles/s41586-020-2649-2.pdf",
            "10.1038/s41586-020-2649-2",
            "https://www.nature.com/articles/s41586-020-2649-2.pdf",
        ),
    ],
)
def test_publisher_doi(url, doi, pdf_url):
    assert add.publisher_doi(url) == (doi, pdf_url)
    assert classify(url) == ("doi", doi)


@pytest.mark.parametrize(
    "url",
    [
        "https://journals.aps.org/prl/issues/128/7",
        "https://journals.aps.org/prl/pdf/not-a-doi",
        "https://pubs.acs.org/doi/pdf/",
        "https://www.nature.com/articles/s41586-020-2649-2/figures/1",
        "https://www.nature.com/nature/volumes",
        "https://www.sciencedirect.com/science/article/pii/S0370269320300001",
        "10.1038/nature14539",
    ],
)
def test_publisher_doi_unrecognized(url):
    assert add.publisher_doi(url) is None


NATURE = "https://www.nature.com/articles/s41586-020-2649-2"
NATURE_SID = "doi:10.1038/s41586-020-2649-2"


def _publisher_fake(fake, has_pdf=False):
    fake.on("doi", "save", result={"saved": True, "metadata": {"source_id": NATURE_SID}})
    fake.on("paper", "get", result={"source_id": NATURE_SID, "has_pdf": has_pdf})
    fake.on("pdf", "download", result={"path": "/pdfs/x.pdf"})


def test_add_publisher_link_saves_doi_and_pdf(client, fake, monkeypatch):
    seen = []

    async def ok(url, dest, limit, timeout):
        seen.append(url)

    monkeypatch.setattr(add, "download_pdf_to", ok)
    _publisher_fake(fake)
    r = client.post("/api/add", json={"input": NATURE})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "doi" and r.json()["pdf_saved"] is True
    assert fake.calls[0] == ["doi", "save", "--", "10.1038/s41586-020-2649-2"]
    pdf = NATURE + ".pdf"
    assert seen == [pdf]
    assert ["pdf", "download", "--", NATURE_SID, pdf] in fake.calls


def test_add_publisher_paywall_keeps_metadata_only(client, fake, monkeypatch):
    async def paywall(url, dest, limit, timeout):
        raise HTTPException(status_code=502, detail="PDF link returned HTTP 403")

    monkeypatch.setattr(add, "download_pdf_to", paywall)
    _publisher_fake(fake)
    r = client.post("/api/add", json={"input": NATURE})
    assert r.status_code == 200, r.text
    assert r.json()["pdf_saved"] is False
    assert not any(c[:2] == ["pdf", "download"] for c in fake.calls)


def test_add_publisher_skips_pdf_when_already_saved(client, fake, monkeypatch):
    async def boom(*a):
        raise AssertionError("no download expected")

    monkeypatch.setattr(add, "download_pdf_to", boom)
    _publisher_fake(fake, has_pdf=True)
    r = client.post("/api/add", json={"input": NATURE})
    assert "pdf_saved" not in r.json()
