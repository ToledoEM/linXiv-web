"""Bulk import from BibTeX (.bib) and Zotero CSL JSON files.

linXiv drops the BibTeX fields it has no column for (volume, pages,
publisher...); after a .bib import they are read from the file and stored per
imported paper (app/bib_store.py, source `bibtex`), matched by DOI, arXiv id,
else exact title."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

from .. import bib_parse, bib_store
from ..doi import doi_or_none
from .common import library, run, settings

router = APIRouter(prefix="/api", tags=["import"])
log = logging.getLogger(__name__)

_CHUNK = 1024 * 1024


def check_bibtex(data: bytes) -> None:
    if b"@" not in data:
        raise HTTPException(status_code=400, detail="no BibTeX entries (@type{...}) found")


def _check_csl_json(data: bytes) -> None:
    try:
        items = json.loads(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="not valid JSON") from e
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="CSL JSON must be an array of items")


async def read_upload(request: Request, file: UploadFile, check: Callable[[bytes], None]) -> bytes:
    """The whole uploaded text file, capped at `max_upload_mb`, UTF-8 and passing `check`."""
    limit = settings(request).max_upload_mb * 1024 * 1024
    buf = bytearray()
    while chunk := await file.read(_CHUNK):
        buf += chunk
        if len(buf) > limit:
            raise HTTPException(status_code=413, detail="file too large")
    data = bytes(buf)
    if not data.strip():
        raise HTTPException(status_code=400, detail="empty file")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail="file is not UTF-8 text") from e
    check(data)
    return data


async def import_text(
    request: Request, data: bytes, cmd: str, suffix: str, overwrite_bib: bool = True
):
    """Run `<cmd> import` on the text; a BibTeX import then stores its extra fields."""
    fd, tmp = tempfile.mkstemp(prefix="linxiv-web-", suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        result = await run(request, [cmd, "import", "--", tmp], long=True)
    finally:
        Path(tmp).unlink(missing_ok=True)
    if cmd == "bibtex":
        try:
            await _store_bib_fields(request, data.decode("utf-8"), result, overwrite_bib)
        except Exception:  # the import itself worked
            log.exception("could not store BibTeX fields of the import")
    return result


async def _import(
    request: Request, file: UploadFile, cmd: str, suffix: str, check: Callable[[bytes], None]
):
    return await import_text(request, await read_upload(request, file, check), cmd, suffix)


def no_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id.strip())


async def _store_bib_fields(request: Request, text: str, result, overwrite: bool = True) -> None:
    sids = [s for s in (result or {}).get("source_ids") or [] if isinstance(s, str)]
    found = [e for e in bib_parse.entries(text) if e.get("fields")]
    if not sids or not found:
        return
    by_doi = {d.lower(): e for e in found if (d := doi_or_none(e["fields"].get("doi")))}
    by_arxiv = {}
    for e in found:
        f = e["fields"]
        if f.get("eprint") and (f.get("archiveprefix") or "").lower() in ("arxiv", ""):
            by_arxiv[no_version(f["eprint"])] = e
    by_title = {t: e for e in found if (t := bib_parse.norm_title(e["fields"].get("title")))}
    lib = library(request)
    unmatched = []
    for sid in sids:
        e = None
        if sid.startswith("doi:"):
            e = by_doi.get(sid[4:].lower())
        elif sid.startswith("arxiv:"):
            e = by_arxiv.get(no_version(sid[6:]))
        if e is None:
            unmatched.append(sid)
            continue
        await bib_store.upsert(lib, sid, bib_parse.bib_fields(e), "bibtex", sid, overwrite)
    if not unmatched:
        return
    papers = await run(request, ["list"])
    titles = {
        p.get("source_id"): bib_parse.norm_title(p.get("title"))
        for p in papers or []
        if isinstance(p, dict)
    }
    for sid in unmatched:
        e = by_title.get(titles.get(sid) or "")
        if e is not None:
            await bib_store.upsert(lib, sid, bib_parse.bib_fields(e), "bibtex", sid, overwrite)


@router.post("/import/bibtex")
async def import_bibtex(request: Request, file: UploadFile):
    return await _import(request, file, "bibtex", ".bib", check_bibtex)


@router.post("/import/zotero")
async def import_zotero(request: Request, file: UploadFile):
    return await _import(request, file, "zotero", ".json", _check_csl_json)
