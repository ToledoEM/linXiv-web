"""Maintenance operations (Settings → Server Admin → Maintenance operations).

Each operation runs over every library on the server (root, shared and each
account's, when their folders exist) as one background job, `maint-<id>`, on
demand or each night at the configured hour. Times are the server's local time
(the container's `TZ`).

The schedule and the last result per operation live in two web-only settings of
the root library, JSON strings that are never PATCHable through /api/settings:
`web_maint_schedule` ({hour, nightly: [op ids]}) and `web_maint_status`
({op id: {started_at, finished_at, state, libraries: {key: summary}}, nightly_on}).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .cli import CLIError
from .jobs import Job

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .libraries import Library

log = logging.getLogger(__name__)

KIND_PREFIX = "maint-"
SCHEDULE_SETTING = "web_maint_schedule"
STATUS_SETTING = "web_maint_status"
DEFAULT_HOUR = 3
MAX_WAIT = 3600  # schedule re-read at least hourly (PUT /schedule wakes it sooner)
MAINT_DIR = "maintenance"
SHARED = "shared"
ROOT = "root"

# (app, library, job) -> summary of what it did in that library (JSON-able).
Work = Callable[["FastAPI", "Library", Job], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Op:
    id: str
    label: str
    description: str
    run: Work
    # Deletes or changes data: the panel asks before Run.
    destructive: bool = False

    def public(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "destructive": self.destructive,
        }


def _now() -> datetime:
    return datetime.now().astimezone()


def _parse(raw: Any) -> dict:
    try:
        data = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        data = None
    return data if isinstance(data, dict) else {}


_report_locks: dict[Path, asyncio.Lock] = {}


def report_lock(path: Path) -> asyncio.Lock:
    """One read-modify-write at a time per report file (an operation's run and the
    page acting on its result)."""
    return _report_locks.setdefault(path, asyncio.Lock())


def report_path(lib: Library, name: str) -> Path:
    """`<library data dir>/maintenance/<name>`: where operations keep their results."""
    folder = lib.data_dir / MAINT_DIR
    folder.mkdir(mode=0o700, exist_ok=True)
    return folder / name


def read_report(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_report(path: Path, data: dict) -> None:
    """Whole-file replace, so a reader never sees half a report."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def library_keys(app: FastAPI) -> list[str]:
    """Root, then shared and each account's library whose folder exists (an
    account that never logged in has none; maintenance does not create it)."""
    libs = app.state.libraries
    keys = [ROOT]
    users = app.state.auth.state.list_users()
    for key in (SHARED, *(str(u.get("library") or "") for u in users)):
        if key and key not in keys and libs.dir_for(key).is_dir():
            keys.append(key)
    return keys


class Maintenance:
    def __init__(self, app: FastAPI, ops: list[Op], now: Callable[[], datetime] = _now) -> None:
        self.app = app
        self.ops = {op.id: op for op in ops}
        self.now = now
        self._wake = asyncio.Event()
        self._write = asyncio.Lock()

    # -- stored state -------------------------------------------------------

    @property
    def _cli(self):
        return self.app.state.cli

    @property
    def _timeout(self) -> float:
        return self.app.state.settings.timeout_short

    async def stored(self) -> dict:
        out = await self._cli(["settings", "get"], self._timeout)
        return out if isinstance(out, dict) else {}

    async def _save(self, key: str, value: dict) -> None:
        await self._cli(
            ["settings", "update", "--", key, json.dumps(json.dumps(value))], self._timeout
        )

    def schedule_from(self, stored: dict) -> dict:
        raw = _parse(stored.get(SCHEDULE_SETTING))
        hour = raw.get("hour")
        nightly = raw.get("nightly")
        return {
            "hour": hour if isinstance(hour, int) and 0 <= hour <= 23 else DEFAULT_HOUR,
            "nightly": [i for i in self.ops if isinstance(nightly, list) and i in nightly],
        }

    async def schedule(self) -> dict:
        return self.schedule_from(await self.stored())

    async def set_schedule(self, hour: int, nightly: list[str]) -> dict:
        value = {"hour": hour, "nightly": [i for i in self.ops if i in nightly]}
        async with self._write:
            await self._save(SCHEDULE_SETTING, value)
        self.wake()
        return value

    async def status(self) -> dict:
        return self.status_from(await self.stored())

    def status_from(self, stored: dict) -> dict:
        return _parse(stored.get(STATUS_SETTING))

    async def _update_status(self, change: Callable[[dict], None]) -> None:
        # Read-modify-write: two operations may finish at the same time.
        async with self._write:
            status = await self.status()
            change(status)
            await self._save(STATUS_SETTING, status)

    # -- running ------------------------------------------------------------

    def running(self, op_id: str) -> Job | None:
        return self.app.state.jobs.running(KIND_PREFIX + op_id)

    def start(self, op_id: str, user_id: int | None = None) -> Job:
        """Start one operation over every library; JobBusy while it already runs."""
        op = self.ops[op_id]
        return self.app.state.jobs.start(
            KIND_PREFIX + op.id, lambda job: self._run(op, job), ROOT, user_id
        )

    async def _run(self, op: Op, job: Job) -> None:
        started = self.now().isoformat(timespec="seconds")
        keys = library_keys(self.app)
        job.total = len(keys)
        summary: dict[str, dict] = {}
        totals: dict[str, int] = {}
        for key in keys:
            if job.cancel_requested:
                break
            job.current = key
            try:
                lib = self.app.state.libraries.get(key)
                out = await op.run(self.app, lib, job)
            except (CLIError, OSError) as e:
                msg = getattr(e, "message", None) or str(e) or type(e).__name__
                out = {"error": msg}
                job.errors.append({"source_id": key, "error": msg})
                log.warning("maintenance %s on %s failed: %s", op.id, key, msg)
            summary[key] = out
            for k, v in out.items():
                if isinstance(v, int) and not isinstance(v, bool):
                    totals[k] = totals.get(k, 0) + v
            job.result = dict(totals)
            job.done += 1
        state = "cancelled" if job.cancel_requested else "done"
        record = {
            "started_at": started,
            "finished_at": self.now().isoformat(timespec="seconds"),
            "state": state,
            "errors": len(job.errors),
            "libraries": summary,
        }
        await self._update_status(lambda s: s.__setitem__(op.id, record))

    # -- nightly ------------------------------------------------------------

    def wake(self) -> None:
        self._wake.set()

    def _next_run(self, now: datetime, hour: int) -> datetime:
        at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        return at if at > now else at + timedelta(days=1)

    async def step(self) -> float:
        """One loop turn: run the nightly operations once during the set hour;
        seconds to sleep next."""
        try:
            stored = await self.stored()
        except CLIError:
            return MAX_WAIT
        sched = self.schedule_from(stored)
        now = self.now()
        today = now.date().isoformat()
        status = self.status_from(stored)
        if sched["nightly"] and now.hour == sched["hour"] and status.get("nightly_on") != today:
            await self._update_status(lambda s: s.__setitem__("nightly_on", today))
            await self.run_nightly(sched["nightly"])
            now = self.now()
        wait = (self._next_run(now, sched["hour"]) - now).total_seconds()
        return max(1.0, min(wait, MAX_WAIT))

    async def run_nightly(self, op_ids: list[str]) -> None:
        """One operation after another, so they never share a library at once."""
        jobs = self.app.state.jobs
        for op_id in op_ids:
            busy = self.running(op_id)
            try:
                job = busy or self.start(op_id)
            except Exception:
                log.exception("nightly maintenance %s could not start", op_id)
                continue
            await jobs.wait(job.id)

    async def run(self) -> None:
        while True:
            try:
                wait = await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("maintenance scheduler step failed")
                wait = MAX_WAIT
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=wait)
            except TimeoutError:
                pass
            finally:
                self._wake.clear()
