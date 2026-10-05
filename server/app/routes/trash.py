"""Soft-deleted papers and projects (`linxiv trash ...`)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..cli import CLIError
from .common import ident, run

router = APIRouter(prefix="/api", tags=["trash"])


async def _trashed_ids(request: Request) -> set[str]:
    listing = await run(request, ["trash", "list"])
    papers = listing.get("papers", []) if isinstance(listing, dict) else []
    return {p.get("source_id") for p in papers}


@router.get("/trash")
async def list_trash(request: Request):
    return await run(request, ["trash", "list"])


# Suffixed route before the bare {source_id:path} one, as in library.py.
@router.post("/trash/papers/{source_id:path}/restore")
async def restore_paper(request: Request, source_id: str):
    return await run(request, ["trash", "restore", "--", ident(source_id)])


@router.delete("/trash/papers/{source_id:path}")
async def hard_delete_paper(request: Request, source_id: str):
    sid = ident(source_id)
    if sid not in await _trashed_ids(request):
        raise HTTPException(status_code=404, detail=f"Paper {sid} is not in the trash")
    try:
        return await run(request, ["trash", "hard-delete", "--", sid])
    except CLIError as e:
        # linxiv v0.6.0 deletes the paper, then reports "not found" and exits 1.
        # It was in the trash a moment ago; if it's gone now, the delete worked.
        if e.status == 404 and sid not in await _trashed_ids(request):
            return {"ok": True, "hard_deleted": sid}
        raise


@router.post("/trash/projects/{project_id}/restore")
async def restore_project(request: Request, project_id: int):
    return await run(request, ["trash", "restore-project", "--", str(project_id)])


@router.delete("/trash/projects/{project_id}")
async def hard_delete_project(request: Request, project_id: int):
    return await run(request, ["trash", "hard-delete-project", "--", str(project_id)])
