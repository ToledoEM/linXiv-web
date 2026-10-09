"""Remote search, library listing, paper metadata, tags, stats."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field

from ..cli import CLIError
from ..pdf_name import pdf_file, title_from_file, title_suspect
from .common import ident, run, settings

router = APIRouter(prefix="/api", tags=["library"])

Source = Literal["arxiv", "openalex", "crossref"]


@router.get("/search")
async def search(
    request: Request,
    q: str,
    source: Source = "arxiv",
    max: int = Query(10, ge=1, le=100),
):
    return await run(
        request,
        ["search", "--source", source, "--max", str(max), "--", ident(q, "query")],
        long=True,
    )


# Full-text/notes search kicks in from this many characters (desktop LibraryPage).
DEEP_SEARCH_MIN = 3
DEEP_SEARCH_LIMIT = 200


def _annotate(request: Request, papers):
    """Add `pdf_file` (the PDF's path inside the PDF folder) and `title_suspect`
    (the title looks like junk read from the PDF, or unlike the file name)."""
    s = settings(request)
    bases = [str(s.data_dir / "pdfs"), str(s.pdf_dir)]
    for p in papers if isinstance(papers, list) else [papers]:
        if isinstance(p, dict):
            rel = pdf_file(p.get("pdf_path"), bases)
            p["pdf_file"] = rel
            p["title_suspect"] = title_suspect(p.get("title"), title_from_file(rel))
    return papers


def _matches(paper: dict, needle: str) -> bool:
    fields = [paper.get("title"), paper.get("summary"), paper.get("source_id"), paper.get("doi")]
    fields += paper.get("authors") or []
    fields += paper.get("tags") or []
    return any(needle in str(f).lower() for f in fields if f)


@router.get("/papers")
async def list_papers(
    request: Request,
    response: Response,
    q: str | None = None,
    fulltext: bool = False,
    tag: str | None = None,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    category: str | None = None,
    sort: Literal["published", "added", "title"] = "published",
    dir: Literal["asc", "desc"] | None = None,
    pdf: Literal["has", "none"] | None = None,
):
    """Library listing. `q`/`tag`/`pdf` filter `linxiv list` by title, abstract,
    id, DOI, authors, tags and whether a PDF is saved. A `q` of 3+ characters also
    takes `paper search` hits (indexed TeX full text and note titles/bodies);
    papers found only that way carry `deep_match: true`. If that search fails the
    plain matches still return, with an `X-Deep-Search-Error` header.
    `fulltext` alone returns the `paper search` hits only."""
    if q and fulltext:
        return await run(
            request, ["paper", "search", "--limit", str(limit), "--", ident(q, "query")]
        )
    filtering = bool(q or tag or pdf)
    args = ["list", "--sort", sort]
    # The CLI has no text filter, so filtered listings page in Python.
    if not filtering:
        args += ["--limit", str(limit), "--offset", str(offset)]
    if category:
        args += ["--category", ident(category, "category")]
    if dir:
        args += ["--dir", dir]
    papers = _annotate(request, await run(request, args))
    if not filtering or not isinstance(papers, list):
        return papers
    needle = ident(q, "query").lower() if q else None
    deep: set[str] = set()
    if needle and len(needle.strip()) >= DEEP_SEARCH_MIN:
        try:
            found = await run(
                request,
                ["paper", "search", "--limit", str(DEEP_SEARCH_LIMIT), "--", ident(q, "query")],
            )
            deep = {str(p.get("source_id")) for p in found or [] if isinstance(p, dict)}
        except CLIError as e:
            response.headers["X-Deep-Search-Error"] = (
                e.message[:200].encode("ascii", "replace").decode()
            )
    hits = []
    for p in papers:
        if tag is not None and tag not in (p.get("tags") or []):
            continue
        if pdf is not None and bool(p.get("has_pdf")) != (pdf == "has"):
            continue
        if needle is None or _matches(p, needle):
            hits.append(p)
        elif p.get("source_id") in deep:
            hits.append({**p, "deep_match": True})
    return hits[offset : offset + limit]


@router.get("/categories")
async def categories(request: Request):
    return await run(request, ["categories"])


@router.get("/tags")
async def all_tags(request: Request):
    return await run(request, ["tag", "list-all"])


@router.get("/stats")
async def stats(request: Request):
    return await run(request, ["stats"])


# Paper routes take `{source_id:path}` because old-style arXiv ids carry a slash
# (hep-th/9901001). Suffixed routes must be declared before the bare one.


@router.post("/papers/{source_id:path}/fetch")
async def fetch(request: Request, source_id: str, source: Source = "arxiv"):
    sid = ident(source_id)
    out = await run(request, ["fetch", "--source", source, "--", sid], long=True, raw=True)
    # arXiv papers print a Markdown summary, other sources print metadata JSON.
    try:
        meta = json.loads(out)
        sid = meta.get("source_id", sid) if isinstance(meta, dict) else sid
    except ValueError:
        pass
    try:
        return await run(request, ["paper", "get", "--", sid])
    except CLIError:
        return {"source_id": sid}


@router.get("/papers/{source_id:path}/versions")
async def versions(request: Request, source_id: str):
    return await run(request, ["paper", "versions", "--", ident(source_id)])


class TagsBody(BaseModel):
    tags: list[str] = Field(min_length=1, max_length=50)


@router.get("/papers/{source_id:path}/tags")
async def list_tags(request: Request, source_id: str):
    return await run(request, ["tag", "list", "--", ident(source_id)])


@router.post("/papers/{source_id:path}/tags")
async def add_tags(request: Request, source_id: str, body: TagsBody):
    tags = [ident(t, "tag") for t in body.tags]
    return await run(request, ["tag", "add", "--", ident(source_id), *tags])


@router.delete("/papers/{source_id:path}/tags")
async def remove_tags(
    request: Request, source_id: str, tag: Annotated[list[str], Query(min_length=1)]
):
    tags = [ident(t, "tag") for t in tag]
    return await run(request, ["tag", "remove", "--", ident(source_id), *tags])


@router.get("/papers/{source_id:path}")
async def get_paper(request: Request, source_id: str):
    return _annotate(request, await run(request, ["paper", "get", "--", ident(source_id)]))


@router.delete("/papers/{source_id:path}")
async def delete_paper(request: Request, source_id: str):
    return await run(request, ["paper", "delete", "--", ident(source_id)])
