"""In-process background jobs for work that takes minutes (many CLI calls).

A job runs as an asyncio task on the server's event loop. Each step makes its
own CLI call, so the CLI lock is released between steps and the rest of the
API stays responsive. State lives in memory: a restart forgets finished jobs
and stops a running one.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

log = logging.getLogger(__name__)
State = Literal["running", "done", "failed", "cancelled"]
KEEP_FINISHED = 20


@dataclass
class Job:
    id: int
    kind: str
    state: State = "running"
    total: int = 0
    done: int = 0
    current: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    cancel_requested: bool = False
    # Which library it works on, and who started it (None: single-user mode).
    library: str = "root"
    user_id: int | None = None

    def public(self) -> dict[str, Any]:
        return asdict(self)


class JobBusy(Exception):
    def __init__(self, job: Job) -> None:
        super().__init__(f"a {job.kind} job is already running")
        self.job = job


class Jobs:
    def __init__(self) -> None:
        self._jobs: dict[int, Job] = {}
        self._tasks: dict[int, asyncio.Task] = {}
        self._ids = itertools.count(1)

    def get(self, job_id: int) -> Job | None:
        return self._jobs.get(job_id)

    def list(self, kind: str | None = None, library: str | None = None) -> list[Job]:
        jobs = [
            j
            for j in self._jobs.values()
            if (kind is None or j.kind == kind) and (library is None or j.library == library)
        ]
        return sorted(jobs, key=lambda j: j.id, reverse=True)

    def running(self, kind: str | None, library: str | None = None) -> Job | None:
        """A running job of `kind` (any kind when None) in `library` (any when None)."""
        return next((j for j in self.list(kind, library) if j.state == "running"), None)

    def start(
        self,
        kind: str,
        work: Callable[[Job], Awaitable[None]],
        library: str = "root",
        user_id: int | None = None,
    ) -> Job:
        """Start `work(job)` unless a job of the same kind runs on the same library."""
        if busy := self.running(kind, library):
            raise JobBusy(busy)
        job = Job(id=next(self._ids), kind=kind, library=library, user_id=user_id)
        self._jobs[job.id] = job
        self._tasks[job.id] = asyncio.get_running_loop().create_task(self._run(job, work))
        self._prune()
        log.info("job %d %s started", job.id, job.kind)
        return job

    def cancel(self, job_id: int) -> Job | None:
        job = self._jobs.get(job_id)
        if job and job.state == "running":
            # Cooperative: the job stops before its next step.
            job.cancel_requested = True
        return job

    async def _run(self, job: Job, work: Callable[[Job], Awaitable[None]]) -> None:
        try:
            await work(job)
            job.state = "cancelled" if job.cancel_requested else "done"
        except asyncio.CancelledError:
            job.state = "cancelled"
            raise
        except Exception as e:
            job.state = "failed"
            job.error = str(e) or type(e).__name__
            log.exception("job %d %s failed", job.id, job.kind)
        finally:
            job.current = None
            job.finished_at = time.time()
            self._tasks.pop(job.id, None)
            log.info(
                "job %d %s %s in %.1f s (%d/%d done, %d errors)",
                job.id,
                job.kind,
                job.state,
                job.finished_at - job.started_at,
                job.done,
                job.total,
                len(job.errors),
            )
            for err in job.errors[:20]:
                log.warning("job %d %s: %s", job.id, job.kind, err)

    def _prune(self) -> None:
        finished = [j for j in self.list() if j.state != "running"]
        for j in finished[KEEP_FINISHED:]:
            self._jobs.pop(j.id, None)
