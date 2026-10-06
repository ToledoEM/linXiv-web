from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, UploadFile

from ..cli import Runner
from ..settings import Settings


def runner(request: Request) -> Runner:
    return request.app.state.cli


def settings(request: Request) -> Settings:
    return request.app.state.settings


def ident(value: str, what: str = "id") -> str:
    """Validate a user-supplied CLI positional (paper id, tag, query).

    Values always follow `--` in the argv, so this only rejects what can't be a
    real id: empty, oversized, or carrying control characters.
    """
    value = value.strip()
    if not value or len(value) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise HTTPException(status_code=400, detail=f"invalid {what}")
    return value


async def run(request: Request, args: list[str], long: bool = False, raw: bool = False) -> Any:
    s = settings(request)
    return await runner(request)(args, s.timeout_long if long else s.timeout_short, raw=raw)


_CHUNK = 1024 * 1024


async def save_upload(
    request: Request, file: UploadFile, suffix: str, magic: bytes, bad_type: str
) -> Path:
    """Stream an upload to a temp file, capped at `max_upload_mb`, and require it
    to start with `magic`. The caller unlinks the returned path."""
    limit = settings(request).max_upload_mb * 1024 * 1024
    fd, name = tempfile.mkstemp(prefix="lxw-upload-", suffix=suffix)
    tmp = Path(name)
    try:
        size = 0
        head = b""
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail="file too large")
                if len(head) < len(magic):
                    head += chunk[: len(magic) - len(head)]
                out.write(chunk)
        if head != magic:
            raise HTTPException(status_code=400, detail=bad_type)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp
