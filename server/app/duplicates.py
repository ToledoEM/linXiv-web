"""Duplicate papers: different papers whose saved PDFs are the same file.

linXiv keeps no checksum, so the maintenance operation hashes every saved PDF
(SHA-256) and groups papers with identical files. Hashes are cached per library
in `maintenance/pdf-hashes.json` keyed by path, size and mtime, so a nightly run
only reads new or changed files. Versions of one paper never count as
duplicates of each other. The groups go to `maintenance/duplicates.json`, read
by the Duplicates page, which merges a duplicate into the paper kept
(`linxiv paper merge`) or dismisses a group as not duplicates.

Paths come straight from papers.db (read only, like `pdf_layout`): `pdf path`
per paper would mean one CLI call for each of thousands of papers.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .maintenance import Op, read_report, report_path, write_report
from .pdf_layout import safe_file_name

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .jobs import Job
    from .libraries import Library

REPORT = "duplicates.json"
CACHE = "pdf-hashes.json"
CHUNK = 1024 * 1024
# One write at a time per report file (merge / dismiss / scan).
_locks: dict[Path, asyncio.Lock] = {}


def lock_for(path: Path) -> asyncio.Lock:
    return _locks.setdefault(path, asyncio.Lock())


def saved_pdfs(db_path: Path, pdf_dir: Path) -> list[dict[str, Any]]:
    """Every saved PDF of a paper not in the trash: source_id, version, title, file."""
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    try:
        rows = conn.execute(
            "SELECT p.SOURCE_ID, p.VERSION, p.TITLE, m.PDF_PATH FROM PAPER p "
            "JOIN PAPER_META m ON m.PAPER_ID = p.PAPER_ID "
            "JOIN PAPER_ROOTS r ON r.SOURCE_FK = p.SOURCE_FK "
            "WHERE r.DELETED_AT IS NULL AND (p.HAS_PDF = 1 OR coalesce(m.PDF_PATH, '') <> '') "
            "ORDER BY p.SOURCE_ID, p.VERSION"
        ).fetchall()
    finally:
        conn.close()
    out = []
    for sid, version, title, stored in rows:
        path = (
            Path(stored)
            if stored and Path(stored).is_file()
            else pdf_dir / safe_file_name(sid, version)
        )
        if path.is_file():
            out.append({"source_id": sid, "version": version, "title": title or "", "path": path})
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def group_key(source_ids: list[str]) -> str:
    return "\n".join(sorted(set(source_ids)))


def groups_of(files: list[dict], dismissed: set[str]) -> list[dict]:
    """Files with one hash under two or more papers, minus dismissed groups."""
    by_hash: dict[str, list[dict]] = {}
    for f in files:
        by_hash.setdefault(f["sha256"], []).append(f)
    groups = []
    for digest, same in by_hash.items():
        sids = {f["source_id"] for f in same}
        if len(sids) < 2 or group_key(list(sids)) in dismissed:
            continue
        papers = [
            {k: f[k] for k in ("source_id", "version", "title", "file", "size")}
            for f in sorted(same, key=lambda f: (f["source_id"], f["version"]))
        ]
        groups.append({"sha256": digest, "papers": papers})
    groups.sort(key=lambda g: g["papers"][0]["source_id"])
    return groups


async def scan(app: FastAPI, lib: Library, job: Job) -> dict:
    files = await asyncio.to_thread(saved_pdfs, lib.data_dir / "papers.db", lib.pdf_dir)
    cache_path = report_path(lib, CACHE)
    cache = read_report(cache_path)
    fresh: dict[str, list] = {}
    hashed = 0
    root = lib.pdf_dir.resolve()
    for f in files:
        if job.cancel_requested:
            return {"pdfs": len(files), "hashed": hashed, "cancelled": 1}
        path: Path = f["path"]
        st = path.stat()
        key = str(path)
        hit = cache.get(key)
        if isinstance(hit, list) and hit[:2] == [st.st_size, st.st_mtime_ns]:
            digest = hit[2]
        else:
            job.current = f"{lib.key}: {f['source_id']}"
            digest = await asyncio.to_thread(sha256, path)
            hashed += 1
        fresh[key] = [st.st_size, st.st_mtime_ns, digest]
        resolved = path.resolve()
        f.update(
            sha256=digest,
            size=st.st_size,
            file=str(resolved.relative_to(root)) if resolved.is_relative_to(root) else path.name,
        )
    write_report(cache_path, fresh)
    report = report_path(lib, REPORT)
    async with lock_for(report):
        dismissed = set(read_report(report).get("dismissed") or [])
        groups = groups_of(files, dismissed)
        write_report(
            report,
            {
                "scanned_at": app.state.maintenance.now().isoformat(timespec="seconds"),
                "groups": groups,
                "dismissed": sorted(dismissed),
            },
        )
    return {"pdfs": len(files), "hashed": hashed, "duplicate_groups": len(groups)}


OP = Op(
    "duplicates",
    "Find duplicate papers",
    "Hashes every saved PDF and lists papers that share the same file on the Duplicates page."
    " Only new or changed files are read again.",
    scan,
)
