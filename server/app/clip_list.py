"""The automatic reading list add-on imports land in, one per library.

Found by the project id kept in that library's settings, so renaming it changes
nothing. A list that was deleted or archived is replaced by a new one on the next clip.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import Request

from .cli import CLIError
from .libraries import library
from .settings import Settings

SETTING = "web_clip_list_id"
NAME = "Imported - to check"
TAG = "reading-list"

_locks: dict[Path, asyncio.Lock] = {}


def _timeout(request: Request) -> float:
    settings: Settings = request.app.state.settings
    return settings.timeout_short


async def stored_id(request: Request) -> int | None:
    """The id on record for this library; the project may be gone since."""
    raw = await library(request).cli(["settings", "get"], _timeout(request))
    value = raw.get(SETTING) if isinstance(raw, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        return int(value)
    except ValueError:
        return None


async def _active(request: Request, project_id: int) -> bool:
    try:
        project = await library(request).cli(
            ["project", "get", "--", str(project_id)], _timeout(request)
        )
    except CLIError as e:
        if e.status == 404:
            return False
        raise
    return isinstance(project, dict) and project.get("status") == "active"


async def resolve(request: Request) -> int:
    """The list's project id, creating the list when there is none."""
    lib = library(request)
    timeout = _timeout(request)
    async with _locks.setdefault(lib.data_dir, asyncio.Lock()):
        current = await stored_id(request)
        if current is not None and await _active(request, current):
            return current
        made = await lib.cli(["project", "create", f"--tags={TAG}", "--", NAME], timeout)
        project_id = int(made["id"])
        await lib.cli(["settings", "update", "--", SETTING, json.dumps(project_id)], timeout)
        return project_id
