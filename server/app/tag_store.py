"""Tag vocabulary and aliases for AI tagging (web-only, per library).

`<library data dir>/linxiv-web-tags.db` holds:

- `vocab`: tags imported from a CSV, with an optional weight that replaces the
  paper count when AI tagging prefers frequent tags. They join the library's own
  tags as the vocabulary; linXiv only gets a tag when a paper is tagged with it.
- `alias`: synonym -> canonical tag, keyed by `tag_norm.norm_key` of the
  synonym, so a merge is decided once and reused on every later paper.
- `alias_pending`: aliases the AI proposed, waiting for review in Settings →
  Tag vocabulary. A rejected one stays here as `rejected` so it is not proposed
  again.

The CLI does not know this file; server DB backups copy it (db_backup.py).
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .tag_norm import norm_key

if TYPE_CHECKING:
    from .libraries import Library

FILE = "linxiv-web-tags.db"
ORIGINS = ("csv", "user", "llm")
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS vocab (tag_key TEXT PRIMARY KEY, tag TEXT NOT NULL, "
    "weight REAL, added_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS alias (alias_key TEXT PRIMARY KEY, alias TEXT NOT NULL, "
    "canonical TEXT NOT NULL, origin TEXT NOT NULL, added_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS alias_pending (alias_key TEXT PRIMARY KEY, alias TEXT NOT NULL, "
    "canonical TEXT NOT NULL, source_id TEXT, model TEXT, status TEXT NOT NULL, "
    "added_at TEXT NOT NULL)",
)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _path(lib: Library) -> Path:
    return lib.data_dir / FILE


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    for sql in _SCHEMA:
        conn.execute(sql)
    return conn


def _read(path: Path, sql: str, args: tuple = ()) -> list[dict]:
    if not path.is_file():
        return []
    conn = _connect(path)
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def _write(path: Path, statements: list[tuple[str, tuple]]) -> int:
    conn = _connect(path)
    try:
        with conn:
            return sum(conn.execute(sql, args).rowcount for sql, args in statements)
    finally:
        conn.close()


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


async def vocab(lib: Library) -> list[dict]:
    """CSV vocabulary: [{tag_key, tag, weight, added_at}] by tag."""
    return await asyncio.to_thread(
        _read, _path(lib), "SELECT * FROM vocab ORDER BY tag COLLATE NOCASE"
    )


async def aliases(lib: Library) -> list[dict]:
    """[{alias_key, alias, canonical, origin, added_at}] by canonical tag, then alias."""
    return await asyncio.to_thread(
        _read,
        _path(lib),
        "SELECT * FROM alias ORDER BY canonical COLLATE NOCASE, alias COLLATE NOCASE",
    )


async def alias_map(lib: Library) -> dict[str, str]:
    """alias key -> canonical tag."""
    return {r["alias_key"]: r["canonical"] for r in await aliases(lib)}


async def pending(lib: Library) -> list[dict]:
    return await asyncio.to_thread(
        _read,
        _path(lib),
        "SELECT * FROM alias_pending WHERE status = 'pending' ORDER BY added_at, alias_key",
    )


async def proposed_keys(lib: Library) -> set[str]:
    """Alias keys already pending or rejected: not proposed again."""
    rows = await asyncio.to_thread(_read, _path(lib), "SELECT alias_key FROM alias_pending")
    return {r["alias_key"] for r in rows}


async def import_vocab(
    lib: Library,
    tags: dict[str, tuple[str, float | None]],
    alias_rows: dict[str, tuple[str, str]],
    replace: bool,
) -> dict[str, int]:
    """Store CSV tags ({key: (tag, weight)}) and aliases ({alias key: (alias,
    canonical)}). `replace` first drops the CSV vocabulary and CSV aliases; aliases
    added by hand or approved from the review queue stay. An alias never
    overrides one that is already stored."""
    stamp = now()
    statements: list[tuple[str, tuple]] = []
    if replace:
        statements += [("DELETE FROM vocab", ()), ("DELETE FROM alias WHERE origin = 'csv'", ())]
    statements += [
        ("INSERT OR REPLACE INTO vocab VALUES (?, ?, ?, ?)", (k, t, w, stamp))
        for k, (t, w) in tags.items()
    ]
    statements += [
        ("INSERT OR IGNORE INTO alias VALUES (?, ?, ?, 'csv', ?)", (k, a, c, stamp))
        for k, (a, c) in alias_rows.items()
    ]
    await asyncio.to_thread(_write, _path(lib), statements)
    return {"tags": len(tags), "aliases": len(alias_rows)}


async def add_alias(lib: Library, alias: str, canonical: str, origin: str = "user") -> str:
    """Store (or replace) one alias; returns its key. Clears a pending proposal for it."""
    key = norm_key(alias)
    await asyncio.to_thread(
        _write,
        _path(lib),
        [
            (
                "INSERT OR REPLACE INTO alias VALUES (?, ?, ?, ?, ?)",
                (key, alias, canonical, origin if origin in ORIGINS else "user", now()),
            ),
            ("DELETE FROM alias_pending WHERE alias_key = ?", (key,)),
        ],
    )
    return key


async def delete_alias(lib: Library, key: str) -> bool:
    n = await asyncio.to_thread(
        _write, _path(lib), [("DELETE FROM alias WHERE alias_key = ?", (key,))]
    )
    return n > 0


async def propose(
    lib: Library, items: Iterable[tuple[str, str]], source_id: str, model: str
) -> int:
    """Queue AI-proposed aliases (alias, canonical) for review; skips any already
    stored, pending or rejected."""
    stamp = now()
    statements = [
        (
            "INSERT OR IGNORE INTO alias_pending "
            "SELECT ?, ?, ?, ?, ?, 'pending', ? WHERE NOT EXISTS "
            "(SELECT 1 FROM alias WHERE alias_key = ?)",
            (key, alias, canonical, source_id, model, stamp, key),
        )
        for alias, canonical in items
        if (key := norm_key(alias))
    ]
    if not statements:
        return 0
    return await asyncio.to_thread(_write, _path(lib), statements)


async def resolve_pending(lib: Library, key: str, approve: bool) -> dict | None:
    """Approve (becomes an alias, origin `llm`) or reject one pending alias.
    None when there is no pending alias with that key."""
    rows = await asyncio.to_thread(
        _read,
        _path(lib),
        "SELECT * FROM alias_pending WHERE alias_key = ? AND status = 'pending'",
        (key,),
    )
    if not rows:
        return None
    row = rows[0]
    if approve:
        await add_alias(lib, row["alias"], row["canonical"], "llm")
    else:
        await asyncio.to_thread(
            _write,
            _path(lib),
            [("UPDATE alias_pending SET status = 'rejected' WHERE alias_key = ?", (key,))],
        )
    return row


async def backup_to(lib: Library, target: Path) -> bool:
    """Consistent copy of the file to `target`; False when the library has none."""
    return await asyncio.to_thread(_backup, _path(lib), target)
