"""arXiv TeX source for full-text search (`linxiv paper fetch-source`).

One paper is fetched in the request. The backlog runs as a background job that
calls `fetch-source` once per paper, pausing between arXiv requests, so the CLI
lock is free between papers. (`paper index-sources` would hold the lock for the
whole batch and prints progress lines before its JSON.)
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..cli import CLIError
from ..jobs import Job, JobBusy, Jobs
from .common import ident, run

router = APIRouter(prefix="/api", tags=["sources"])

KIND = "index-sources"
# linxiv's own index-sources paces arXiv fetches about 7 s apart.
PACE_SECONDS = 7.0


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


def _pending(papers: object) -> list[str]:
    """Saved arXiv papers whose TeX source isn't indexed yet."""
    if not isinstance(papers, list):
        return []
    return [
        p["source_id"]
        for p in papers
        if str(p.get("source_id", "")).startswith("arxiv:") and not p.get("downloaded_source")
    ]


@router.get("/sources/pending")
async def pending(request: Request):
    papers = await run(request, ["list"])
    arxiv = [p for p in papers or [] if str(p.get("source_id", "")).startswith("arxiv:")]
    return {"pending": len(_pending(papers)), "arxiv_papers": len(arxiv)}


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
