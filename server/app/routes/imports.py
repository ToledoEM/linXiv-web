"""Bulk import from BibTeX (.bib) and Zotero CSL JSON files."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

from .common import run, settings

router = APIRouter(prefix="/api", tags=["import"])

_CHUNK = 1024 * 1024


def _check_bibtex(data: bytes) -> None:
    if b"@" not in data:
        raise HTTPException(status_code=400, detail="no BibTeX entries (@type{...}) found")


def _check_csl_json(data: bytes) -> None:
    try:
        items = json.loads(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="not valid JSON") from e
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="CSL JSON must be an array of items")


async def _import(
    request: Request, file: UploadFile, cmd: str, suffix: str, check: Callable[[bytes], None]
):
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
    fd, tmp = tempfile.mkstemp(prefix="linxiv-web-", suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        return await run(request, [cmd, "import", "--", tmp], long=True)
    finally:
        Path(tmp).unlink(missing_ok=True)


@router.post("/import/bibtex")
async def import_bibtex(request: Request, file: UploadFile):
    return await _import(request, file, "bibtex", ".bib", _check_bibtex)


@router.post("/import/zotero")
async def import_zotero(request: Request, file: UploadFile):
    return await _import(request, file, "zotero", ".json", _check_csl_json)
