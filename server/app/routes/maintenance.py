"""Settings → Server Admin → Maintenance operations (admins only)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ..auth import current_user
from ..db_backup import NAME, backups
from ..jobs import JobBusy
from ..maintenance import (
    MAX_KEEP_BACKUPS,
    MAX_TRASH_DAYS,
    ROOT,
    Maintenance,
    library_keys,
    read_report,
    report_path,
)
from ..metadata_fill import FILLS, OPTIONS_SETTING, options_from
from ..pdf_check import (
    MAX_LISTED,
    MAX_SKIP,
    ORPHAN_KIND,
    ORPHANS,
    move_orphans,
    skip_from,
    valid_folder,
)
from ..pdf_check import OPTIONS_SETTING as PDF_CHECK_OPTIONS
from ..pdf_check import REPORT as PDF_CHECK
from ..tsv import tsv_response
from .metadata import ID_SOURCES

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    hour: int = Field(ge=0, le=23)
    nightly: list[str] = Field(max_length=50)
    keep_backups: int | None = Field(None, ge=1, le=MAX_KEEP_BACKUPS)
    trash_days: int | None = Field(None, ge=0, le=MAX_TRASH_DAYS)


def _maint(request: Request) -> Maintenance:
    return request.app.state.maintenance


@router.get("")
async def overview(request: Request):
    m = _maint(request)
    stored = await m.stored()
    status = m.status_from(stored)
    ops = []
    for op in m.ops.values():
        job = m.running(op.id)
        ops.append({**op.public(), "last": status.get(op.id), "job": job.public() if job else None})
    return {
        **m.schedule_from(stored),
        "timezone": m.now().tzname(),
        "nightly_on": status.get("nightly_on"),
        "ops": ops,
    }


@router.put("/schedule")
async def set_schedule(request: Request, body: ScheduleIn):
    m = _maint(request)
    unknown = [i for i in body.nightly if i not in m.ops]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown operation: {', '.join(unknown)}")
    return await m.set_schedule(body.hour, body.nightly, body.keep_backups, body.trash_days)


@router.post("/{op_id}/run")
async def run_op(request: Request, op_id: str):
    m = _maint(request)
    if op_id not in m.ops:
        raise HTTPException(status_code=404, detail=f"Operation {op_id} not found")
    try:
        job = m.start(op_id, current_user(request).get("id"))
    except JobBusy as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return job.public()


@router.get("/backups")
async def list_backups(request: Request):
    """Database backups kept on the server, every library, newest first per library."""
    out = []
    for key in library_keys(request.app):
        lib = request.app.state.libraries.get(key)
        for path in backups(lib):
            st = path.stat()
            out.append({"library": key, "name": path.name, "size": st.st_size})
    return {"backups": out}


def _backup(request: Request, key: str, name: str):
    if key not in library_keys(request.app) or not NAME.match(name):
        raise HTTPException(status_code=404, detail="backup not found")
    path = next((p for p in backups(request.app.state.libraries.get(key)) if p.name == name), None)
    if path is None:
        raise HTTPException(status_code=404, detail="backup not found")
    return path


@router.get("/backups/{key}/{name}")
async def download_backup(request: Request, key: str, name: str):
    path = _backup(request, key, name)
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=f"linxiv-{key}-{name}")


@router.delete("/backups/{key}/{name}")
async def delete_backup(request: Request, key: str, name: str):
    _backup(request, key, name).unlink(missing_ok=True)
    return {"ok": True}


@router.get("/pdf-check")
async def pdf_check_report(request: Request):
    """Last "Check PDF files" result of every library that has one."""
    out = []
    for key in library_keys(request.app):
        lib = request.app.state.libraries.get(key)
        report = read_report(report_path(lib, PDF_CHECK))
        if report:
            for name in ("missing", "unlinked"):
                report[name] = (report.get(name) or [])[:MAX_LISTED]
            out.append({"library": key, **report})
    return {"libraries": out}


class PdfCheckOptionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    skip: list[str] = Field(max_length=MAX_SKIP)


@router.get("/pdf-check/options")
async def pdf_check_options(request: Request):
    """Top-level folders of the PDF folder the check skips; orphans/ always is."""
    return {"skip": skip_from(await _maint(request).stored()), "always": [ORPHANS]}


@router.put("/pdf-check/options")
async def set_pdf_check_options(request: Request, body: PdfCheckOptionsIn):
    bad = [s for s in body.skip if not valid_folder(s)]
    if bad:
        raise HTTPException(
            status_code=400, detail=f"not a folder name inside the PDF folder: {', '.join(bad)}"
        )
    skip = [s for s in dict.fromkeys(body.skip) if s != ORPHANS]
    await _maint(request).save_setting(PDF_CHECK_OPTIONS, {"skip": skip})
    return await pdf_check_options(request)


def _check_library(request: Request, key: str):
    if key not in library_keys(request.app):
        raise HTTPException(status_code=404, detail="library not found")
    return request.app.state.libraries.get(key)


@router.get("/pdf-check/{key}/unlinked.tsv")
async def pdf_check_unlinked_tsv(request: Request, key: str):
    """Every unlinked file of the library's last check (the API lists 500)."""
    report = read_report(report_path(_check_library(request, key), PDF_CHECK))
    rows = [
        (r.get("file", ""), r.get("size", ""), r.get("modified", ""))
        for r in report.get("unlinked") or []
    ]
    return tsv_response(["file", "size", "modified"], rows, f"unlinked-pdfs-{key}.tsv")


@router.get("/pdf-check/{key}/missing.tsv")
async def pdf_check_missing_tsv(request: Request, key: str):
    """Every paper of the library's last check whose PDF file is missing."""
    report = read_report(report_path(_check_library(request, key), PDF_CHECK))
    rows = [
        (r.get("source_id", ""), r.get("version", ""), r.get("title", ""))
        for r in report.get("missing") or []
    ]
    return tsv_response(["source_id", "version", "title"], rows, f"missing-pdfs-{key}.tsv")


@router.post("/pdf-check/{key}/move-orphans")
async def pdf_check_move_orphans(request: Request, key: str):
    """Move the library's unlinked PDFs to orphans/ as job `pdf-orphans`. Refused
    while any other job runs in that library or any maintenance job runs."""
    lib = _check_library(request, key)
    jobs = request.app.state.jobs
    if busy := jobs.running(None, lib.key) or jobs.running(None, ROOT):
        raise HTTPException(status_code=409, detail=f"a {busy.kind} job is running")
    app = request.app
    try:
        job = jobs.start(
            ORPHAN_KIND,
            lambda job: move_orphans(app, lib, job),
            lib.key,
            current_user(request).get("id"),
        )
    except JobBusy as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return job.public()


class FillOptionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    gaps: list[str] = Field(min_length=1, max_length=len(FILLS))
    sources: list[str] = Field(min_length=1, max_length=len(ID_SOURCES))


@router.get("/complete-metadata/options")
async def fill_options(request: Request):
    """Which gaps make a new paper incomplete, and which sources it is looked up
    in, in order. `all_gaps` / `all_sources` list every choice."""
    opts = options_from(await _maint(request).stored())
    return {**opts, "all_gaps": list(FILLS), "all_sources": list(ID_SOURCES)}


@router.put("/complete-metadata/options")
async def set_fill_options(request: Request, body: FillOptionsIn):
    bad = [g for g in body.gaps if g not in FILLS]
    bad += [s for s in body.sources if s not in ID_SOURCES]
    if bad or len(set(body.gaps)) != len(body.gaps) or len(set(body.sources)) != len(body.sources):
        raise HTTPException(status_code=400, detail=f"unknown or repeated choice: {', '.join(bad)}")
    value = {"gaps": [g for g in FILLS if g in body.gaps], "sources": body.sources}
    await _maint(request).save_setting(OPTIONS_SETTING, value)
    return await fill_options(request)
