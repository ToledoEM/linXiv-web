from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

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
