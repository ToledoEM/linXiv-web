"""PDF file check (maintenance operation, report only).

Lists papers whose PDF file is gone from disk, and PDF files in the PDF folder
(subfolders included) that no paper points at, e.g. left behind by a move or an
import that failed half way. Papers in the trash still own their files. Nothing
is deleted or changed; the report goes to `maintenance/pdf-check.json`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from .duplicates import pdf_records
from .maintenance import Op, report_path, write_report

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .jobs import Job
    from .libraries import Library

REPORT = "pdf-check.json"
# Rows kept in the report per list; the counts are always complete.
MAX_LISTED = 500


def check(db_path: Path, pdf_dir: Path) -> dict:
    records = pdf_records(db_path, pdf_dir)
    missing = [
        {"source_id": r["source_id"], "version": r["version"], "title": r["title"]}
        for r in records
        if not r["exists"] and not r["trashed"]
    ]
    owned = {r["path"].resolve() for r in records if r["exists"]}
    root = pdf_dir.resolve()
    unlinked = []
    if root.is_dir():
        for f in sorted(root.rglob("*")):
            if f.is_file() and f.suffix.lower() == ".pdf" and f.resolve() not in owned:
                unlinked.append({"file": str(f.relative_to(root)), "size": f.stat().st_size})
    return {
        "pdfs": len(records),
        "missing_count": len(missing),
        "unlinked_count": len(unlinked),
        "missing": missing[:MAX_LISTED],
        "unlinked": unlinked[:MAX_LISTED],
    }


async def check_pdfs(app: FastAPI, lib: Library, job: Job) -> dict:
    found = await asyncio.to_thread(check, lib.data_dir / "papers.db", lib.pdf_dir)
    checked_at = app.state.maintenance.now().isoformat(timespec="seconds")
    write_report(report_path(lib, REPORT), {"checked_at": checked_at, **found})
    return {
        "pdfs_checked": found["pdfs"],
        "missing_files": found["missing_count"],
        "unlinked_files": found["unlinked_count"],
    }


OP = Op(
    "pdf-check",
    "Check PDF files",
    "Lists papers whose PDF file is missing on disk and PDF files that no paper points at."
    " Changes nothing.",
    check_pdfs,
)
