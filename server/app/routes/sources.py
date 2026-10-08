"""Full-text search sources.

arXiv TeX source (`linxiv paper fetch-source`): one paper is fetched in the
request. The backlog runs as a background job that calls `fetch-source` once per
paper, pausing between arXiv requests, so the CLI lock is free between papers.
(`paper index-sources` would hold the lock for the whole batch and prints
progress lines before its JSON.)

PDF text (`linxiv paper set-text`, linXiv v0.7.0+): for papers arXiv has no TeX
for, the server extracts the saved PDF's text and stores it, per paper or as a
job over every non-arXiv paper with a PDF and no indexed text.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..cli import CLIError
from ..jobs import Job, JobBusy, Jobs
from ..pdf_text import PdfTextError, extract_text
from .common import ident, run
from .pdfs import _inside

router = APIRouter(prefix="/api", tags=["sources"])

KIND = "index-sources"
# linxiv's own index-sources paces arXiv fetches about 7 s apart.
PACE_SECONDS = 7.0

PDF_KIND = "index-pdf-text"
# Indexing wants the whole paper, unlike the AI summary's prompt-sized excerpt.
PDF_MAX_PAGES = 500
PDF_MAX_CHARS = 2_000_000


def jobs(request: Request) -> Jobs:
    return request.app.state.jobs


def _not_arxiv(e: CLIError) -> bool:
    return "only published by arXiv" in e.message


class FetchBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    force: bool = False


class IndexBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    limit: int = Field(25, ge=1, le=500)


@router.post("/papers/{source_id:path}/source")
async def fetch_source(request: Request, source_id: str, body: FetchBody | None = None):
    args = ["paper", "fetch-source"]
    if body and body.force:
        args.append("--force")
    try:
        return await run(request, [*args, "--", ident(source_id, "paper id")], long=True)
    except CLIError as e:
        if _not_arxiv(e):
            raise HTTPException(status_code=400, detail=e.message) from e
        raise


class PdfTextFailed(Exception):
    """A paper whose PDF can't be indexed (no PDF, unreadable, no text layer)."""


async def index_pdf_text(app: FastAPI, source_id: str) -> dict:
    """Extract the saved PDF's text and store it with `paper set-text`.
    Returns the CLI receipt plus `truncated`."""
    s = app.state.settings
    cli = app.state.cli
    loc = await cli(["pdf", "path", "--", source_id], s.timeout_short)
    raw = loc.get("path") if isinstance(loc, dict) else None
    if not raw:
        raise PdfTextFailed("no PDF saved for this paper")
    path = Path(raw)
    if not _inside(path, [s.data_dir, s.pdf_dir]) or not path.is_file():
        raise PdfTextFailed("PDF file missing on disk")
    try:
        text, truncated = await asyncio.to_thread(extract_text, path, PDF_MAX_PAGES, PDF_MAX_CHARS)
    except PdfTextError as e:
        raise PdfTextFailed(str(e)) from e
    if not text.strip():
        raise PdfTextFailed("the PDF has no text layer (scanned?)")
    # The text goes through a temp file: argv is capped at 128 KiB per string.
    fd, name = tempfile.mkstemp(prefix="lxw-text-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        receipt = await cli(["paper", "set-text", "--", source_id, name], s.timeout_long)
    finally:
        Path(name).unlink(missing_ok=True)
    out = receipt if isinstance(receipt, dict) else {}
    return {**out, "truncated": truncated}


@router.post("/papers/{source_id:path}/pdf-text")
async def pdf_text(request: Request, source_id: str):
    """Index one paper's PDF text for full-text search (replaces stored text)."""
    try:
        return await index_pdf_text(request.app, ident(source_id, "paper id"))
    except PdfTextFailed as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _pdf_pending(papers: object) -> list[str]:
    """Non-arXiv papers with a saved PDF and no indexed text."""
    if not isinstance(papers, list):
        return []
    return [
        p["source_id"]
        for p in papers
        if not str(p.get("source_id", "")).startswith("arxiv:")
        and p.get("has_pdf")
        and not p.get("downloaded_source")
    ]


def _pending(papers: object) -> list[str]:
    """Saved arXiv papers whose TeX source isn't indexed yet."""
    if not isinstance(papers, list):
        return []
    return [
        p["source_id"]
        for p in papers
        if str(p.get("source_id", "")).startswith("arxiv:") and not p.get("downloaded_source")
    ]


@router.get("/sources/worker")
async def worker_status(request: Request):
    """Background indexer (Settings toggle `full_text_worker_enabled`): session counters."""
    return request.app.state.fulltext_worker.public()


@router.get("/sources/pending")
async def pending(request: Request):
    papers = await run(request, ["list"])
    arxiv = [p for p in papers or [] if str(p.get("source_id", "")).startswith("arxiv:")]
    return {
        "pending": len(_pending(papers)),
        "arxiv_papers": len(arxiv),
        "pdf_pending": len(_pdf_pending(papers)),
    }


async def _index(app: FastAPI, job: Job, limit: int) -> None:
    timeout = app.state.settings.timeout_long
    cli = app.state.cli
    todo = _pending(await cli(["list"], timeout))[:limit]
    job.total = len(todo)
    job.result = {"indexed": 0, "skipped": 0, "failed": 0}
    for i, sid in enumerate(todo):
        if i:
            job.current = None
            await _pause(job)
        if job.cancel_requested:
            return
        job.current = sid
        try:
            out = await cli(["paper", "fetch-source", "--", sid], timeout)
            # indexed false: e.g. a PDF-only submission with no .tex to index
            key = "indexed" if isinstance(out, dict) and out.get("indexed") else "skipped"
            job.result[key] += 1
        except CLIError as e:
            job.result["failed"] += 1
            job.errors.append({"source_id": sid, "error": e.message})
        job.done = i + 1


async def _pause(job: Job) -> None:
    """Wait PACE_SECONDS between arXiv requests, waking early on cancel."""
    loop = asyncio.get_running_loop()
    end = loop.time() + PACE_SECONDS
    while not job.cancel_requested and (left := end - loop.time()) > 0:
        await asyncio.sleep(min(0.5, left))


@router.post("/jobs/index-sources")
async def start_index(request: Request, body: IndexBody | None = None):
    limit = (body or IndexBody()).limit
    app = request.app
    try:
        job = jobs(request).start(KIND, lambda j: _index(app, j, limit))
    except JobBusy as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return job.public()


async def _index_pdfs(app: FastAPI, job: Job) -> None:
    todo = _pdf_pending(await app.state.cli(["list"], app.state.settings.timeout_long))
    job.total = len(todo)
    job.result = {"indexed": 0, "failed": 0}
    for i, sid in enumerate(todo):
        if job.cancel_requested:
            return
        job.current = sid
        try:
            await index_pdf_text(app, sid)
            job.result["indexed"] += 1
        except (PdfTextFailed, CLIError) as e:
            job.result["failed"] += 1
            job.errors.append({"source_id": sid, "error": getattr(e, "message", str(e))})
        job.done = i + 1


@router.post("/jobs/index-pdf-text")
async def start_pdf_index(request: Request):
    app = request.app
    try:
        job = jobs(request).start(PDF_KIND, lambda j: _index_pdfs(app, j))
    except JobBusy as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return job.public()


@router.get("/jobs")
async def list_jobs(request: Request, kind: str | None = None):
    return [j.public() for j in jobs(request).list(kind)]


@router.get("/jobs/{job_id}")
async def get_job(request: Request, job_id: int):
    job = jobs(request).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job.public()


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(request: Request, job_id: int):
    job = jobs(request).cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job.public()
