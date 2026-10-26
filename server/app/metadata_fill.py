"""Complete the metadata of newly added papers (maintenance operation).

"New" means added to the library since the operation last ran there (the first
run looks back FIRST_RUN_DAYS), read from `PAPER_ROOTS.CREATED_AT` in papers.db.
A new paper is incomplete when its title looks like junk, or it has no authors,
date, abstract, journal or DOI. For each one the operation asks the lookup
sources for the record under the paper's own arXiv id or DOI (never a title
search, so a hit is the same paper) and fills only the empty fields; what is
already stored stays. Papers it cannot complete are listed for review in
`maintenance/metadata-review.json`, which Library → batch edit opens.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException
from pydantic import ValidationError

from .cli import CLIError
from .maintenance import Op, read_report, report_lock, report_path, write_report
from .pdf_name import pdf_file, title_from_file, title_suspect
from .routes.metadata import UNKNOWN_AUTHOR, MetadataIn, match_by_id, repair_args
from .routes.user_settings import disabled_sources, ncbi_api_key

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .jobs import Job
    from .libraries import Library

REPORT = "metadata-review.json"
FIRST_RUN_DAYS = 30
PACE_SECONDS = 1.0  # between lookups: the sources are shared public services
SQLITE_TIME = "%Y-%m-%d %H:%M:%S"  # CREATED_AT, as SQLite's datetime('now') writes it (UTC)
# Gap name -> lookup candidate field that fills it.
FILLS = {
    "title": "title",
    "authors": "authors",
    "date": "published",
    "abstract": "summary",
    "journal": "category",
    "doi": "doi",
}


def added_since(db_path: Path, since: str) -> set[str]:
    """Papers (not in the trash) added after `since` (UTC, SQLITE_TIME)."""
    if not db_path.is_file():
        return set()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    try:
        rows = conn.execute(
            "SELECT SOURCE_ID FROM PAPER_ROOTS WHERE DELETED_AT IS NULL AND CREATED_AT > ?",
            (since,),
        ).fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


def gaps(paper: dict, pdf_bases: list[str]) -> list[str]:
    """What a library paper (`linxiv list` entry) is missing, in FILLS order."""
    sid = str(paper.get("source_id") or "")
    arxiv = sid.startswith("arxiv:")
    rel = pdf_file(paper.get("pdf_path"), pdf_bases)
    authors = paper.get("authors") or []
    missing = {
        "title": title_suspect(paper.get("title"), title_from_file(rel)),
        "authors": not authors or authors == [UNKNOWN_AUTHOR],
        "date": not paper.get("published"),
        "abstract": not str(paper.get("summary") or "").strip(),
        # arXiv papers carry a subject, not a journal, and need no DOI.
        "journal": not arxiv and not (paper.get("category") or paper.get("journal_ref")),
        "doi": not arxiv and not paper.get("doi"),
    }
    return [k for k in FILLS if missing[k]]


def completed(paper: dict, found: dict, missing: list[str]) -> MetadataIn | None:
    """The stored record with the empty fields taken from `found`; None when
    nothing changes or the result would not save."""
    record = {
        "title": paper.get("title") or "",
        "authors": [a for a in paper.get("authors") or [] if a != UNKNOWN_AUTHOR],
        "published": paper.get("published") or "",
        "summary": paper.get("summary") or "",
        "category": paper.get("category"),
        "doi": paper.get("doi"),
        "url": paper.get("url"),
    }
    changed = False
    for gap in missing:
        value = found.get(FILLS[gap])
        if value:
            record[FILLS[gap]] = value
            changed = True
    if not record["url"] and found.get("url"):
        record["url"] = found["url"]
    if not changed:
        return None
    try:
        return MetadataIn.model_validate(record)
    except ValidationError:
        return None


def _entry(paper: dict, missing: list[str]) -> dict:
    return {
        "source_id": paper.get("source_id"),
        "title": paper.get("title") or "",
        "missing": missing,
    }


async def complete_new(app: FastAPI, lib: Library, job: Job) -> dict:
    s = app.state.settings

    def call(args: list[str]):
        return lib.cli(args, s.timeout_long)

    path = report_path(lib, REPORT)
    report = read_report(path)
    started = datetime.now(UTC).strftime(SQLITE_TIME)
    since = report.get("checked_until") or (
        datetime.now(UTC) - timedelta(days=FIRST_RUN_DAYS)
    ).strftime(SQLITE_TIME)
    new = await asyncio.to_thread(added_since, lib.data_dir / "papers.db", since)
    stored = await lib.cli(["settings", "get"], s.timeout_short) if new else {}
    stored = stored if isinstance(stored, dict) else {}
    off = disabled_sources(stored)
    preferred = str(stored.get("web_lookup_source") or "crossref")
    ncbi_key = ncbi_api_key(stored)[0]
    papers = await call(["list"]) if new else []
    bases = [str(lib.data_dir / "pdfs"), str(lib.pdf_dir)]
    todo = [
        (p, m)
        for p in papers or []
        if isinstance(p, dict) and p.get("source_id") in new and (m := gaps(p, bases))
    ]
    review: dict[str, dict] = {}
    done = 0
    for i, (paper, missing) in enumerate(todo):
        if job.cancel_requested:
            break
        if i:
            await asyncio.sleep(PACE_SECONDS)
        sid = str(paper["source_id"])
        job.current = f"{lib.key}: {sid}"
        try:
            found = await match_by_id(call, paper, off, preferred, ncbi_key)
            fixed = completed(paper, found, missing) if found else None
            if fixed:
                await call(repair_args(sid, fixed, paper.get("tags") or []))
                done += 1
                continue
        except (CLIError, HTTPException) as e:
            job.errors.append(
                {"source_id": sid, "error": getattr(e, "message", None) or str(e.detail)}
            )
        review[sid] = _entry(paper, missing)
    async with report_lock(path):
        current = read_report(path)
        listed = {p["source_id"]: p for p in current.get("papers") or [] if p.get("source_id")}
        listed.update(review)
        out = {**current, "papers": sorted(listed.values(), key=lambda p: p["source_id"])}
        if not job.cancel_requested:
            out["checked_until"] = started
        write_report(path, out)
    return {"new_papers": len(new), "completed": done, "to_review": len(review)}


OP = Op(
    "complete-metadata",
    "Complete metadata of new papers",
    "For papers added since the last run with a junk title, or no authors, date, abstract,"
    " journal or DOI: fills the empty fields from the record found under the paper's own DOI"
    " or arXiv id. Papers it cannot complete are listed for review in Library.",
    complete_new,
)
