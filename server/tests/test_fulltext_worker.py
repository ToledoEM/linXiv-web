from __future__ import annotations

import asyncio

from app import fulltext_worker as fw
from app.cli import CLIError
from app.jobs import Job, Jobs

from .conftest import FakeCLI


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _papers(*rows):
    return [{"source_id": sid, "downloaded_source": done} for sid, done in rows]


def _worker(fake, clock=None, jobs=None):
    return fw.FullTextWorker(fake, jobs or Jobs(), 30, 120, clock=clock or Clock())


def run(coro):
    return asyncio.run(coro)


def test_off_by_default_does_nothing(fake):
    fake.on("settings", "get", result={"full_text_worker_enabled": False})
    w = _worker(fake)
    assert run(w.step()) == fw.OFF_POLL
    assert [c[:2] for c in fake.calls] == [["settings", "get"]]
    assert w.public()["enabled"] is False


def test_indexes_oldest_pending_arxiv_paper(fake):
    fake.on("settings", "get", result={"full_text_worker_enabled": True})
    fake.on(
        "list",
        result=_papers(("doi:1", False), ("arxiv:1", True), ("arxiv:2", False), ("arxiv:3", False)),
    )
    fake.on("paper", "fetch-source", result={"indexed": True})
    w = _worker(fake)
    assert run(w.step()) == fw.PACE + fw.GAP
    assert ["list", "--sort", "added", "--dir", "asc"] in fake.calls
    assert fake.calls[-1] == ["paper", "fetch-source", "--", "arxiv:2"]
    assert w.public()["indexed"] == 1 and w.public()["current"] is None


def test_failures_park_and_back_off(fake):
    clock = Clock()
    fake.on("settings", "get", result={"full_text_worker_enabled": True})
    fake.on("list", result=_papers(("arxiv:1", False), ("arxiv:2", False)))
    fake.on("paper", "fetch-source", result=CLIError(502, "arXiv API is temporarily unavailable"))
    w = _worker(fake, clock)
    first = run(w.step())
    second = run(w.step())
    fetched = [c[-1] for c in fake.calls if c[:2] == ["paper", "fetch-source"]]
    assert fetched == ["arxiv:1", "arxiv:2"]  # arxiv:1 parked, next pass moves on
    assert second > first  # doubling backoff
    assert run(w.step()) == fw.IDLE  # both parked
    clock.t += fw.RETRY_AFTER + 1
    run(w.step())
    assert [c[-1] for c in fake.calls if c[:2] == ["paper", "fetch-source"]][-1] == "arxiv:1"
    assert w.public()["failed"] == 3 and "unavailable" in w.public()["last_error"]


def test_gives_up_after_max_attempts(fake):
    clock = Clock()
    fake.on("settings", "get", result={"full_text_worker_enabled": True})
    fake.on("list", result=_papers(("arxiv:1", False)))
    fake.on("paper", "fetch-source", result=CLIError(502, "boom"))
    w = _worker(fake, clock)
    for _ in range(fw.MAX_ATTEMPTS):
        run(w.step())
        clock.t += fw.RETRY_AFTER + 1
    assert run(w.step()) == fw.IDLE
    assert w.parked["arxiv:1"].until is None


def test_no_tex_is_parked_for_the_session(fake):
    fake.on("settings", "get", result={"full_text_worker_enabled": True})
    fake.on("list", result=_papers(("arxiv:1", False)))
    fake.on("paper", "fetch-source", result={"indexed": False, "reason": "no .tex"})
    w = _worker(fake)
    run(w.step())
    assert run(w.step()) == fw.IDLE
    assert w.public()["skipped"] == 1


def test_yields_to_manual_index_job(fake):
    fake.on("settings", "get", result={"full_text_worker_enabled": True})
    jobs = Jobs()
    jobs._jobs[1] = Job(id=1, kind="index-sources")
    w = _worker(fake, jobs=jobs)
    assert run(w.step()) == fw.OFF_POLL
    assert not [c for c in fake.calls if c[0] in ("list", "paper")]


def test_wake_cuts_a_wait_short():
    async def go():
        w = _worker(FakeCLI())
        task = asyncio.create_task(w._sleep(60))
        await asyncio.sleep(0)
        w.wake()
        return await asyncio.wait_for(task, 1)

    assert run(go()) is True


def test_status_route_and_setting_wakes(client, fake):
    assert client.get("/api/sources/worker").json()["enabled"] is False
    stored: dict = {}
    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=lambda argv: stored.update({argv[-2]: argv[-1]}))
    woken = []
    client.app.state.fulltext_worker.wake = lambda: woken.append(True)
    r = client.patch("/api/settings", json={"full_text_worker_enabled": True})
    assert r.status_code == 200
    assert ["settings", "update", "--", "full_text_worker_enabled", "true"] in fake.calls
    assert woken == [True]
