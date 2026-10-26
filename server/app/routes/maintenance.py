"""Settings → Server Admin → Maintenance operations (admins only)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import current_user
from ..jobs import JobBusy
from ..maintenance import Maintenance

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    hour: int = Field(ge=0, le=23)
    nightly: list[str] = Field(max_length=50)


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
    return await m.set_schedule(body.hour, body.nightly)


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
