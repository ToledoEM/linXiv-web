"""Remote search, library listing, paper metadata, tags, stats."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from ..cli import CLIError
from .common import ident, run

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


def _matches(paper: dict, needle: str) -> bool:
    fields = [paper.get("title"), paper.get("source_id"), paper.get("doi")]
    fields += paper.get("authors") or []
    fields += paper.get("tags") or []
    return any(needle in str(f).lower() for f in fields if f)


@router.get("/papers")
async def list_papers(
    request: Request,
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
    """Library listing. `fulltext` uses linXiv's TeX-source index (`paper search`);
    otherwise `q`/`tag`/`pdf` filter `linxiv list` by title, id, DOI, authors, tags
    and whether a PDF is saved."""
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
    papers = await run(request, args)
    if not filtering or not isinstance(papers, list):
        return papers
    needle = ident(q, "query").lower() if q else None
    hits = [
        p
        for p in papers
        if (needle is None or _matches(p, needle))
        and (tag is None or tag in (p.get("tags") or []))
        and (pdf is None or bool(p.get("has_pdf")) == (pdf == "has"))
    ]
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
    return await run(request, ["paper", "get", "--", ident(source_id)])


@router.delete("/papers/{source_id:path}")
async def delete_paper(request: Request, source_id: str):
    return await run(request, ["paper", "delete", "--", ident(source_id)])
