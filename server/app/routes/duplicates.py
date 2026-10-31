"""Duplicates page: groups found by the "Find duplicate papers" maintenance
operation, in the library in view; merge or dismiss them."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..duplicates import REPORT, group_key
from ..maintenance import read_report, report_lock, report_path, write_report
from ..tsv import tsv_response
from .common import ident, library, run

router = APIRouter(prefix="/api/duplicates", tags=["duplicates"])


class MergeIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    winner: str = Field(min_length=1, max_length=512)
    loser: str = Field(min_length=1, max_length=512)


class DismissIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_ids: list[str] = Field(min_length=2, max_length=100)


def _public(report: dict) -> dict:
    return {"scanned_at": report.get("scanned_at"), "groups": report.get("groups") or []}


@router.get("")
async def duplicates(request: Request):
    return _public(read_report(report_path(library(request), REPORT)))


@router.get("/export.tsv")
async def export_tsv(request: Request):
    """The library's duplicate groups, one row per paper, groups numbered in order."""
    lib = library(request)
    groups = read_report(report_path(lib, REPORT)).get("groups") or []
    cols = ("source_id", "version", "title", "file", "size")
    rows = [
        (n, g.get("sha256", ""), *(p.get(k, "") for k in cols))
        for n, g in enumerate(groups, 1)
        for p in g.get("papers") or []
    ]
    header = ["group", "sha256", "source_id", "version", "title", "file", "size"]
    return tsv_response(header, rows, f"duplicates-{lib.key}.tsv")


@router.post("/merge")
async def merge(request: Request, body: MergeIn):
    """Keep `winner`; linXiv moves the loser's notes, highlights, projects, tags,
    missing versions and PDFs over, then deletes the loser."""
    winner, loser = ident(body.winner, "paper id"), ident(body.loser, "paper id")
    if winner == loser:
        raise HTTPException(status_code=400, detail="pick two different papers")
    path = report_path(library(request), REPORT)
    async with report_lock(path):
        report = read_report(path)
        groups = report.get("groups") or []
        group = next(
            (g for g in groups if {winner, loser} <= {p["source_id"] for p in g["papers"]}), None
        )
        if group is None:
            raise HTTPException(status_code=404, detail="these papers are not a duplicate group")
        await run(request, ["paper", "merge", "--", winner, loser])
        group["papers"] = [p for p in group["papers"] if p["source_id"] != loser]
        if len({p["source_id"] for p in group["papers"]}) < 2:
            groups.remove(group)
        write_report(path, {**report, "groups": groups})
    return _public(report | {"groups": groups})


@router.post("/dismiss")
async def dismiss(request: Request, body: DismissIn):
    """Not duplicates: the group stays hidden in later scans while its papers stay
    the same."""
    key = group_key([ident(s, "paper id") for s in body.source_ids])
    path = report_path(library(request), REPORT)
    async with report_lock(path):
        report = read_report(path)
        groups = [
            g
            for g in report.get("groups") or []
            if group_key([p["source_id"] for p in g["papers"]]) != key
        ]
        dismissed = sorted({*(report.get("dismissed") or []), key})
        report = {**report, "groups": groups, "dismissed": dismissed}
        write_report(path, report)
    return _public(report)
