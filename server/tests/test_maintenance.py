from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.cli import CLIError
from app.main import create_app
from app.maintenance import Maintenance, Op, library_keys


def _store(fake, stored: dict) -> dict:
    def update(argv):
        stored[argv[-2]] = json.loads(argv[-1])
        return {}

    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=update)
    return stored


async def _count(app, lib, job):
    return {"checked": 2, "note": "ok"}


async def _fails_on_shared(app, lib, job):
    if lib.key == "shared":
        raise CLIError(502, "boom")
    return {"checked": 1}


COUNT = Op("count", "Count things", "Counts.", _count)
FLAKY = Op("flaky", "Flaky", "Fails on shared.", _fails_on_shared, destructive=True)


def _app(settings, fake, ops, now=None):
    app = create_app(settings, fake)
    app.state.maintenance = Maintenance(app, ops, now=now) if now else Maintenance(app, ops)
    return app


def _wait(c: TestClient, job_id: int) -> dict:
    for _ in range(200):
        job = c.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_overview_defaults(settings, fake):
    _store(fake, {})
    with TestClient(_app(settings, fake, [COUNT, FLAKY])) as c:
        got = c.get("/api/maintenance").json()
    assert got["hour"] == 3
    assert got["nightly"] == []
    assert [o["id"] for o in got["ops"]] == ["count", "flaky"]
    assert got["ops"][1]["destructive"] is True
    assert got["ops"][0]["last"] is None and got["ops"][0]["job"] is None


def test_run_covers_every_library_and_records_status(settings, fake):
    stored = _store(fake, {})
    (settings.data_dir / "libraries" / "shared").mkdir(parents=True)
    with TestClient(_app(settings, fake, [FLAKY])) as c:
        job = c.post("/api/maintenance/flaky/run").json()
        assert job["kind"] == "maint-flaky"
        job = _wait(c, job["id"])
        assert job["state"] == "done"
        assert (job["total"], job["done"]) == (2, 2)
        assert job["result"] == {"checked": 1}
        assert job["errors"] == [{"source_id": "shared", "error": "boom"}]
        last = c.get("/api/maintenance").json()["ops"][0]["last"]
    assert last["state"] == "done" and last["errors"] == 1
    assert last["libraries"] == {"root": {"checked": 1}, "shared": {"error": "boom"}}
    assert json.loads(stored["web_maint_status"])["flaky"] == last


def test_run_unknown_and_busy(settings, fake):
    _store(fake, {})
    gate = asyncio.Event()

    async def slow(app, lib, job):
        await gate.wait()
        return {}

    app = _app(settings, fake, [Op("slow", "Slow", "", slow)])
    with TestClient(app) as c:
        assert c.post("/api/maintenance/nope/run").status_code == 404
        job = c.post("/api/maintenance/slow/run").json()
        assert c.post("/api/maintenance/slow/run").status_code == 409
        assert c.get("/api/maintenance").json()["ops"][0]["job"]["id"] == job["id"]
        c.portal.call(gate.set)
        assert _wait(c, job["id"])["state"] == "done"


def test_library_keys_skip_missing_folders(settings, fake):
    app = create_app(settings, fake)
    uid = app.state.auth.state.create_user("alice", "x" * 60, "user")
    assert library_keys(app) == ["root"]
    (settings.data_dir / "libraries" / f"u{uid}").mkdir(parents=True)
    (settings.data_dir / "libraries" / "shared").mkdir()
    assert library_keys(app) == ["root", "shared", f"u{uid}"]


def test_schedule_put(settings, fake):
    stored = _store(fake, {})
    with TestClient(_app(settings, fake, [COUNT, FLAKY])) as c:
        r = c.put("/api/maintenance/schedule", json={"hour": 2, "nightly": ["flaky", "count"]})
        assert r.status_code == 200, r.text
        want = {"hour": 2, "nightly": ["count", "flaky"], "keep_backups": 7}
        assert r.json() == want
        assert json.loads(stored["web_maint_schedule"]) == want
        # keep_backups stays unless given
        body = {"hour": 2, "nightly": [], "keep_backups": 3}
        assert c.put("/api/maintenance/schedule", json=body).json()["keep_backups"] == 3
        body = {"hour": 2, "nightly": ["flaky", "count"]}
        assert c.put("/api/maintenance/schedule", json=body).json() == {**want, "keep_backups": 3}
        body = {"hour": 2, "nightly": [], "keep_backups": 0}
        assert c.put("/api/maintenance/schedule", json=body).status_code == 422
        assert (
            c.put("/api/maintenance/schedule", json={"hour": 2, "nightly": ["x"]}).status_code
            == 400
        )
        assert (
            c.put("/api/maintenance/schedule", json={"hour": 24, "nightly": []}).status_code == 422
        )
        got = c.get("/api/maintenance").json()
    assert (got["hour"], got["nightly"]) == (2, ["count", "flaky"])


def test_nightly_runs_once_in_its_hour(settings, fake):
    stored = _store(fake, {"web_maint_schedule": json.dumps({"hour": 3, "nightly": ["count"]})})
    clock = {"now": datetime(2026, 10, 26, 3, 15, tzinfo=UTC)}
    app = _app(settings, fake, [COUNT], now=lambda: clock["now"])
    m = app.state.maintenance

    async def go():
        wait = await m.step()
        assert json.loads(stored["web_maint_status"])["count"]["libraries"] == {
            "root": {"checked": 2, "note": "ok"}
        }
        assert json.loads(stored["web_maint_status"])["nightly_on"] == "2026-10-26"
        assert wait == 3600  # next run is a day away: re-read hourly
        before = len(fake.calls)
        await m.step()  # same hour, same day: nothing runs again
        assert not any(c[:2] == ["settings", "update"] for c in fake.calls[before:])
        clock["now"] = datetime(2026, 10, 27, 2, 50, tzinfo=UTC)
        assert await m.step() == 600  # ten minutes to 03:00

    asyncio.run(go())


def test_nightly_off_outside_hour(settings, fake):
    _store(fake, {"web_maint_schedule": json.dumps({"hour": 3, "nightly": []})})
    now = datetime(2026, 10, 26, 3, 30, tzinfo=UTC)
    app = _app(settings, fake, [COUNT], now=lambda: now)
    asyncio.run(app.state.maintenance.step())
    assert not any(c[:2] == ["settings", "update"] for c in fake.calls)
