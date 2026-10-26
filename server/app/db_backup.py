"""Database backups on the server (maintenance operation).

`linxiv backup` snapshots each library's papers.db (papers, metadata, projects,
notes, tags; never PDF files) into `maintenance/backups/` of that library; the
newest `keep_backups` (Settings → Server Admin) stay, older ones are deleted.
Settings → Server Admin lists them for download, and Settings → Backup restores
a downloaded one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .cli import CLIError
from .maintenance import Op, report_path

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .jobs import Job
    from .libraries import Library

FOLDER = "backups"
NAME = re.compile(r"^papers-\d{8}-\d{6}\.db$")


def backup_dir(lib: Library) -> Path:
    folder = report_path(lib, FOLDER)
    folder.mkdir(mode=0o700, exist_ok=True)
    return folder


def backups(lib: Library) -> list[Path]:
    """Newest first (the names sort by time)."""
    folder = lib.data_dir / "maintenance" / FOLDER
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.iterdir() if NAME.match(p.name)), reverse=True)


async def back_up(app: FastAPI, lib: Library, job: Job) -> dict:
    m = app.state.maintenance
    keep = (await m.schedule())["keep_backups"]
    name = m.now().strftime("papers-%Y%m%d-%H%M%S.db")
    target = backup_dir(lib) / name
    out = await lib.cli(["backup", "--", str(target)], app.state.settings.timeout_long)
    written = Path(str(out.get("path", ""))) if isinstance(out, dict) else None
    if not written or not written.is_file():
        raise CLIError(502, "linxiv backup wrote no file")
    removed = 0
    for old in backups(lib)[keep:]:
        old.unlink(missing_ok=True)
        removed += 1
    return {"backed_up": 1, "removed": removed}


OP = Op(
    "backup",
    "Back up databases",
    "Saves a copy of each library's database (papers, metadata, projects, notes, tags;"
    " not the PDF files) on the server and keeps the newest ones.",
    back_up,
)
