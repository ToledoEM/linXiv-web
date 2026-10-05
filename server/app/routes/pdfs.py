"""PDF download, viewing, deletion and upload/import."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

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


@router.get("/papers/{source_id:path}/pdf")
async def view_pdf(request: Request, source_id: str, version: int | None = None):
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
async def list_pdfs(request: Request):
    return await run(request, ["pdf", "list"])


@router.get("/pdfs/storage")
async def storage(request: Request):
    return await run(request, ["pdf", "storage"])


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
