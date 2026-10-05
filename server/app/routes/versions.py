"""arXiv new-version monitor (`linxiv versions ...`).

`versions check` polls arXiv for the stalest saved arXiv papers and stores any
newer version it finds; `versions new` lists those flagged papers until each is
acknowledged.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ..cli import CLIError
from .common import ident, run

router = APIRouter(prefix="/api", tags=["versions"])


class CheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    limit: int = Field(20, ge=1, le=100)


@router.get("/versions/new")
async def new_versions(request: Request):
    return await run(request, ["versions", "new"])


@router.post("/versions/check")
async def check_versions(request: Request, body: CheckBody | None = None):
    limit = (body or CheckBody()).limit
    return await run(request, ["versions", "check", f"--limit={limit}"], long=True)


@router.post("/versions/{source_id:path}/ack")
async def ack_version(request: Request, source_id: str):
    sid = ident(source_id, "paper id")
    try:
        return await run(request, ["versions", "ack", "--", sid])
    except CLIError as e:
        # Dismissing twice (or from a stale list) is not an error for the UI.
        if "no new version flagged" in e.message:
            return {"ok": True, "already_acknowledged": True}
        raise
