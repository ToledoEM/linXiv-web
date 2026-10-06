"""PDF folder layout: file saved PDFs into year / journal subfolders.

linXiv keeps every PDF flat in its PDF folder and stores each file's location in
`PAPER_META.PDF_PATH`; the CLI has no command to change that location. This
module moves the files itself and rewrites `PDF_PATH` directly in `papers.db`,
so linXiv (`pdf path`, `pdf delete`, project export, the reader) keeps finding
them. Layout `none` moves everything back to the flat folder.

Each move + DB update runs under the CLI lock, so no `linxiv` process touches the
database mid-move; a failed DB write moves the file back. linXiv's own storage
total only counts files directly in the PDF folder (see `storage_bytes`).
New downloads keep landing flat until the layout is applied again.
"""

from __future__ import annotations

import asyncio
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Layout = Literal["none", "year", "journal", "year/journal", "journal/year"]
LAYOUTS: tuple[Layout, ...] = ("none", "year", "journal", "year/journal", "journal/year")
UNKNOWN_YEAR = "Unknown year"
UNKNOWN_JOURNAL = "Unknown journal"
MAX_FOLDER = 80
_BAD = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]+')


@dataclass
class Move:
    source_id: str
    version: int
    paper_id: int
    src: Path
    dst: Path
    stored: str | None  # current PDF_PATH


def folder_name(raw: str | None, fallback: str) -> str:
    """A safe single path segment: no separators, control or reserved characters."""
    name = _BAD.sub(" ", raw or "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = name[:MAX_FOLDER].strip(" .")
    return name or fallback


def safe_file_name(source_id: str, version: int) -> str:
    """linXiv's managed name: `arxiv:1706.03762` v7 → `arxiv_1706.03762v7.pdf`."""
    return f"{re.sub(r'[:/]', '_', source_id)}v{version}.pdf"


def _journal(source_id: str, category: str | None, journal_ref: str | None) -> str:
    # arXiv's category (cs.CL) is a subject, not a venue.
    if source_id.startswith("arxiv:"):
        return folder_name(journal_ref, "arXiv")
    return folder_name(category or journal_ref, UNKNOWN_JOURNAL)


def subdir(layout: Layout, published: str | None, journal: str) -> Path:
    year = (published or "")[:4]
    year = year if re.fullmatch(r"\d{4}", year) and year != "0001" else UNKNOWN_YEAR
    parts = {
        "none": [],
        "year": [year],
        "journal": [journal],
        "year/journal": [year, journal],
        "journal/year": [journal, year],
    }[layout]
    return Path(*parts) if parts else Path()


class PdfLayout:
    """`db_path`: papers.db. `pdf_dir`: the PDF folder as linXiv sees it
    (`<LINXIV_DATA_DIR>/pdfs`), which is how PDF_PATH values are written."""

    def __init__(self, db_path: Path, pdf_dir: Path) -> None:
        self.db_path = db_path
        self.pdf_dir = pdf_dir

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def _inside(self, path: Path) -> bool:
        return path.resolve().is_relative_to(self.pdf_dir.resolve())

    def plan(self, layout: Layout) -> dict:
        """Every saved PDF's current file and its target under `layout`."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT p.PAPER_ID, p.SOURCE_ID, p.VERSION, p.CATEGORY, m.PUBLISHED, "
                "m.JOURNAL_REF, m.PDF_PATH FROM PAPER p JOIN PAPER_META m ON m.PAPER_ID = p.PAPER_ID "
                "WHERE p.HAS_PDF = 1 OR coalesce(m.PDF_PATH, '') <> '' ORDER BY p.SOURCE_ID, p.VERSION"
            ).fetchall()
        moves: list[Move] = []
        in_place = missing = 0
        conflicts: list[str] = []
        taken: set[Path] = set()
        for paper_id, sid, version, category, published, journal_ref, stored in rows:
            name = safe_file_name(sid, version)
            src = Path(stored) if stored and Path(stored).is_file() else self.pdf_dir / name
            if not src.is_file() or not self._inside(src):
                missing += 1
                continue
            folder = subdir(layout, published, _journal(sid, category, journal_ref))
            dst = self.pdf_dir / folder / name
            if src.resolve() == dst.resolve() and stored == str(dst):
                in_place += 1
                taken.add(dst)
                continue
            if dst in taken or (dst.exists() and dst.resolve() != src.resolve()):
                conflicts.append(
                    f"{sid} v{version}: {dst.relative_to(self.pdf_dir)} already exists"
                )
                continue
            taken.add(dst)
            moves.append(Move(sid, version, paper_id, src, dst, stored))
        return {
            "layout": layout,
            "moves": moves,
            "in_place": in_place,
            "missing": missing,
            "conflicts": conflicts,
        }

    def summary(self, plan: dict, sample: int = 10) -> dict:
        rel = self.pdf_dir

        def show(p: Path) -> str:
            return str(p.relative_to(rel)) if p.is_relative_to(rel) else str(p)

        return {
            "layout": plan["layout"],
            "to_move": len(plan["moves"]),
            "in_place": plan["in_place"],
            "missing": plan["missing"],
            "conflicts": plan["conflicts"],
            "sample": [
                {
                    "source_id": m.source_id,
                    "version": m.version,
                    "from": show(m.src),
                    "to": show(m.dst),
                }
                for m in plan["moves"][:sample]
            ],
        }

    def move_one(self, m: Move) -> None:
        """Move one file and point PDF_PATH at it; the file goes back if the DB write fails."""
        if not (self._inside(m.src) and self._inside(m.dst.parent)):
            raise ValueError(f"{m.source_id}: path outside the PDF folder")
        m.dst.parent.mkdir(parents=True, exist_ok=True)
        if m.src.resolve() != m.dst.resolve():
            if m.dst.exists():
                raise FileExistsError(f"{m.dst.relative_to(self.pdf_dir)} already exists")
            os.replace(m.src, m.dst)
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE PAPER_META SET PDF_PATH = ? WHERE PAPER_ID = ?",
                    (str(m.dst), m.paper_id),
                )
        except sqlite3.Error:
            if m.src.resolve() != m.dst.resolve():
                os.replace(m.dst, m.src)
            raise

    def prune_empty_dirs(self) -> int:
        removed = 0
        for d in sorted((p for p in self.pdf_dir.rglob("*") if p.is_dir()), reverse=True):
            try:
                d.rmdir()  # only succeeds when empty
                removed += 1
            except OSError:
                pass
        return removed


def storage_bytes(pdf_dir: Path) -> int:
    """All PDFs under the folder, subfolders included (linXiv counts only the top level)."""
    return sum(p.stat().st_size for p in pdf_dir.rglob("*.pdf") if p.is_file())


async def apply(layout_tool: PdfLayout, layout: Layout, job, lock: asyncio.Lock | None) -> None:
    """Job body: move every planned file, one at a time under the CLI lock."""
    plan = await asyncio.to_thread(layout_tool.plan, layout)
    moves: list[Move] = plan["moves"]
    job.total = len(moves)
    job.result = {
        "layout": layout,
        "moved": 0,
        "failed": 0,
        "in_place": plan["in_place"],
        "missing": plan["missing"],
        "conflicts": len(plan["conflicts"]),
    }
    job.errors.extend({"source_id": c.split(":")[0], "error": c} for c in plan["conflicts"])
    for i, m in enumerate(moves):
        if job.cancel_requested:
            break
        job.current = m.source_id
        try:
            if lock:
                async with lock:
                    layout_tool.move_one(m)
            else:
                layout_tool.move_one(m)
            job.result["moved"] += 1
        except (OSError, ValueError, sqlite3.Error) as e:
            job.result["failed"] += 1
            job.errors.append({"source_id": m.source_id, "error": str(e)})
        job.done = i + 1
    job.result["pruned_dirs"] = await asyncio.to_thread(layout_tool.prune_empty_dirs)
