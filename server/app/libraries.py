"""One linXiv library per account, plus the shared library (multi-user mode).

linXiv keeps a library in one data dir (`LINXIV_DATA_DIR`: papers.db, settings,
`pdfs/`), so each library here is its own dir with its own CLI process lock:

- `root`: the existing library (`LINXIV_WEB_DATA_DIR`), the server owner's;
- `shared`: read by everyone, written by admins;
- `u<id>`: one per multi-user account.

New libraries live in `<data>/libraries/<key>/` and are created on first use
(linXiv makes papers.db on its first call). With LINXIV_WEB_LIBRARIES_PDF_DIR
set, `<key>/pdfs` links to `<that dir>/<key>` (PDFs on another disk). Library
PDF folders are never nested in the root PDF folder: its storage count is
recursive and the PDF folder layout prunes empty dirs.

Each request works on one library: the caller's own, or the shared one when the
client sends `X-Linxiv-Library: shared` (or `?library=shared` on a plain link) in
multi-user mode.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request

from .auth import LIBRARY_HEADER, SHARED_LIBRARY, current_user, wants_shared
from .cli import Runner
from .fulltext_worker import FullTextWorker
from .jobs import Jobs
from .settings import Settings
from .state_db import OWNER_LIBRARY

log = logging.getLogger(__name__)

ROOT = OWNER_LIBRARY
SHARED = SHARED_LIBRARY
HEADER = LIBRARY_HEADER
LIBRARIES_DIR = "libraries"
_KEY = re.compile(r"^(root|shared|u[1-9][0-9]{0,9})$")

RunnerFactory = Callable[[str, Path], Runner]


@dataclass
class Library:
    key: str
    data_dir: Path
    # The PDF folder as linXiv writes it is always `<data_dir>/pdfs`; for root this
    # is LINXIV_WEB_PDF_DIR (linked by entrypoint.sh).
    pdf_dir: Path
    cli: Runner
    worker: FullTextWorker

    @property
    def lock(self) -> asyncio.Lock | None:
        return getattr(self.cli, "_lock", None)


class Libraries:
    def __init__(
        self,
        settings: Settings,
        jobs: Jobs,
        factory: RunnerFactory,
        root_cli: Runner,
        root_worker: FullTextWorker,
        start_workers: bool = False,
    ) -> None:
        self.settings = settings
        self.jobs = jobs
        self.factory = factory
        self.start_workers = start_workers
        self._libs: dict[str, Library] = {
            ROOT: Library(ROOT, settings.data_dir, settings.pdf_dir, root_cli, root_worker)
        }
        self._tasks: list[asyncio.Task] = []

    def dir_for(self, key: str) -> Path:
        return self.settings.data_dir / LIBRARIES_DIR / key

    def get(self, key: str) -> Library:
        lib = self._libs.get(key)
        if lib is not None:
            return lib
        if not _KEY.fullmatch(key):
            raise ValueError(f"invalid library key {key!r}")
        data_dir = self._prepare(key)
        cli = self.factory(key, data_dir)
        s = self.settings
        worker = FullTextWorker(
            cli,
            self.jobs,
            s.timeout_short,
            s.timeout_long,
            library=key,
            fetch_lock=self._libs[ROOT].worker.fetch_lock,
        )
        lib = Library(key, data_dir, (data_dir / "pdfs").resolve(), cli, worker)
        self._libs[key] = lib
        if self.start_workers:
            self._tasks.append(asyncio.get_running_loop().create_task(worker.run()))
        log.info("library %s opened at %s", key, data_dir)
        return lib

    def _prepare(self, key: str) -> Path:
        data_dir = self.dir_for(key)
        data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        pdfs = data_dir / "pdfs"
        external = self.settings.libraries_pdf_dir
        if external is not None:
            target = external / key
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not pdfs.is_symlink() and not pdfs.exists():
                pdfs.symlink_to(target, target_is_directory=True)
        else:
            pdfs.mkdir(mode=0o700, exist_ok=True)
        return data_dir

    def opened(self) -> list[Library]:
        return list(self._libs.values())

    def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()


def library_key(request: Request) -> str:
    """Which library this request works on (see module doc)."""
    cached = getattr(request.state, "library_key", None)
    if cached:
        return cached
    user = current_user(request)
    key = user.get("library") or ROOT
    if wants_shared(request) and request.app.state.auth.multi_user():
        key = SHARED
    request.state.library_key = key
    return key


def library(request: Request) -> Library:
    key = library_key(request)
    try:
        return request.app.state.libraries.get(key)
    except OSError as exc:
        log.warning("library %s unavailable: %s", key, exc)
        raise HTTPException(status_code=503, detail=f"library {key} is unavailable") from exc
