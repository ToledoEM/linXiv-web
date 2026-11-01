"""BibTeX fields and the metadata source of each paper (web-only, per library).

linXiv's `paper repair` stores title, authors, date, abstract, category (the
journal), DOI and URL only; nothing else a `.bib` entry needs (volume, pages,
publisher, entry type...) has a CLI command. Those fields live here, in
`<library data dir>/linxiv-web-bib.db`, one row per paper keyed by `source_id`
(which `paper repair` never changes). A paper with no row has every field null.

The row also records where the paper's metadata last came from
(`metadata_source`, `metadata_ref`: the source's own id for it, a DOI, arXiv id,
PMID or OpenAlex work id), so "Refresh metadata" asks that source again.

The CLI does not know this file: merges, hard deletes and backups update it
here (routes/duplicates.py, routes/trash.py, trash_empty.py, db_backup.py).
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .libraries import Library

FILE = "linxiv-web-bib.db"
# BibTeX fields not held by linXiv itself, in the order a `.bib` entry lists them.
# title, author, journal (category), year, doi and url come from the CLI record.
BIB_FIELDS = (
    "entry_type",
    "booktitle",
    "editor",
    "edition",
    "series",
    "volume",
    "number",
    "chapter",
    "pages",
    "month",
    "publisher",
    "address",
    "school",
    "institution",
    "organization",
    "howpublished",
    "note",
    "issn",
    "isbn",
    "eprint",
    "archive_prefix",
    "primary_class",
)
SOURCE_COLUMNS = ("metadata_source", "metadata_ref", "metadata_fetched_at")
# Where metadata can come from. The first five can be asked again by id
# (maintenance "Refresh metadata"); the others cannot.
REFRESHABLE = ("crossref", "pubmed", "biorxiv", "arxiv", "openalex")
SOURCES = (*REFRESHABLE, "bibtex", "filename", "ai")
ENTRY_TYPES = (
    "article",
    "book",
    "booklet",
    "conference",
    "inbook",
    "incollection",
    "inproceedings",
    "manual",
    "mastersthesis",
    "misc",
    "phdthesis",
    "proceedings",
    "techreport",
    "unpublished",
)
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
MAX_VALUE = 2000

_COLUMNS = (*BIB_FIELDS, *SOURCE_COLUMNS)
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS paper_bib (source_id TEXT PRIMARY KEY, "
    + ", ".join(f"{c} TEXT" for c in _COLUMNS)
    + ")"
)
# Built from the constant column names above, never from input.
_INSERT = (
    f"INSERT OR REPLACE INTO paper_bib (source_id, {', '.join(_COLUMNS)}) "  # noqa: S608
    f"VALUES ({', '.join('?' * (len(_COLUMNS) + 1))})"
)


def month(value: object) -> str | None:
    """BibTeX month macro (jan..dec) from 1-12, "05", "May" or "may"."""
    text = str(value or "").strip().lower()
    if text.isdigit() and 1 <= int(text) <= 12:
        return MONTHS[int(text) - 1]
    return text[:3] if text[:3] in MONTHS else None


def clean(fields: dict | None) -> dict[str, str]:
    """Known BIB_FIELDS with a non-blank single-line value; the rest dropped."""
    out: dict[str, str] = {}
    for key, value in (fields or {}).items():
        if key not in BIB_FIELDS or value is None or isinstance(value, bool):
            continue
        text = re.sub(r"\s+", " ", str(value)).strip()[:MAX_VALUE]
        if key == "month":
            text = month(text) or ""
        elif key == "entry_type":
            text = text.lower() if text.lower() in ENTRY_TYPES else ""
        if text:
            out[key] = text
    return out


def _path(lib: Library) -> Path:
    return lib.data_dir / FILE


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_SCHEMA)
    return conn


def _row(r: sqlite3.Row) -> dict:
    return {
        "bib": {k: r[k] for k in BIB_FIELDS if r[k] is not None},
        "metadata_source": (
            {"source": r["metadata_source"], "ref": r["metadata_ref"]}
            if r["metadata_source"]
            else None
        ),
        "metadata_fetched_at": r["metadata_fetched_at"],
    }


def _get_many(path: Path, sids: list[str]) -> dict[str, dict]:
    if not sids or not path.is_file():
        return {}
    conn = _connect(path)
    try:
        out = {}
        for i in range(0, len(sids), 500):
            chunk = sids[i : i + 500]
            marks = ",".join("?" * len(chunk))
            # Only "?" placeholders are formatted in; the ids are bound.
            sql = f"SELECT * FROM paper_bib WHERE source_id IN ({marks})"  # noqa: S608
            for r in conn.execute(sql, chunk).fetchall():
                out[r["source_id"]] = _row(r)
        return out
    finally:
        conn.close()


def _all(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    conn = _connect(path)
    try:
        return {r["source_id"]: _row(r) for r in conn.execute("SELECT * FROM paper_bib")}
    finally:
        conn.close()


def _upsert(
    path: Path,
    sid: str,
    fields: dict[str, str],
    source: str | None,
    ref: str | None,
    overwrite: bool,
    fetched_at: str | None,
) -> None:
    conn = _connect(path)
    try:
        with conn:
            current = conn.execute("SELECT * FROM paper_bib WHERE source_id = ?", (sid,)).fetchone()
            row = {c: (current[c] if current else None) for c in _COLUMNS}
            for key, value in fields.items():
                if overwrite or row[key] is None:
                    row[key] = value
            if source and (overwrite or not row["metadata_source"]):
                row["metadata_source"] = source
                row["metadata_ref"] = ref
                row["metadata_fetched_at"] = fetched_at
            conn.execute(_INSERT, (sid, *(row[c] for c in _COLUMNS)))
    finally:
        conn.close()


def _clear(path: Path, sid: str, keys: list[str]) -> None:
    keys = [k for k in keys if k in BIB_FIELDS]
    if not keys or not path.is_file():
        return
    conn = _connect(path)
    try:
        with conn:
            # `keys` are filtered to the constant BIB_FIELDS above.
            sets = ", ".join(f"{k} = NULL" for k in keys)
            conn.execute(f"UPDATE paper_bib SET {sets} WHERE source_id = ?", (sid,))  # noqa: S608
    finally:
        conn.close()


def _move(path: Path, loser: str, winner: str) -> None:
    if not path.is_file():
        return
    conn = _connect(path)
    try:
        with conn:
            lose = conn.execute("SELECT * FROM paper_bib WHERE source_id = ?", (loser,)).fetchone()
            if lose is None:
                return
            win = conn.execute("SELECT * FROM paper_bib WHERE source_id = ?", (winner,)).fetchone()
            row = {c: (win[c] if win else None) for c in _COLUMNS}
            for c in BIB_FIELDS:
                if row[c] is None:
                    row[c] = lose[c]
            if not row["metadata_source"]:
                for c in SOURCE_COLUMNS:
                    row[c] = lose[c]
            conn.execute(_INSERT, (winner, *(row[c] for c in _COLUMNS)))
            conn.execute("DELETE FROM paper_bib WHERE source_id = ?", (loser,))
    finally:
        conn.close()


def _delete(path: Path, sids: list[str]) -> int:
    if not sids or not path.is_file():
        return 0
    conn = _connect(path)
    try:
        with conn:
            return sum(
                conn.execute("DELETE FROM paper_bib WHERE source_id = ?", (s,)).rowcount
                for s in sids
            )
    finally:
        conn.close()


def _prune(path: Path, keep: set[str]) -> int:
    if not path.is_file():
        return 0
    conn = _connect(path)
    try:
        gone = [
            r["source_id"]
            for r in conn.execute("SELECT source_id FROM paper_bib")
            if r["source_id"] not in keep
        ]
    finally:
        conn.close()
    return _delete(path, gone)


def _backup(path: Path, target: Path) -> bool:
    if not path.is_file():
        return False
    src = _connect(path)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return True


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


async def get(lib: Library, sid: str) -> dict:
    """{bib, metadata_source, metadata_fetched_at}; empty values when no row."""
    found = await asyncio.to_thread(_get_many, _path(lib), [sid])
    return found.get(sid) or {"bib": {}, "metadata_source": None, "metadata_fetched_at": None}


async def get_many(lib: Library, sids: Iterable[str]) -> dict[str, dict]:
    return await asyncio.to_thread(_get_many, _path(lib), list(dict.fromkeys(sids)))


async def all_rows(lib: Library) -> dict[str, dict]:
    return await asyncio.to_thread(_all, _path(lib))


async def upsert(
    lib: Library,
    sid: str,
    fields: dict | None,
    source: str | None = None,
    ref: str | None = None,
    overwrite: bool = True,
) -> None:
    """Store a paper's fields (cleaned) and, with `source`, where they came from.
    `overwrite=False` only fills fields (and the source) that are still null."""
    values = clean(fields)
    src = source if source in SOURCES else None
    if not values and not src:
        return
    ref_text = str(ref).strip()[:MAX_VALUE] if ref else None
    await asyncio.to_thread(
        _upsert, _path(lib), sid, values, src, ref_text, overwrite, now() if src else None
    )


async def clear(lib: Library, sid: str, keys: Iterable[str]) -> None:
    """Set these BibTeX fields of a paper back to null."""
    await asyncio.to_thread(_clear, _path(lib), sid, list(keys))


async def move(lib: Library, loser: str, winner: str) -> None:
    """After a merge: the winner keeps its fields, takes the loser's where null."""
    await asyncio.to_thread(_move, _path(lib), loser, winner)


async def delete(lib: Library, sids: Iterable[str]) -> int:
    return await asyncio.to_thread(_delete, _path(lib), list(sids))


async def prune(lib: Library, keep: Iterable[str]) -> int:
    """Drop rows of papers no longer in the library (`keep`: every source_id,
    trash included)."""
    return await asyncio.to_thread(_prune, _path(lib), set(keep))


async def backup_to(lib: Library, target: Path) -> bool:
    """Consistent copy of the file to `target`; False when the library has none."""
    return await asyncio.to_thread(_backup, _path(lib), target)
