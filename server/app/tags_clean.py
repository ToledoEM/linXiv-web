"""Remove tags without papers (maintenance operation; deletes, so the panel asks
before Run and it is not nightly unless ticked).

`linxiv tag delete` takes a tag id and unlinks the tag from every paper and
project, so this op decides on its own which tags are unused, from papers.db
read-only: no row in PAPER_TO_TAG (papers in the trash count, so a restored
paper keeps its tags) and none in PROJECT_TO_TAG (any project status; reading
lists are marked by a project tag). A tag named `Untagged` (any case) is kept.
Each tag is checked again right before its delete, so one linked since the scan
is left alone (counted as skipped).
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from .cli import CLIError
from .maintenance import Op

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .jobs import Job
    from .libraries import Library

KEEP = "untagged"

_UNUSED = (
    "SELECT t.TAG_FK, t.TAG FROM TAG t "
    "WHERE NOT EXISTS (SELECT 1 FROM PAPER_TO_TAG p WHERE p.TAG_FK = t.TAG_FK) "
    "AND NOT EXISTS (SELECT 1 FROM PROJECT_TO_TAG j WHERE j.TAG_FK = t.TAG_FK)"
)


def _connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)


def unused_tags(db_path: Path) -> list[tuple[int, str]]:
    """(id, label) of every tag no paper and no project carries, by label."""
    if not db_path.is_file():
        return []
    conn = _connect(db_path)
    try:
        rows = conn.execute(_UNUSED + " ORDER BY t.TAG COLLATE NOCASE, t.TAG_FK").fetchall()
    finally:
        conn.close()
    return [(int(tid), label or "") for tid, label in rows]


def still_unused(db_path: Path, tag_id: int) -> bool:
    conn = _connect(db_path)
    try:
        return conn.execute(_UNUSED + " AND t.TAG_FK = ?", (tag_id,)).fetchone() is not None
    finally:
        conn.close()


async def clean_tags(app: FastAPI, lib: Library, job: Job) -> dict:
    out = {"tags_removed": 0, "skipped": 0}
    db = lib.data_dir / "papers.db"
    timeout = app.state.settings.timeout_short
    for tag_id, label in await asyncio.to_thread(unused_tags, db):
        if job.cancel_requested:
            break
        if label.strip().casefold() == KEEP:
            continue
        job.current = f"{lib.key}: {label or tag_id}"
        if not await asyncio.to_thread(still_unused, db, tag_id):
            out["skipped"] += 1  # linked since the scan
            continue
        try:
            await lib.cli(["tag", "delete", "--", str(tag_id)], timeout)
            out["tags_removed"] += 1
        except CLIError:
            out["skipped"] += 1
    return out


OP = Op(
    "clean-tags",
    "Clean tags without papers",
    "Deletes tags that no paper (trash included) and no project uses. A tag named"
    " Untagged is kept.",
    clean_tags,
    destructive=True,
)
