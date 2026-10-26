"""Papers the "Complete metadata of new papers" operation could not complete, for
the library in view. Library opens them in batch edit."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ..maintenance import read_report, report_lock, report_path, write_report
from ..metadata_fill import REPORT, gaps
from .common import ident, library
from .library import _full_list

router = APIRouter(prefix="/api/metadata-review", tags=["metadata"])


class RemoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_ids: list[str] = Field(min_length=1, max_length=1000)


@router.get("")
async def review(request: Request):
    """Still listed papers that still miss something (a paper fixed or deleted
    since the run drops out)."""
    lib = library(request)
    listed = read_report(report_path(lib, REPORT)).get("papers") or []
    if not listed:
        return {"papers": []}
    bases = [str(lib.data_dir / "pdfs"), str(lib.pdf_dir)]
    current = {p.get("source_id"): p for p in await _full_list(request, ["list"])}
    papers = []
    for entry in listed:
        paper = current.get(entry.get("source_id"))
        if paper is not None and (missing := gaps(paper, bases)):
            papers.append({**entry, "title": paper.get("title") or "", "missing": missing})
    return {"papers": papers}


@router.post("/remove")
async def remove(request: Request, body: RemoveIn):
    """Take papers off the list (skipped in batch edit)."""
    drop = {ident(s, "paper id") for s in body.source_ids}
    path = report_path(library(request), REPORT)
    async with report_lock(path):
        report = read_report(path)
        report["papers"] = [p for p in report.get("papers") or [] if p.get("source_id") not in drop]
        write_report(path, report)
    return {"ok": True}
