"""Settings → About: release check, disk space and configuration health."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Request

from .. import logs
from ..cli import CLIError
from ..pdf_layout import storage_bytes
from .common import run, settings

router = APIRouter(prefix="/api", tags=["system"])

LOW_FREE = 0.10  # warn below 10 % free
PDF_LIMIT_WARN = 0.90  # warn at 90 % of pdf_save_limit_mb


@router.get("/update")
async def update_status(request: Request):
    """Last release check (cached; `POST /api/update/check` asks GHCR now)."""
    try:
        stored = await run(request, ["settings", "get"])
    except CLIError:
        stored = {}
    return request.app.state.update_checker.view(stored if isinstance(stored, dict) else {})


@router.post("/update/check")
async def update_check(request: Request):
    return await request.app.state.update_checker.check()


def _locations(data_dir: Path, pdf_dir: Path) -> list[tuple[str, Path, set[Path]]]:
    """(label, folder, sub-paths left out). Data skips logs/ and the pdfs link: own rows."""
    log_dir = logs.log_dir(data_dir)
    return [
        ("Data (library database, settings)", data_dir, {log_dir, data_dir / "pdfs"}),
        ("PDFs", pdf_dir, set()),
        ("Logs", log_dir, set()),
    ]


def folder_usage(path: Path, skip: set[Path]) -> tuple[int, int]:
    """(bytes, files) under `path`, symlinks not followed, `skip` paths left out."""
    total = files = 0
    stack = [path]
    while stack:
        try:
            entries = list(os.scandir(stack.pop()))
        except OSError:
            continue
        for e in entries:
            if Path(e.path) in skip:
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    stack.append(Path(e.path))
                elif e.is_file(follow_symlinks=False):
                    total += e.stat(follow_symlinks=False).st_size
                    files += 1
            except OSError:
                continue
    return total, files


def _disk(label: str, path: Path, skip: set[Path]) -> dict:
    """Space the folder uses; free/total of its filesystem feed the Health check."""
    row: dict = {"label": label, "path": str(path)}
    try:
        usage = shutil.disk_usage(path)
    except OSError as e:
        row["error"] = e.strerror or type(e).__name__
        return row
    used, files = folder_usage(path, skip)
    row.update(used=used, files=files, total=usage.total, free=usage.free)
    return row


@router.get("/system/status")
async def system_status(request: Request):
    """Space used per folder (data, PDFs, logs) plus configuration issues."""
    cfg = settings(request)
    issues: list[dict] = []
    stored: dict = {}
    try:
        out = await run(request, ["settings", "get"])
        stored = out if isinstance(out, dict) else {}
    except CLIError as e:
        issues.append({"level": "error", "message": f"linxiv CLI not responding: {e.message}"})

    disk = await asyncio.to_thread(
        lambda: [_disk(*loc) for loc in _locations(cfg.data_dir, cfg.pdf_dir)]
    )
    for row in disk:
        if row.get("error"):
            issues.append(
                {"level": "error", "message": f"{row['label']}: {row['path']} ({row['error']})"}
            )
        elif row["total"] and row["free"] / row["total"] < LOW_FREE:
            pct = row["free"] / row["total"] * 100
            issues.append(
                {"level": "warning", "message": f"{row['path']}: only {pct:.0f}% disk space free"}
            )

    for label, path in (("Data folder", cfg.data_dir), ("PDF folder", cfg.pdf_dir)):
        if not os.access(path, os.W_OK):
            issues.append({"level": "error", "message": f"{label} {path} is not writable"})

    limit_mb = stored.get("pdf_save_limit_mb")
    if isinstance(limit_mb, int) and limit_mb > 0:
        used = await asyncio.to_thread(storage_bytes, cfg.pdf_dir)
        share = used / (limit_mb * 1024 * 1024)
        if share >= PDF_LIMIT_WARN:
            issues.append(
                {
                    "level": "error" if share >= 1 else "warning",
                    "message": (
                        f"PDFs use {share * 100:.0f}% of the PDF storage limit "
                        f"({limit_mb} MB, Settings → Library)"
                    ),
                }
            )

    if stored:
        update = request.app.state.update_checker.view(stored)
        if update["update_available"]:
            msg = f"linXiv-web {update['latest']} is available (running {update['current']})"
            issues.append({"level": "info", "message": msg})

    return {"disk": disk, "issues": issues}
