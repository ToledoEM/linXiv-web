"""Empty the trash of old papers (maintenance operation; deletes for good, so the
panel asks before Run and it is not nightly unless ticked).

Papers in the trash longer than `trash_days` (Settings → Server Admin, 1 to 120;
0, the default, leaves the trash alone) are deleted for good with
`linxiv trash hard-delete`. Projects in the trash are never touched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from .cli import CLIError
from .maintenance import Op

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .jobs import Job
    from .libraries import Library


def _older(deleted_at, cutoff: datetime) -> bool:
    # linXiv writes SQLite's datetime('now'): UTC without an offset.
    try:
        at = datetime.fromisoformat(str(deleted_at)).replace(tzinfo=UTC)
    except ValueError:
        return False
    return at < cutoff


async def empty_trash(app: FastAPI, lib: Library, job: Job) -> dict:
    out = {"papers_purged": 0}
    days = (await app.state.maintenance.schedule())["trash_days"]
    if not days:
        return out
    timeout = app.state.settings.timeout_long
    cutoff = datetime.now(UTC) - timedelta(days=days)
    trash = await lib.cli(["trash", "list"], timeout)
    trash = trash if isinstance(trash, dict) else {}
    for p in trash.get("papers") or []:
        if job.cancel_requested:
            break
        sid = str(p.get("source_id") or "")
        if not sid or not _older(p.get("deleted_at"), cutoff):
            continue
        job.current = f"{lib.key}: {sid}"
        try:
            await lib.cli(["trash", "hard-delete", "--", sid], timeout)
        except CLIError as e:
            # Older linxiv deletes the paper, then reports "not found" (routes/trash.py).
            if e.status != 404:
                job.errors.append({"source_id": sid, "error": e.message})
                continue
        out["papers_purged"] += 1
    return out


OP = Op(
    "empty-trash",
    "Empty trash",
    "Deletes for good the papers that have been in the trash longer than the days set below"
    " (0: never). Projects in the trash stay.",
    empty_trash,
    destructive=True,
)
