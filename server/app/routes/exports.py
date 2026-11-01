"""Exports for an arbitrary paper selection (the CLI exports whole projects only)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .. import bib_store, bibtex
from .common import library, run

router = APIRouter(prefix="/api", tags=["exports"])


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ids: list[str] = Field(min_length=1, max_length=1000)


@router.post("/export/bibtex")
async def export_bibtex(request: Request, body: Selection):
    """`.bib` file for the selected papers, in selection order."""
    papers = await run(request, ["list", "--sort", "added"])
    by_id = {p.get("source_id"): p for p in papers or [] if isinstance(p, dict)}
    picked = [by_id[i] for i in dict.fromkeys(body.ids) if i in by_id]
    if not picked:
        raise HTTPException(404, "none of the selected papers were found")
    rows = await bib_store.get_many(library(request), [p["source_id"] for p in picked])
    bibs = {sid: row["bib"] for sid, row in rows.items()}
    return Response(
        bibtex.render(picked, bibs),
        media_type="application/x-bibtex; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="linxiv-selection.bib"'},
    )
