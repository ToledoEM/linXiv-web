"""App log viewer (Settings → Server & data → Logs): read, export, clear."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from .. import logs

router = APIRouter(prefix="/api", tags=["logs"])
log = logging.getLogger(__name__)
Window = Literal["1h", "24h", "7d", "30d", "all"]


def _data_dir(request: Request):
    return request.app.state.settings.data_dir


@router.get("/logs")
async def read_logs(
    request: Request, window: Window = "24h", limit: int = Query(1000, ge=1, le=5000)
):
    data_dir = _data_dir(request)
    lines, truncated = logs.read(data_dir, window, limit)
    return {
        "lines": lines,
        "truncated": truncated,
        "level": logs.level_name(),
        "files": [{"name": p.name, "size": p.stat().st_size} for p in logs.files(data_dir)],
    }


@router.get("/logs/export")
async def export_logs(request: Request, window: Window = "24h"):
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"linxiv-web-{stamp}-{window}.log"
    return StreamingResponse(
        logs.iter_window(_data_dir(request), window),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.delete("/logs")
async def clear_logs(request: Request):
    logs.clear(_data_dir(request))
    log.info("log cleared")
    return {"ok": True}
