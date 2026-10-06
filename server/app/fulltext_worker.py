"""Background full-text indexer (desktop `linxiv_server::full_text_worker`).

While the linXiv setting `full_text_worker_enabled` is on (off by default), it
walks the saved arXiv papers that have no TeX source yet, oldest first, and
runs `paper fetch-source` for one at a time. Each fetch is its own CLI call, so
the CLI lock is free between papers. Desktop's pacing and retry rules apply:

- a gap between papers on top of arXiv's ~7 s spacing;
- a paper whose fetch failed is parked for RETRY_AFTER, and left alone for the
  rest of this server run after MAX_ATTEMPTS failures or when it has no TeX;
- failures in a row back off (doubling, capped at MAX_BACKOFF), since being
  offline or rate-limited fails every paper alike.

The setting is re-read at least every OFF_POLL; `wake()` (called when the
setting changes) cuts any wait short. It yields while a manual `index-sources`
job runs. State is in memory: a restart forgets parked papers.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass

from .cli import CLIError, Runner
from .jobs import Jobs

SETTING = "full_text_worker_enabled"
MANUAL_JOB_KIND = "index-sources"
OFF_POLL = 60.0
IDLE = 300.0
PACE = 7.0
GAP = 15.0
RETRY_AFTER = 600.0
MAX_ATTEMPTS = 5
MAX_BACKOFF = 3600.0


@dataclass
class Park:
    attempts: int
    until: float | None  # None: not again this run


@dataclass
class WorkerStatus:
    enabled: bool = False
    current: str | None = None
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    parked: int = 0
    last_error: str | None = None
    last_fetch_at: float | None = None


class FullTextWorker:
    def __init__(
        self,
        cli: Runner,
        jobs: Jobs,
        timeout_short: float,
        timeout_long: float,
        clock=time.monotonic,
    ) -> None:
        self.cli = cli
        self.jobs = jobs
        self.timeout_short = timeout_short
        self.timeout_long = timeout_long
        self.clock = clock
        self.status = WorkerStatus()
        self.parked: dict[str, Park] = {}
        self.consecutive_failures = 0
        self._wake = asyncio.Event()

    def public(self) -> dict:
        return asdict(self.status)

    def wake(self) -> None:
        self._wake.set()

    async def _enabled(self) -> bool:
        try:
            out = await self.cli(["settings", "get"], self.timeout_short)
        except CLIError:
            return False
        on = isinstance(out, dict) and out.get(SETTING) is True
        self.status.enabled = on
        return on

    async def _sleep(self, seconds: float) -> bool:
        """Sleep; True when `wake()` cut it short."""
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=max(0.0, seconds))
        except TimeoutError:
            return False
        finally:
            self._wake.clear()
        return True

    async def _nap(self, total: float) -> None:
        """Wait `total` in OFF_POLL steps; stop early on wake or once the setting is off."""
        end = self.clock() + total
        while (left := end - self.clock()) > 0:
            if await self._sleep(min(OFF_POLL, left)) or not await self._enabled():
                return

    async def _queue(self) -> list[str]:
        papers = await self.cli(["list", "--sort", "added", "--dir", "asc"], self.timeout_long)
        now = self.clock()
        out = []
        for p in papers if isinstance(papers, list) else []:
            sid = str(p.get("source_id", ""))
            if not sid.startswith("arxiv:") or p.get("downloaded_source"):
                continue
            park = self.parked.get(sid)
            if park and (park.until is None or park.until > now):
                continue
            out.append(sid)
        return out

    def _park(self, sid: str, permanent: bool = False) -> None:
        prev = self.parked.get(sid)
        attempts = (prev.attempts if prev else 0) + 1
        until = None if permanent or attempts >= MAX_ATTEMPTS else self.clock() + RETRY_AFTER
        self.parked[sid] = Park(attempts, until)
        self.status.parked = len(self.parked)

    async def step(self) -> float:
        """One pass: fetch at most one paper. Returns how long to wait before the next."""
        if not await self._enabled():
            self.status.current = None
            return OFF_POLL
        if self.jobs.running(MANUAL_JOB_KIND):
            return OFF_POLL
        try:
            queue = await self._queue()
        except CLIError as e:
            self.status.last_error = e.message
            return OFF_POLL
        if not queue:
            return IDLE
        sid = queue[0]
        self.status.current = sid
        try:
            out = await self.cli(["paper", "fetch-source", "--", sid], self.timeout_long)
            if isinstance(out, dict) and out.get("indexed"):
                self.status.indexed += 1
            else:
                # Fetched but nothing to index (PDF-only submission): not again this run.
                self.status.skipped += 1
                self._park(sid, permanent=True)
            self.consecutive_failures = 0
            wait = PACE + GAP
        except CLIError as e:
            self.status.failed += 1
            self.status.last_error = f"{sid}: {e.message}"
            # Not arXiv-hosted TeX at all: retrying can't help.
            self._park(sid, permanent="only published by arXiv" in e.message)
            self.consecutive_failures += 1
            wait = min(GAP * 2**self.consecutive_failures, MAX_BACKOFF)
        finally:
            self.status.current = None
            self.status.last_fetch_at = time.time()
        return wait

    async def run(self) -> None:
        while True:
            try:
                wait = await self.step()
            except Exception as e:  # noqa: BLE001 - keep the loop alive, report it
                self.status.last_error = str(e) or type(e).__name__
                wait = OFF_POLL
            if self.status.enabled:
                await self._nap(wait)
            else:
                await self._sleep(OFF_POLL)
