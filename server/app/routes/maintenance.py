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
    Maintenance,
    library_keys,
    read_report,
    report_path,
)
from ..metadata_fill import FILLS, OPTIONS_SETTING, options_from
from ..pdf_check import REPORT as PDF_CHECK
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
            out.append({"library": key, **report})
    return {"libraries": out}


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
