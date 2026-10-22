"""Remote search, library listing, paper metadata, tags, stats."""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from ..cli import CLIError
from ..pdf_name import pdf_file, title_from_file, title_suspect
from .common import ident, library, run

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
    lib = library(request)
    bases = [str(lib.data_dir / "pdfs"), str(lib.pdf_dir)]
    for p in papers if isinstance(papers, list) else [papers]:
        if isinstance(p, dict):
            rel = pdf_file(p.get("pdf_path"), bases)
            p["pdf_file"] = rel
            p["title_suspect"] = title_suspect(p.get("title"), title_from_file(rel))
    return papers


_TERM = re.compile(r'"([^"]+)"|(\S+)')


def _terms(q: str) -> list[str]:
    """Lowercased search words; a "quoted part" stays one phrase."""
    terms = (a or b for a, b in _TERM.findall(q.lower()))
    return [t for t in (t.strip() for t in terms) if t]


def _matches(paper: dict, terms: list[str]) -> bool:
    """Every term is in some field (title, abstract, id, DOI, authors, tags)."""
    fields = [paper.get("title"), paper.get("summary"), paper.get("source_id"), paper.get("doi")]
    fields += paper.get("authors") or []
    fields += paper.get("tags") or []
    text = [str(f).lower() for f in fields if f]
    return all(any(t in f for f in text) for t in terms)


def _db_stamp(request: Request) -> tuple:
    """Changes whenever papers.db is written, by the CLI, linxiv-mcp or this server."""
    db = library(request).data_dir / "papers.db"
    stamp = []
    for f in (db, db.with_name(db.name + "-wal")):
        try:
            st = f.stat()
            stamp.append((st.st_mtime_ns, st.st_size))
        except OSError:
            stamp.append(None)
    return tuple(stamp)


async def _full_list(request: Request, args: list[str]):
    """Unpaged `linxiv list`, annotated, reused until papers.db changes. Callers
    must not mutate the returned papers."""
    caches = getattr(request.app.state, "list_cache", None)
    if caches is None:
        caches = request.app.state.list_cache = {}
    # One cache per library, each stamped by its own papers.db.
    cache = caches.setdefault(library(request).key, {})
    stamp = _db_stamp(request)
    for k in [k for k, (s, _) in cache.items() if s != stamp]:
        del cache[k]
    key = tuple(args)
    if key not in cache:
        cache[key] = (stamp, _annotate(request, await run(request, args)))
    return cache[key][1]


SortKey = Literal["published", "added", "title", "authors", "category", "tags", "pdf"]
CLI_SORTS = ("published", "added", "title")
_DIGITS = re.compile(r"(\d+)")


def _sort_value(p: dict, key: str) -> str:
    if key == "authors":
        value = (p.get("authors") or [""])[0]
    elif key == "tags":
        value = ", ".join(p.get("tags") or [])
    elif key == "pdf":
        value = "1" if p.get("has_pdf") else ""
    else:
        value = p.get(key)
    return str(value or "").strip()


def _natural(value: str) -> list[tuple[int, int | str]]:
    """Case-insensitive, digit runs compared as numbers ("v2" before "v10")."""
    return [
        (0, int(part)) if part.isdigit() else (1, part)
        for part in _DIGITS.split(value.casefold())
        if part
    ]


def sort_papers(papers: list, key: str, dir: str) -> list:
    """Stable sort by one column (web `paperSort.ts`); empty values last either way."""
    keyed = [(_sort_value(p, key), p) for p in papers]
    full = [x for x in keyed if x[0]]
    full.sort(key=lambda x: _natural(x[0]), reverse=dir == "desc")
    return [p for _, p in full] + [p for v, p in keyed if not v]


@router.get("/papers")
async def list_papers(
    request: Request,
    response: Response,
    q: str | None = None,
    fulltext: bool = False,
    tag: str | None = None,
    untagged: bool = False,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    category: str | None = None,
    sort: SortKey = "published",
    dir: Literal["asc", "desc"] | None = None,
    pdf: Literal["has", "none"] | None = None,
):
    """Library listing. `q`/`tag`/`untagged`/`pdf` filter `linxiv list` by title,
    abstract, id, DOI, authors, tags (or none) and whether a PDF is saved; every word
    of `q` must match, a "quoted phrase" as a whole. A `q` of 3+ characters also
    takes `paper search` hits (indexed TeX full text and note titles/bodies);
    papers found only that way carry `deep_match: true`. If that search fails the
    plain matches still return, with an `X-Deep-Search-Error` header.
    `sort` authors/category/tags/pdf orders the whole result before paging.
    `X-Total-Count` carries the number of papers across all pages.
    `fulltext` alone returns the `paper search` hits only."""
    if q and fulltext:
        return await run(
            request, ["paper", "search", "--limit", str(limit), "--", ident(q, "query")]
        )
    if tag is not None and untagged:
        raise HTTPException(status_code=400, detail="Use either tag or untagged, not both")
    # The CLI sorts by date, added or title only and has no text filter, so the
    # cached full list is filtered, sorted and paged here (and the total is known).
    cli_sort = sort in CLI_SORTS
    args = ["list", "--sort", sort if cli_sort else "published"]
    if category:
        args += ["--category", ident(category, "category")]
    if dir and cli_sort:
        args += ["--dir", dir]
    papers = await _full_list(request, args)
    if not isinstance(papers, list):
        return papers
    terms = _terms(ident(q, "query")) if q else None
    deep: set[str] = set()
    if terms and len(q.strip()) >= DEEP_SEARCH_MIN:
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
        if untagged and p.get("tags"):
            continue
        if pdf is not None and bool(p.get("has_pdf")) != (pdf == "has"):
            continue
        if not terms or _matches(p, terms):
            hits.append(p)
        elif p.get("source_id") in deep:
            hits.append({**p, "deep_match": True})
    if not cli_sort:
        hits = sort_papers(hits, sort, dir or "asc")
    response.headers["X-Total-Count"] = str(len(hits))
    return hits[offset : offset + limit]


@router.get("/categories")
async def categories(request: Request):
    return await run(request, ["categories"])


@router.get("/tags")
async def all_tags(request: Request):
    return await run(request, ["tag", "list-all"])


@router.get("/tags/counts")
async def tag_counts(request: Request):
    """Papers per tag (count desc, then name), plus untagged and total paper counts.
    Tags no paper carries are listed with 0."""
    papers = [p for p in (await run(request, ["list"]) or []) if isinstance(p, dict)]
    counts: dict[str, int] = {t: 0 for t in await run(request, ["tag", "list-all"]) or []}
    untagged = 0
    for p in papers:
        tags = p.get("tags") or []
        if not tags:
            untagged += 1
        for t in set(tags):
            counts[t] = counts.get(t, 0) + 1
    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "tags": [{"tag": t, "count": n} for t, n in rows],
        "untagged": untagged,
        "total": len(papers),
    }


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
