"""Add a paper from one pasted string: arXiv id/link, DOI/doi.org link, or PDF link."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
import tempfile
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

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


def classify(text: str) -> tuple[str, str]:
    """('arxiv', id) | ('doi', doi) | ('pdf', url), or 400 when it's none of them."""
    text = text.strip()
    if m := _ARXIV_BARE.match(text):
        return "arxiv", m.group(1)
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
        return {"kind": kind, "paper": paper}

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
