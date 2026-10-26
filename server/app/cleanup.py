"""Clean up old files and trash (maintenance operation; deletes, so the panel
asks before Run and it is not nightly unless ticked).

- Restore snapshots: each database restore leaves the replaced database beside
  the new one (`papers.pre-restore`, `.pre-restore.1`, ...); the newest
  KEEP_SNAPSHOTS stay.
- Trash: papers and projects in the trash longer than `trash_days` (Settings →
  Server Admin; 0 leaves the trash alone) are deleted for good.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from .cli import CLIError
from .maintenance import Op

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .jobs import Job
    from .libraries import Library

KEEP_SNAPSHOTS = 3
SNAPSHOT = re.compile(r"^papers\.pre-restore(\.\d+)?$")
SIDECARS = ("-wal", "-shm")


def old_snapshots(data_dir: Path, keep: int = KEEP_SNAPSHOTS) -> list[Path]:
    """Restore snapshots past the newest `keep` (by modification time)."""
    found = [p for p in data_dir.iterdir() if p.is_file() and SNAPSHOT.match(p.name)]
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found[keep:]


def _older(deleted_at, cutoff: datetime) -> bool:
    # linXiv writes SQLite's datetime('now'): UTC without an offset.
    try:
        at = datetime.fromisoformat(str(deleted_at)).replace(tzinfo=UTC)
    except ValueError:
        return False
    return at < cutoff


async def clean_up(app: FastAPI, lib: Library, job: Job) -> dict:
    out = {"snapshots_removed": 0, "papers_purged": 0, "projects_purged": 0}
    for snap in old_snapshots(lib.data_dir):
        for f in (snap, *(snap.with_name(snap.name + s) for s in SIDECARS)):
            f.unlink(missing_ok=True)
        out["snapshots_removed"] += 1

    days = (await app.state.maintenance.schedule())["trash_days"]
    if not days:
        return out
    timeout = app.state.settings.timeout_long
    cutoff = datetime.now(UTC) - timedelta(days=days)
    trash = await lib.cli(["trash", "list"], timeout)
    trash = trash if isinstance(trash, dict) else {}
    for p in trash.get("papers") or []:
        if job.cancel_requested:
            return out
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
    for p in trash.get("projects") or []:
        if job.cancel_requested:
            return out
        pid = p.get("id") if isinstance(p, dict) else None
        if not isinstance(pid, int) or not _older(p.get("deleted_at"), cutoff):
            continue
        try:
            await lib.cli(["trash", "hard-delete-project", "--", str(pid)], timeout)
            out["projects_purged"] += 1
        except CLIError as e:
            job.errors.append({"source_id": f"project {pid}", "error": e.message})
    return out


OP = Op(
    "cleanup",
    "Clean up",
    f"Deletes database restore snapshots beyond the newest {KEEP_SNAPSHOTS}, and papers and"
    " projects that have been in the trash longer than the days set below (0: trash kept).",
    clean_up,
    destructive=True,
)
