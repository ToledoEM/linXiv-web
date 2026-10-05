"""Authors (`linxiv author ...`)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .common import run

router = APIRouter(prefix="/api", tags=["authors"])


@router.get("/authors")
async def list_authors(request: Request, hide_single: bool = False):
    """`author list`; `hide_single` drops authors with fewer than two papers
    (the CLI has no such flag, so it's filtered here)."""
    authors = await run(request, ["author", "list"])
    if not hide_single or not isinstance(authors, list):
        return authors
    return [a for a in authors if (a.get("paper_count") or 0) > 1]
