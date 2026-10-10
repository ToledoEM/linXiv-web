"""PDF download, viewing, deletion and upload/import."""

from __future__ import annotations

import asyncio
import os
import random
import re
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ..jobs import JobBusy
from ..pdf_layout import Layout, PdfLayout, apply, storage_bytes
from .common import ident, run, settings

router = APIRouter(prefix="/api", tags=["pdfs"])

_ARXIV_NEW = re.compile(r"^\d{4}\.\d{4,5}$")
_ARXIV_OLD = re.compile(r"^[a-z\-]+(\.[A-Z]{2})?/\d{7}$")
_CHUNK = 1024 * 1024


def _inside(path: Path, roots: list[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(r.resolve()) for r in roots)


def pdf_url_for(paper: dict) -> str | None:
    """Download URL for a stored paper (`paper get` JSON).

    arXiv papers store the versioned PDF link in `url`; other sources only when
    `url` points at a .pdf. Otherwise the caller must supply one.
    """
    url = paper.get("url")
    if (
        isinstance(url, str)
        and url.startswith(("http://", "https://"))
        and (paper.get("source") == "arxiv" or url.lower().endswith(".pdf"))
    ):
        return url
    if paper.get("source") == "arxiv":
        sid = str(paper.get("source_id", "")).removeprefix("arxiv:")
        if _ARXIV_NEW.match(sid) or _ARXIV_OLD.match(sid):
            version = paper.get("version")
            return f"https://arxiv.org/pdf/{sid}" + (f"v{version}" if version else "")
    return None


async def managed_pdf_path(request: Request, source_id: str, version: int | None = None) -> Path:
    """The saved PDF of a paper (`pdf path`), checked to be a file inside the
    data or PDF dir."""
    args = ["pdf", "path"]
    if version:
        args += ["--version", str(version)]
    loc = await run(request, [*args, "--", ident(source_id)])
    raw = loc.get("path") if isinstance(loc, dict) else None
    if not raw:
        raise HTTPException(status_code=404, detail="no PDF saved for this paper")
    path = Path(raw)
    s = settings(request)
    if not _inside(path, [s.data_dir, s.pdf_dir]):
        raise HTTPException(status_code=403, detail="PDF is outside managed storage")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="PDF file missing on disk")
    return path


@router.get("/papers/{source_id:path}/pdf")
async def view_pdf(request: Request, source_id: str, version: int | None = None):
    path = await managed_pdf_path(request, source_id, version)
    return FileResponse(
        path, media_type="application/pdf", filename=path.name, content_disposition_type="inline"
    )


class DownloadBody(BaseModel):
    url: str | None = Field(default=None, max_length=2048)
    version: int | None = Field(default=None, ge=1)


@router.post("/papers/{source_id:path}/pdf")
async def download_pdf(request: Request, source_id: str, body: DownloadBody | None = None):
    sid = ident(source_id)
    body = body or DownloadBody()
    url = body.url
    if not url:
        paper = await run(request, ["paper", "get", "--", sid])
        url = pdf_url_for(paper if isinstance(paper, dict) else {})
        if not url:
            raise HTTPException(status_code=400, detail="no known PDF URL, pass one in 'url'")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="url must be http(s)")
    args = ["pdf", "download"]
    if body.version:
        args += ["--version", str(body.version)]
    return await run(request, [*args, "--", sid, url], long=True)


@router.delete("/papers/{source_id:path}/pdf")
async def delete_pdf(request: Request, source_id: str):
    return await run(request, ["pdf", "delete", "--", ident(source_id)])


@router.get("/pdfs")
async def list_pdfs(
    request: Request,
    view: Literal["all", "random", "size", "untagged"] = "all",
    limit: int | None = Query(None, ge=10, le=100),
):
    """Saved PDFs (`pdf list`). `view` picks a slice for Home: a random sample,
    the largest files, or papers with no tags; `limit` caps it (default 10).
    `all` without a limit returns everything, as before."""
    out = await run(request, ["pdf", "list"])
    if view == "all" and limit is None:
        return out
    pdfs = [p for p in (out or {}).get("pdfs") or [] if isinstance(p, dict)]
    n = limit or 10
    if view == "random":
        pdfs = random.sample(pdfs, min(n, len(pdfs)))
    elif view == "size":
        pdfs.sort(key=lambda p: p.get("size_bytes") or 0, reverse=True)
    elif view == "untagged":
        papers = await run(request, ["list", "--sort", "added"])
        tagged = {p.get("source_id") for p in papers or [] if isinstance(p, dict) and p.get("tags")}
        pdfs = [p for p in pdfs if p.get("source_id") not in tagged]
    return {**out, "pdfs": pdfs[:n], "total": len(out.get("pdfs") or [])}


@router.get("/pdfs/storage")
async def storage(request: Request):
    """linXiv's report, with the total recounted to include PDFs filed into
    subfolders (linXiv itself only counts the top level)."""
    out = await run(request, ["pdf", "storage"])
    total = await asyncio.to_thread(storage_bytes, settings(request).pdf_dir)
    if isinstance(out, dict):
        out = {**out, "storage_mb": total / (1024 * 1024)}
    return out


# --- Folder layout (pdf_layout.py) ------------------------------------------
LAYOUT_KIND = "pdf-layout"
LAYOUT_SETTING = "web_pdf_folder_layout"


def _layout_tool(request: Request) -> PdfLayout:
    s = settings(request)
    # PDF_PATH values are written the way linXiv sees the folder: <data dir>/pdfs/...
    return PdfLayout(s.data_dir / "papers.db", s.data_dir / "pdfs")


class LayoutBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    layout: Layout


@router.get("/pdfs/layout/preview")
async def layout_preview(request: Request, layout: Layout):
    tool = _layout_tool(request)
    plan = await asyncio.to_thread(tool.plan, layout)
    return tool.summary(plan)


@router.post("/jobs/pdf-layout")
async def start_layout(request: Request, body: LayoutBody):
    """Move saved PDFs into the chosen subfolder layout (`none` = flat). Refused while
    another background job runs; each move holds the CLI lock."""
    jobs = request.app.state.jobs
    if busy := next((j for j in jobs.list() if j.state == "running"), None):
        raise HTTPException(
            status_code=409, detail=f"a {busy.kind} job is running; wait for it first"
        )
    tool = _layout_tool(request)
    cli = request.app.state.cli
    timeout = settings(request).timeout_short

    async def work(job):
        await apply(tool, body.layout, job, getattr(cli, "_lock", None))
        if not job.result.get("failed") and not job.cancel_requested:
            await cli(["settings", "update", "--", LAYOUT_SETTING, body.layout], timeout)

    try:
        job = jobs.start(LAYOUT_KIND, work)
    except JobBusy as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return job.public()


@router.post("/pdfs/import")
async def import_pdf(request: Request, file: UploadFile):
    limit = settings(request).max_upload_mb * 1024 * 1024
    fd, tmp = tempfile.mkstemp(prefix="linxiv-web-", suffix=".pdf")
    try:
        size = 0
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(_CHUNK):
                if size == 0 and not chunk.startswith(b"%PDF-"):
                    raise HTTPException(status_code=400, detail="not a PDF file")
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail="file too large")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="empty file")
        return await run(request, ["pdf", "import", "--", tmp], long=True)
    finally:
        Path(tmp).unlink(missing_ok=True)
