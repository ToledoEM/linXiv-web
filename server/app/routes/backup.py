"""Library backup (`linxiv backup / import / restore`).

Backups hold the database only (papers, metadata, projects, notes, tags...),
never PDF files. `import` merges a backup insert-only; `restore` replaces the
whole database after the CLI copies the current one to `papers.pre-restore`
(then `.pre-restore.1`, ...) beside it.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ..cli import CLIError
from .common import library, run, save_upload
from .feed import clear_feed_cache

router = APIRouter(prefix="/api", tags=["backup"])

SQLITE_MAGIC = b"SQLite format 3\x00"


@router.get("/backup")
async def download_backup(request: Request):
    """Snapshot the database into a private temp dir and send it as a download."""
    tmp = Path(tempfile.mkdtemp(prefix="lxw-backup-"))
    name = time.strftime("linxiv-backup-%Y%m%d-%H%M%S.db")
    try:
        out = await run(request, ["backup", "--", str(tmp / name)], long=True)
        path = Path(str(out.get("path", ""))).resolve() if isinstance(out, dict) else None
        if not path or not path.is_file() or not path.is_relative_to(tmp.resolve()):
            raise CLIError(502, "linxiv backup wrote no file")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return FileResponse(
        path,
        media_type="application/vnd.sqlite3",
        filename=name,
        background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True),
    )


async def _save_upload(request: Request, file: UploadFile) -> Path:
    return await save_upload(
        request, file, ".db", SQLITE_MAGIC, "not a linXiv backup (SQLite) file"
    )


def _cli_bad_file(e: CLIError) -> bool:
    msg = e.message.lower()
    return "not a valid" in msg or "backup file" in msg


@router.post("/backup/import")
async def import_backup(request: Request, file: UploadFile):
    """Insert-only merge: nothing in the library is replaced or restored from trash."""
    tmp = await _save_upload(request, file)
    try:
        out = await run(request, ["import", "--", str(tmp)], long=True)
    except CLIError as e:
        if _cli_bad_file(e):
            raise HTTPException(status_code=400, detail=e.message) from e
        raise
    finally:
        tmp.unlink(missing_ok=True)
    clear_feed_cache(request)
    return out


@router.post("/backup/restore")
async def restore_backup(request: Request, file: UploadFile):
    """Replace the whole database. Refused while a background job is running."""
    if busy := request.app.state.jobs.running(None, library(request).key):
        raise HTTPException(
            status_code=409, detail=f"a {busy.kind} job is running; cancel it or wait first"
        )
    tmp = await _save_upload(request, file)
    try:
        out = await run(request, ["restore", "--", str(tmp)], long=True)
    except CLIError as e:
        if _cli_bad_file(e):
            raise HTTPException(status_code=400, detail=e.message) from e
        if "in use" in e.message:
            raise HTTPException(status_code=409, detail=e.message) from e
        raise
    finally:
        tmp.unlink(missing_ok=True)
    clear_feed_cache(request)
    return out
