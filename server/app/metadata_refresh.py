"""Refresh paper metadata from the source it came from (maintenance operation).

Each paper whose metadata source is recorded (app/bib_store.py: set when a
looked-up record is saved, or by "Complete metadata of new papers") is asked
for again at that source, by its own id: arXiv id, DOI, or OpenAlex work id.
Fetched non-empty values replace the stored ones (title, authors, date,
abstract, journal, DOI) together with the BibTeX fields; tags and the paper's
link stay. Papers without a recorded source, or whose source cannot be asked
again (BibTeX import, file name, AI), are left alone.

Scope (Settings → Server Admin, `web_maint_refresh` {scope}): every paper, or
only papers published within the last year and preprints (arXiv, bioRxiv,
medRxiv), whose records change most. Runs on demand, nightly or monthly.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import TYPE_CHECKING

from fastapi import HTTPException
from pydantic import ValidationError

from . import bib_store
from .cli import CLIError
from .maintenance import Op, parse_setting, report_path, write_report
from .routes.metadata import (
    BIORXIV_PREFIXES,
    UNKNOWN_AUTHOR,
    MetadataIn,
    mailto_from,
    match_by_id,
    openalex_work,
    repair_args,
)
from .routes.user_settings import ncbi_api_key

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .jobs import Job
    from .libraries import Library

REPORT = "metadata-refresh.json"
OPTIONS_SETTING = "web_maint_refresh"
SCOPES = ("all", "recent_or_preprint")
DEFAULT_SCOPE = "recent_or_preprint"
RECENT_DAYS = 365
PACE_SECONDS = 1.0  # between lookups: the sources are shared public services
PREPRINT_JOURNALS = {"biorxiv", "medrxiv"}
FIELDS = ("title", "authors", "published", "summary", "category", "doi", "url")


def options_from(stored: dict) -> dict:
    raw = parse_setting(stored.get(OPTIONS_SETTING))
    scope = raw.get("scope")
    return {"scope": scope if scope in SCOPES else DEFAULT_SCOPE}


def is_preprint(paper: dict) -> bool:
    sid = str(paper.get("source_id") or "")
    doi = str(paper.get("doi") or "").lower()
    journal = str(paper.get("category") or "").strip().lower()
    return (
        sid.startswith("arxiv:") or doi.startswith(BIORXIV_PREFIXES) or journal in PREPRINT_JOURNALS
    )


def is_recent(paper: dict, today: date) -> bool:
    try:
        published = date.fromisoformat(str(paper.get("published") or "")[:10])
    except ValueError:
        return False
    return published >= today - timedelta(days=RECENT_DAYS)


def in_scope(paper: dict, scope: str, today: date) -> bool:
    return scope == "all" or is_recent(paper, today) or is_preprint(paper)


def _record(paper: dict) -> dict:
    return {
        "title": paper.get("title") or "",
        "authors": [a for a in paper.get("authors") or [] if a != UNKNOWN_AUTHOR],
        "published": paper.get("published") or "",
        "summary": paper.get("summary") or "",
        "category": paper.get("category") or None,
        "doi": paper.get("doi") or None,
        "url": paper.get("url") or None,
    }


def refreshed(paper: dict, found: dict) -> MetadataIn | None:
    """The stored record with the fetched non-empty values; None when nothing
    changes or the result would not save. The link stays; an arXiv record's
    subject code never replaces a journal; a year-only date ("YYYY-01-01")
    never replaces a fuller one of the same year."""
    before = _record(paper)
    record = dict(before)
    for key in ("title", "authors", "published", "summary", "category", "doi"):
        value = found.get(key)
        if not value:
            continue
        if key == "category" and found.get("source") == "arxiv" and before["category"]:
            continue
        if (
            key == "published"
            and str(value).endswith("-01-01")
            and str(before["published"])[:4] == str(value)[:4]
        ):
            continue
        record[key] = value
    if not record["url"] and found.get("url"):
        record["url"] = found["url"]
    try:
        out = MetadataIn.model_validate(record)
    except ValidationError:
        return None
    try:
        norm = MetadataIn.model_validate(before).model_dump(include=set(FIELDS))
    except ValidationError:
        norm = {}  # the stored record would not save as is: anything valid is a change
    return None if out.model_dump(include=set(FIELDS)) == norm else out


async def _trash_ids(lib: Library, timeout: float) -> set[str] | None:
    try:
        trash = await lib.cli(["trash", "list"], timeout)
    except CLIError:
        return None
    papers = trash.get("papers") if isinstance(trash, dict) else None
    return {str(p.get("source_id")) for p in papers or [] if isinstance(p, dict)}


async def refresh(app: FastAPI, lib: Library, job: Job) -> dict:
    out = {"checked": 0, "updated": 0, "unchanged": 0, "not_found": 0, "not_refreshable": 0}
    rows = await bib_store.all_rows(lib)
    if not any(r.get("metadata_source") for r in rows.values()):
        return out
    s = app.state.settings

    def call(args: list[str]):
        return lib.cli(args, s.timeout_long)

    scope = options_from(await app.state.maintenance.stored())["scope"]
    stored = await lib.cli(["settings", "get"], s.timeout_short)
    stored = stored if isinstance(stored, dict) else {}
    ncbi_key = ncbi_api_key(stored)[0]
    papers = [p for p in await call(["list"]) or [] if isinstance(p, dict)]
    trash = await _trash_ids(lib, s.timeout_short)
    if trash is not None:
        await bib_store.prune(lib, {str(p.get("source_id")) for p in papers} | trash)
    today = date.today()
    todo = []
    for p in papers:
        row = rows.get(str(p.get("source_id")))
        src = (row or {}).get("metadata_source")
        if not src or not in_scope(p, scope, today):
            continue
        if src.get("source") not in bib_store.REFRESHABLE:
            out["not_refreshable"] += 1
            continue
        todo.append((p, src, row.get("bib") or {}))
    not_found = []
    for i, (paper, src, bib) in enumerate(todo):
        if job.cancel_requested:
            break
        if i:
            await asyncio.sleep(PACE_SECONDS)
        sid = str(paper["source_id"])
        job.current = f"{lib.key}: {sid}"
        out["checked"] += 1
        try:
            if src["source"] == "openalex":
                found = await openalex_work(
                    src.get("ref") or "", mailto_from(stored, "OPENALEX_MAILTO")
                )
            else:
                found = await match_by_id(call, paper, [src["source"]], ncbi_key, stored)
            if not found:
                out["not_found"] += 1
                not_found.append(
                    {"source_id": sid, "title": paper.get("title") or "", "source": src["source"]}
                )
                continue
            fixed = refreshed(paper, found)
            if fixed:
                await call(repair_args(sid, fixed, paper.get("tags") or []))
            new_bib = found.get("bib") or {}
            bib_changed = any(bib.get(k) != v for k, v in new_bib.items())
            await bib_store.upsert(
                lib, sid, new_bib, src["source"], found.get("ref") or src.get("ref"), True
            )
            out["updated" if fixed or bib_changed else "unchanged"] += 1
        except (CLIError, HTTPException) as e:
            job.errors.append(
                {"source_id": sid, "error": getattr(e, "message", None) or str(e.detail)}
            )
    write_report(
        report_path(lib, REPORT),
        {"scope": scope, "checked_on": today.isoformat(), "not_found": not_found},
    )
    return out


OP = Op(
    "metadata-refresh",
    "Refresh metadata",
    "Asks again the source each paper's metadata came from (Crossref, PubMed, bioRxiv, arXiv"
    " or OpenAlex, recorded when a looked-up record is saved) and replaces the stored values"
    " with the fetched ones, BibTeX fields included. Papers with no recorded source stay as"
    " they are.",
    refresh,
)
