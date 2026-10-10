"""Activity log viewer (Settings → Server & data → Activity): read, CSV export, clear."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from .. import activity

router = APIRouter(prefix="/api", tags=["activity"])


def _data_dir(request: Request):
    return request.app.state.settings.data_dir


@router.get("/activity")
async def read_activity(request: Request, limit: int = Query(200, ge=1, le=5000)):
    return {"events": activity.read(_data_dir(request), limit)}


@router.get("/activity/export")
async def export_activity(request: Request):
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    body = activity.to_csv(activity.read(_data_dir(request), 1_000_000))
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="linxiv-web-activity-{stamp}.csv"'},
    )


class ClearRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    confirm: str


@router.delete("/activity")
async def clear_activity(request: Request, body: ClearRequest):
    if body.confirm != activity.CLEAR_PHRASE:
        raise HTTPException(status_code=400, detail=f'type "{activity.CLEAR_PHRASE}" to confirm')
    activity.clear(_data_dir(request))
    # The middleware then records this DELETE: a wiped log shows who wiped it.
    return {"ok": True}
