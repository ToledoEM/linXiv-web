"""PDF file check (maintenance operation, report only) and the orphan move.

Lists papers whose PDF file is gone from disk, and PDF files in the PDF folder
(subfolders included) that no paper points at, e.g. left behind by a move or an
import that failed half way. Papers in the trash still own their files. The
report also breaks the folder down (files of any type, PDFs, top-level
subfolders) next to the paper counts, so "files on disk" vs "papers" adds up.

Top-level subfolders the admin lists in `web_maint_pdfcheck` {skip: [...]} (e.g.
`dup`, `errors`) and `orphans/` are counted but never listed as unlinked. The
check itself changes nothing; the report goes to `maintenance/pdf-check.json`.

`move_orphans` (Move to orphans/, started from the report) moves unlinked PDFs
into `orphans/<same relative path>` one at a time under the CLI lock. Files
changed in the last hour are left alone (an import may be writing them).
Nothing is deleted.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .duplicates import pdf_records
from .maintenance import Op, parse_setting, report_lock, report_path, write_report

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .jobs import Job
    from .libraries import Library

REPORT = "pdf-check.json"
OPTIONS_SETTING = "web_maint_pdfcheck"
ORPHANS = "orphans"
ROOT_FOLDER = "."
MAX_SKIP = 20
# Rows the API returns per list; the report file and CSV keep every row.
MAX_LISTED = 500
# Files modified this recently are not moved (seconds).
RECENT_SECONDS = 3600
ORPHAN_KIND = "pdf-orphans"


def skip_from(stored: dict) -> list[str]:
    """Admin-listed top-level folders the check skips (stored order, no orphans/)."""
    raw = parse_setting(stored.get(OPTIONS_SETTING)).get("skip")
    if not isinstance(raw, list):
        return []
    out = [s for s in raw if isinstance(s, str) and valid_folder(s) and s != ORPHANS]
    return list(dict.fromkeys(out))[:MAX_SKIP]


def valid_folder(name: str) -> bool:
    """One folder name directly under the PDF folder: no path separators, not . or .."""
    return (
        0 < len(name) <= 100
        and name == name.strip()
        and name not in (".", "..")
        and not any(c in name for c in "/\\\0")
    )


def _paper_count(db_path: Path) -> int:
    if not db_path.is_file():
        return 0
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    try:
        row = conn.execute("SELECT count(*) FROM PAPER_ROOTS WHERE DELETED_AT IS NULL").fetchone()
    finally:
        conn.close()
    return int(row[0]) if row else 0


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def check(db_path: Path, pdf_dir: Path, skip: list[str] | tuple[str, ...] = ()) -> dict:
    records = pdf_records(db_path, pdf_dir)
    missing = [
        {"source_id": r["source_id"], "version": r["version"], "title": r["title"]}
        for r in records
        if not r["exists"] and not r["trashed"]
    ]
    owned = {r["path"].resolve() for r in records if r["exists"]}
    live = [r for r in records if r["exists"] and not r["trashed"]]
    skipped = {*skip, ORPHANS}
    root = pdf_dir.resolve()
    folders: dict[str, dict] = {}
    disk = {"files": 0, "pdf_files": 0, "other_files": 0, "skipped_files": 0}
    unlinked = []
    if root.is_dir():
        for f in sorted(root.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(root)
            top = rel.parts[0] if len(rel.parts) > 1 else ROOT_FOLDER
            row = folders.setdefault(
                top,
                {"folder": top, "files": 0, "pdfs": 0, "unlinked": 0, "skipped": top in skipped},
            )
            is_pdf = f.suffix.lower() == ".pdf"
            row["files"] += 1
            disk["files"] += 1
            row["pdfs"] += is_pdf
            disk["pdf_files" if is_pdf else "other_files"] += 1
            if row["skipped"]:
                disk["skipped_files"] += 1
                continue
            if is_pdf and f.resolve() not in owned:
                st = f.stat()
                row["unlinked"] += 1
                unlinked.append(
                    {"file": str(rel), "size": st.st_size, "modified": _iso(st.st_mtime)}
                )
    disk["by_folder"] = sorted(
        folders.values(), key=lambda r: (r["folder"] != ROOT_FOLDER, r["folder"])
    )
    return {
        "pdfs": len(records),
        "papers": _paper_count(db_path),
        "papers_with_pdf": len({r["source_id"] for r in live}),
        "extra_versions": len(live) - len({r["source_id"] for r in live}),
        "trashed_pdfs": sum(1 for r in records if r["exists"] and r["trashed"]),
        "skip": sorted(skipped),
        "disk": disk,
        "missing_count": len(missing),
        "unlinked_count": len(unlinked),
        "missing": missing,
        "unlinked": unlinked,
    }


async def run_check(app: FastAPI, lib: Library) -> dict:
    """Check one library with the stored skip list and write its report."""
    skip = skip_from(await app.state.maintenance.stored())
    found = await asyncio.to_thread(check, lib.data_dir / "papers.db", lib.pdf_dir, skip)
    checked_at = app.state.maintenance.now().isoformat(timespec="seconds")
    path = report_path(lib, REPORT)
    async with report_lock(path):
        write_report(path, {"checked_at": checked_at, **found})
    return found


async def check_pdfs(app: FastAPI, lib: Library, job: Job) -> dict:
    found = await run_check(app, lib)
    return {
        "pdfs_checked": found["pdfs"],
        "missing_files": found["missing_count"],
        "unlinked_files": found["unlinked_count"],
    }


def _free_name(dest: Path) -> Path:
    """`dest`, or `name (2).pdf`, `name (3).pdf`… when taken."""
    n = 2
    out = dest
    while out.exists():
        out = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        n += 1
    return out


def _move_one(root: Path, rel: str) -> str:
    src = root / rel
    dest = _free_name(root / ORPHANS / rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dest)
    parent = src.parent
    while parent != root:  # prune the folders this move left empty
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return str(dest.relative_to(root))


async def move_orphans(app: FastAPI, lib: Library, job: Job) -> None:
    """Job body: check again (never trust an old report), move unlinked PDFs
    older than RECENT_SECONDS to orphans/, then write a fresh report."""
    skip = skip_from(await app.state.maintenance.stored())
    root = lib.pdf_dir.resolve()
    found = await asyncio.to_thread(check, lib.data_dir / "papers.db", lib.pdf_dir, skip)
    job.total = len(found["unlinked"])
    job.result = {"moved": 0, "skipped_recent": 0, "failed": 0}
    cutoff = time.time() - RECENT_SECONDS
    lock = lib.lock
    for item in found["unlinked"]:
        if job.cancel_requested:
            break
        rel = item["file"]
        job.current = rel
        try:
            if (root / rel).stat().st_mtime > cutoff:
                job.result["skipped_recent"] += 1
                continue
            async with lock if lock is not None else contextlib.nullcontext():
                await asyncio.to_thread(_move_one, root, rel)
            job.result["moved"] += 1
        except OSError as e:
            job.result["failed"] += 1
            job.errors.append({"source_id": rel, "error": e.strerror or type(e).__name__})
        finally:
            job.done += 1
    await run_check(app, lib)


OP = Op(
    "pdf-check",
    "Check PDF files",
    "Lists papers whose PDF file is missing on disk and PDF files that no paper points at,"
    " with a breakdown of the files on disk. Changes nothing.",
    check_pdfs,
)
