"""Copy papers from the shared library into the caller's own (multi-user mode).

linXiv has no cross-library copy, so this goes through a project archive, the
same way a user would by hand: a temporary project in the shared library holds
the papers, `project export --pdfs` bundles them with their PDFs, notes and
highlights, and `project import --on-conflict=merge` brings them in (papers
already in the caller's library keep their stored metadata). Both temporary
projects are deleted afterwards; the papers stay.
"""

from __future__ import annotations

import logging
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import current_user
from ..cli import CLIError
from ..libraries import SHARED, Library
from .common import ident, settings
from .projects import _check_lxproj

router = APIRouter(prefix="/api", tags=["shared"])
log = logging.getLogger(__name__)

PaperId = Annotated[str, Field(min_length=1, max_length=512)]


class CopyBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_ids: list[PaperId] = Field(min_length=1, max_length=500)


async def _drop_project(lib: Library, project_id: int, timeout: float) -> None:
    """Soft delete, then purge, a temporary project. Its papers stay."""
    for args in (["project", "delete"], ["trash", "hard-delete-project"]):
        try:
            await lib.cli([*args, "--", str(project_id)], timeout)
        except CLIError as e:
            log.warning("library %s: temp project %d not removed: %s", lib.key, project_id, e)
            return


@router.post("/shared/copy")
async def copy_from_shared(request: Request, body: CopyBody):
    if not request.app.state.auth.multi_user():
        raise HTTPException(status_code=409, detail="multi-user mode is off")
    libraries = request.app.state.libraries
    src = libraries.get(SHARED)
    dst = libraries.get(current_user(request)["library"])
    ids = list(dict.fromkeys(ident(s, "paper id") for s in body.source_ids))
    s = settings(request)
    name = f"lxw-copy-{secrets.token_hex(4)}"
    project = await src.cli(["project", "create", "--description=", "--", name], s.timeout_short)
    src_pid = int(project["id"])
    tmp = Path(tempfile.mkdtemp(prefix="lxw-copy-"))
    try:
        added = await src.cli(["project", "add-papers", "--", str(src_pid), *ids], s.timeout_short)
        added = added if isinstance(added, dict) else {}
        if not added.get("added"):
            raise HTTPException(
                status_code=404, detail="none of these papers is in the shared library"
            )
        out = await src.cli(
            ["project", "export", "--pdfs", "--", str(src_pid), str(tmp / "copy.lxproj")],
            s.timeout_long,
        )
        path = Path(str(out.get("path", ""))).resolve() if isinstance(out, dict) else None
        if not path or not path.is_file() or not path.is_relative_to(tmp.resolve()):
            raise CLIError(502, "linxiv export wrote no file")
        _check_lxproj(path, 4 * s.max_upload_mb * 1024 * 1024)
        res = await dst.cli(
            ["project", "import", "--on-conflict=merge", "--", str(path)], s.timeout_long
        )
        res = res if isinstance(res, dict) else {}
        if isinstance(res.get("project_id"), int):
            await _drop_project(dst, res["project_id"], s.timeout_short)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        await _drop_project(src, src_pid, s.timeout_short)
    return {
        "copied": list(added.get("added") or []),
        "failed": list(added.get("failed") or []),
        "skipped_pdfs": list(res.get("skipped_pdfs") or []),
    }
