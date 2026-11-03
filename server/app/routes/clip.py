"""Imports from the browser add-on, and the token it uses.

`endpoint` is authenticated by a per-account bearer token, not the browser session:
an add-on's `moz-extension://` origin fails the session guard, and it holds no
cookie or CSRF token. It always works on the token owner's own library, whatever
`X-Linxiv-Library` says. `router` (session guarded) manages the token and tells the
web UI which project is the list.

A clip never changes a stored record: a paper already in the library only joins
the list. `pdf import` would repoint its PDF, or replace its metadata when it has
no PDF yet, and the paper's id is only known after an import, so a PDF is first
imported into a throwaway library to learn the id.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from .. import bib_parse, clip_list
from ..auth import current_user
from ..cli import CLIError
from ..doi import doi_or_none
from ..libraries import ROOT
from .common import ident, run, save_upload, settings
from .imports import check_bibtex, import_text, no_version, read_upload
from .metadata import MetadataIn, repair_args

log = logging.getLogger(__name__)

_trial_slot = asyncio.Semaphore(1)


def require_clip_token(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and urlparse(origin).scheme != "moz-extension":
        raise HTTPException(status_code=403, detail="cross-origin request rejected")
    auth = request.app.state.auth
    if auth.setup_required:
        raise HTTPException(status_code=403, detail="first-run setup required")
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    user = auth.clip_identity(token.strip()) if scheme.lower() == "bearer" else None
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid clip token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.user = user
    # Set here so `library_key` never reads the shared-library header: the rule that
    # keeps non-admins out of the shared library lives in the session guard.
    request.state.library_key = user.get("library") or ROOT


router = APIRouter(prefix="/api/clip", tags=["clip"])
endpoint = APIRouter(prefix="/api/clip", tags=["clip"], dependencies=[Depends(require_clip_token)])


# --- token and list (browser, session) --------------------------------------


def _own_library(request: Request) -> str:
    return current_user(request).get("library") or ROOT


@router.get("/token")
async def token_status(request: Request):
    found = request.app.state.auth.clip_token_status(_own_library(request))
    return {"set": bool(found), **(found or {"hint": None, "created": None})}


@router.post("/token")
async def create_token(request: Request):
    """New token, returned this once; replaces any previous one."""
    return request.app.state.auth.create_clip_token(_own_library(request))


@router.delete("/token")
async def revoke_token(request: Request):
    request.app.state.auth.revoke_clip_token(_own_library(request))
    return {"ok": True}


@router.get("/list")
async def list_id(request: Request):
    """Which project is this library's list. Read only: clips create it."""
    return {"project_id": await clip_list.stored_id(request)}


# --- imports (add-on, bearer) -----------------------------------------------


@endpoint.get("/ping")
async def ping(request: Request):
    return {
        "ok": True,
        "version": request.app.version,
        "username": current_user(request).get("username"),
    }


async def _paper(request: Request, sid: str) -> dict | None:
    """The live record, None when there is none: a trashed paper counts as none, and
    importing it again restores it."""
    try:
        paper = await run(request, ["paper", "get", "--", ident(sid, "paper id")])
    except CLIError as e:
        if e.status == 404:
            return None
        raise
    return paper if isinstance(paper, dict) else None


async def _trial_id(request: Request, pdf: Path) -> str:
    """The id this PDF gets, from an import into a throwaway library."""
    timeout = settings(request).timeout_long
    async with _trial_slot:
        with tempfile.TemporaryDirectory(prefix="linxiv-web-clip-") as scratch:
            cli = request.app.state.scratch_cli("clip-trial", Path(scratch))
            out = await cli(["pdf", "import", "--", str(pdf)], timeout)
    return out["source_id"]


async def _restore(request: Request, paper: dict) -> bool:
    """Put a record's metadata back after `pdf import` replaced it."""
    # Built without validation: this writes back what is stored, as it is stored.
    body = MetadataIn.model_construct(
        title=paper.get("title") or "",
        authors=paper.get("authors") or [],
        published=paper.get("published") or "",
        summary=paper.get("summary") or "",
        category=paper.get("category"),
        doi=paper.get("doi"),
        url=paper.get("url"),
    )
    sid = paper["source_id"]
    try:
        await run(request, repair_args(sid, body, paper.get("tags") or []))
    except CLIError:
        log.exception("could not restore the metadata of %s", sid)
        return False
    return True


async def _join_list(request: Request, source_ids: list[str]) -> dict[str, Any]:
    """Add to the list. The import already worked, so a failure here is only reported."""
    if not source_ids:
        return {"project_id": None, "failed": []}
    try:
        project_id = await clip_list.resolve(request)
        out = await run(request, ["project", "add-papers", "--", str(project_id), *source_ids])
    except (CLIError, KeyError, TypeError, ValueError):
        log.exception("could not add clipped papers to the list")
        return {"project_id": None, "failed": source_ids}
    failed = out.get("failed") if isinstance(out, dict) else None
    return {"project_id": project_id, "failed": failed or []}


@endpoint.post("/pdf")
async def clip_pdf(request: Request, file: UploadFile):
    tmp = await save_upload(request, file, ".pdf", b"%PDF-", "not a PDF file")
    try:
        sid = await _trial_id(request, tmp)
        stored = await _paper(request, sid)
        pdf_path = (stored or {}).get("pdf_path")
        if stored and pdf_path and Path(pdf_path).is_file():
            result: dict[str, Any] = {"new": [], "existing": [sid], "attached": []}
        else:
            out = await run(request, ["pdf", "import", "--", str(tmp)], long=True)
            sid = out["source_id"]
            if stored is None:
                result = {"new": [sid], "existing": [], "attached": []}
            else:
                result = {"new": [], "existing": [sid], "attached": [sid]}
                result["metadata_kept"] = await _restore(request, stored)
    finally:
        tmp.unlink(missing_ok=True)
    return {"source_ids": [sid], **result, **await _join_list(request, [sid])}


def _known_id(entry: dict, by_doi: dict, by_arxiv: dict, by_title: dict) -> str | None:
    """The library paper a BibTeX entry is, by DOI, arXiv id, else exact title."""
    f = entry["fields"]
    doi = doi_or_none(f.get("doi"))
    if doi and doi.lower() in by_doi:
        return by_doi[doi.lower()]
    key = entry["key"]
    arxiv = key[6:] if key.lower().startswith("arxiv:") else None
    if not arxiv and f.get("eprint") and (f.get("archiveprefix") or "").lower() in ("arxiv", ""):
        arxiv = f["eprint"]
    if arxiv and no_version(arxiv) in by_arxiv:
        return by_arxiv[no_version(arxiv)]
    return by_title.get(bib_parse.norm_title(f.get("title")) or None)


@endpoint.post("/bibtex")
async def clip_bibtex(request: Request, file: UploadFile):
    data = await read_upload(request, file, check_bibtex)
    text = data.decode("utf-8")
    listed = await run(request, ["list"])
    papers = [p for p in listed or [] if isinstance(p, dict)]
    by_doi = {d.lower(): p["source_id"] for p in papers if (d := doi_or_none(p.get("doi")))}
    by_arxiv = {
        no_version(p["source_id"][6:]): p["source_id"]
        for p in papers
        if str(p.get("source_id")).startswith("arxiv:")
    }
    by_title = {t: p["source_id"] for p in papers if (t := bib_parse.norm_title(p.get("title")))}

    entries = bib_parse.spans(text)
    existing: list[str] = []
    keep: list[str] = []
    pos = 0
    kept = 0
    for entry in entries:
        sid = _known_id(entry, by_doi, by_arxiv, by_title)
        if sid is None:
            kept += 1
            continue
        if sid not in existing:
            existing.append(sid)
        # Cut only known entries, so @string and @comment stay for the rest.
        keep.append(text[pos : entry["start"]])
        pos = entry["end"]
    keep.append(text[pos:])

    new: list[str] = []
    # An unparsable file goes to the CLI whole, for its own error.
    if kept or not entries:
        out = await import_text(
            request, "".join(keep).encode("utf-8"), "bibtex", ".bib", overwrite_bib=False
        )
        imported = (out or {}).get("source_ids") if isinstance(out, dict) else None
        known = {p["source_id"] for p in papers}
        for sid in imported or []:
            if sid in known:
                if sid not in existing:
                    existing.append(sid)
            elif sid not in new:
                new.append(sid)
    source_ids = [*new, *existing]
    return {
        "source_ids": source_ids,
        "new": new,
        "existing": existing,
        **await _join_list(request, source_ids),
    }
