"""Add a paper from one pasted string: arXiv id/link, DOI/doi.org link, publisher
article link (saved by its DOI), or PDF link."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
import tempfile
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..cli import CLIError
from .common import ident, run, settings
from .library import fetch

router = APIRouter(prefix="/api", tags=["add"])

_ARXIV_ID = r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?"
_ARXIV_BARE = re.compile(rf"^(?:arxiv:)?{_ARXIV_ID}$", re.IGNORECASE)
_ARXIV_PATH = re.compile(rf"^/(?:abs|pdf|html)/{_ARXIV_ID}(?:\.pdf)?/?$")
_ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_DOI_HOSTS = {"doi.org", "dx.doi.org", "www.doi.org"}
_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)
_MAX_REDIRECTS = 5
_CHUNK = 1024 * 1024

# Publisher article URLs that carry the DOI, ported from linXiv v0.7.0
# `core::recognize` (PUBLISHER_DOI_PATHS): (hosts sans `www.`, path prefix,
# optional suffixes, DOI registrant for suffix-only paths, PDF path template).
# Prefix segments are `*` or `a|b` alternatives; the template fills `{1}` with
# the first path segment and `{id}` with the DOI part. Elsevier, IEEE and JSTOR
# URLs don't carry the DOI, so they are absent.
_ATYPON_HOSTS = frozenset(
    {
        "onlinelibrary.wiley.com",
        "pubs.acs.org",
        "tandfonline.com",
        "dl.acm.org",
        "epubs.siam.org",
        "journals.sagepub.com",
        "science.org",
        "pnas.org",
    }
)
_PUBLISHER_DOI_PATHS: list[tuple[frozenset[str], str, tuple[str, ...], str, str]] = [
    (frozenset({"journals.aps.org"}), "*/pdf|abstract", (), "", "{1}/pdf/{id}"),
    (_ATYPON_HOSTS, "doi/pdf|epdf|abs|full", (), "", "doi/pdf/{id}"),
    (_ATYPON_HOSTS, "doi", (), "", "doi/pdf/{id}"),
    (frozenset({"iopscience.iop.org"}), "article", ("/pdf", "/meta"), "", "article/{id}/pdf"),
    (frozenset({"link.springer.com"}), "content/pdf", (".pdf",), "", "content/pdf/{id}.pdf"),
    (frozenset({"link.springer.com"}), "article|chapter", (), "", "content/pdf/{id}.pdf"),
    (frozenset({"nature.com"}), "articles", (".pdf",), "10.1038", "articles/{id}.pdf"),
]
_BARE_HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+/", re.IGNORECASE)


def publisher_doi(text: str) -> tuple[str, str] | None:
    """(DOI, publisher PDF URL) for a known publisher article link, else None.
    A pasted PDF link keeps its URL; other pages get the PDF path swapped in."""
    text = text.strip()
    if _BARE_HOST.match(text) and not text.startswith("10."):
        text = "https://" + text
    if not text.lower().startswith(("http://", "https://")):
        return None
    parts = urlsplit(text)
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.strip("/")
    first = path.split("/", 1)[0]
    for hosts, prefix, suffixes, registrant, template in _PUBLISHER_DOI_PATHS:
        if host not in hosts:
            continue
        rest: str | None = path
        for seg in prefix.split("/"):
            head, sep, tail = rest.partition("/")
            if not sep or (seg != "*" and head not in seg.split("|")):
                rest = None
                break
            rest = tail
        if rest is None:
            continue
        for suffix in suffixes:
            if rest.endswith(suffix):
                rest = rest[: -len(suffix)]
                break
        if registrant:
            if not rest or "/" in rest:
                continue
            doi = f"{registrant}/{rest}"
        else:
            doi = rest
        reg, _, tail = doi.partition("/")
        if not reg.startswith("10.") or not tail:
            continue
        pdf_path = template.replace("{1}", first).replace("{id}", rest)
        if path == pdf_path:
            return doi, text
        return doi, urlunsplit((parts.scheme, parts.netloc, "/" + pdf_path, "", ""))
    return None


def classify(text: str) -> tuple[str, str]:
    """('arxiv', id) | ('doi', doi) | ('pdf', url), or 400 when it's none of them."""
    text = text.strip()
    if m := _ARXIV_BARE.match(text):
        return "arxiv", m.group(1)
    if pub := publisher_doi(text):
        return "doi", pub[0]
    doi = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    if text.lower().startswith(("http://", "https://")):
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
        if host in _ARXIV_HOSTS and (m := _ARXIV_PATH.match(parts.path)):
            return "arxiv", m.group(1)
        if host in _DOI_HOSTS:
            doi = unquote(parts.path.lstrip("/"))
        else:
            return "pdf", text
    if _DOI.match(doi):
        # arXiv-minted DOIs (10.48550/arXiv.<id>) go through the arXiv fetch.
        if (m := _ARXIV_DOI.match(doi)) and (a := _ARXIV_BARE.match(m.group(1))):
            return "arxiv", a.group(1)
        return "doi", doi
    raise HTTPException(
        status_code=400, detail="not an arXiv id or link, a DOI, or an http(s) PDF link"
    )


async def _resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


async def _check_public(url: str) -> None:
    """Refuse URLs that aren't http(s) or that resolve to a non-public address
    (loopback, private LAN, link-local, cloud metadata...)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise HTTPException(status_code=400, detail="PDF link must be http(s)")
    try:
        addrs = await _resolve(parts.hostname)
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"cannot resolve {parts.hostname}") from e
    if not addrs or not all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs):
        raise HTTPException(status_code=400, detail="PDF link must point at a public host")


def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, headers={"User-Agent": "linxiv-web"}
    )


async def download_pdf_to(url: str, dest: Path, limit: int, timeout: float) -> None:
    """Stream a PDF to `dest`, re-checking every redirect hop and capping the size."""
    async with _client(timeout) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            await _check_public(url)
            async with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    url = urljoin(url, resp.headers.get("location", ""))
                    continue
                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=502, detail=f"PDF link returned HTTP {resp.status_code}"
                    )
                size = 0
                with dest.open("wb") as out:
                    async for chunk in resp.aiter_bytes(_CHUNK):
                        if size == 0 and not chunk.startswith(b"%PDF-"):
                            raise HTTPException(status_code=400, detail="link is not a PDF")
                        size += len(chunk)
                        if size > limit:
                            raise HTTPException(status_code=413, detail="PDF too large")
                        out.write(chunk)
                if size == 0:
                    raise HTTPException(status_code=400, detail="link returned an empty file")
                return
    raise HTTPException(status_code=502, detail="too many redirects")


async def _attach_publisher_pdf(request: Request, sid: str, url: str) -> bool:
    """Best effort, like linXiv's DOI save with a publisher PDF: a paywall (403)
    or HTML page leaves the paper metadata-only. `linxiv pdf download` keeps
    whatever the link returns, so the link is checked here first (public host,
    size cap, `%PDF-` body) and only a real PDF is handed to the CLI, which
    fetches it again and records it on the paper."""
    s = settings(request)
    fd, tmp = tempfile.mkstemp(prefix="linxiv-web-", suffix=".pdf")
    os.close(fd)
    try:
        await download_pdf_to(url, Path(tmp), s.max_upload_mb * 1024 * 1024, s.timeout_long)
        await run(request, ["pdf", "download", "--", sid, url], long=True)
    except (HTTPException, httpx.HTTPError, CLIError):
        return False
    finally:
        Path(tmp).unlink(missing_ok=True)
    return True


class AddBody(BaseModel):
    input: str = Field(min_length=1, max_length=2048)


@router.post("/add")
async def add_paper(request: Request, body: AddBody):
    """Returns {kind, paper}: the saved paper's `paper get` JSON (or a stub)."""
    kind, value = classify(body.input)
    if kind == "arxiv":
        return {"kind": kind, "paper": await fetch(request, value, "arxiv")}
    if kind == "doi":
        out = await run(request, ["doi", "save", "--", ident(value, "DOI")], long=True)
        meta = out.get("metadata") if isinstance(out, dict) else None
        sid = (meta or {}).get("source_id") or f"doi:{value}"
        try:
            paper = await run(request, ["paper", "get", "--", sid])
        except CLIError:
            paper = {"source_id": sid, "title": (meta or {}).get("title")}
        result = {"kind": kind, "paper": paper}
        pub = publisher_doi(body.input)
        if pub and not paper.get("has_pdf"):
            result["pdf_saved"] = await _attach_publisher_pdf(request, sid, pub[1])
            if result["pdf_saved"]:
                paper = await run(request, ["paper", "get", "--", sid])
                result["paper"] = paper
        return result

    s = settings(request)
    fd, tmp = tempfile.mkstemp(prefix="linxiv-web-", suffix=".pdf")
    os.close(fd)
    try:
        await download_pdf_to(value, Path(tmp), s.max_upload_mb * 1024 * 1024, s.timeout_long)
        paper = await run(request, ["pdf", "import", "--", tmp], long=True)
        return {"kind": kind, "paper": paper}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"PDF download failed: {e}") from e
    finally:
        Path(tmp).unlink(missing_ok=True)
