from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app import fulltext_worker as fw
from app.jobs import Job, Jobs
from app.libraries import HEADER, Libraries
from app.main import create_app

from .conftest import FakeCLI
from .test_users import ALICE_PW, OWNER_PW, _csrf, _login

SHARED = {HEADER: "shared"}


class PerLibrary:
    """One FakeCLI per library key, made on first use."""

    def __init__(self) -> None:
        self.fakes: dict[str, FakeCLI] = {}
        self.dirs: dict[str, object] = {}

    def __call__(self, key, data_dir):
        self.dirs[key] = data_dir
        fake = self.fakes.setdefault(key, FakeCLI())
        fake.on("list", result=[{"source_id": f"local:{key}", "title": key}])
        return fake


@pytest.fixture
def libs():
    return PerLibrary()


@pytest.fixture
def app(settings, fake, libs):
    fake.on("list", result=[{"source_id": "local:root", "title": "root"}])
    a = create_app(replace(settings, password=OWNER_PW), fake)
    a.state.libraries.factory = libs
    return a


def _client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def admin(app):
    c = _client(app)
    assert _login(c, OWNER_PW) == 200
    r = c.post(
        "/api/admin/multi-user", json={"enabled": True, "username": "boss"}, headers=_csrf(c)
    )
    assert r.status_code == 200
    return c


@pytest.fixture
def alice(app, admin):
    r = admin.post(
        "/api/users",
        json={"username": "alice", "password": ALICE_PW, "role": "user"},
        headers=_csrf(admin),
    )
    c = _client(app)
    assert _login(c, ALICE_PW, "alice") == 200
    c.user = r.json()
    return c


def _ids(c, headers=None):
    r = c.get("/api/papers", headers=headers or {})
    assert r.status_code == 200
    return [p["source_id"] for p in r.json()]


def test_single_user_mode_ignores_header(app, settings, libs):
    c = _client(app)
    _login(c, OWNER_PW)
    assert _ids(c, SHARED) == ["local:root"]
    assert libs.fakes == {}
    assert not (settings.data_dir / "libraries").exists()


def test_owner_root_shared_and_user_libraries(admin, alice, settings, libs):
    assert _ids(admin) == ["local:root"]
    assert _ids(admin, SHARED) == ["local:shared"]
    key = alice.user["library"]
    assert _ids(alice) == [f"local:{key}"]
    assert _ids(alice, SHARED) == ["local:shared"]
    # Anything else in the header means "my own".
    assert _ids(alice, {HEADER: "root"}) == [f"local:{key}"]
    for k in ("shared", key):
        d = settings.data_dir / "libraries" / k
        assert libs.dirs[k] == d
        assert (d / "pdfs").is_dir() and d.stat().st_mode & 0o777 == 0o700


def test_list_cache_kept_per_library(admin, libs):
    _ids(admin)
    _ids(admin, SHARED)
    _ids(admin, SHARED)
    assert len([c for c in libs.fakes["shared"].calls if c[0] == "list"]) == 1
    assert _ids(admin) == ["local:root"]


def test_external_pdf_dir_links_each_library(settings, fake, tmp_path, libs):
    store = tmp_path / "usb"
    store.mkdir()
    a = create_app(replace(settings, password=OWNER_PW, libraries_pdf_dir=store), fake)
    a.state.libraries.factory = libs
    lib = a.state.libraries.get("shared")
    link = settings.data_dir / "libraries" / "shared" / "pdfs"
    assert link.is_symlink() and link.resolve() == (store / "shared").resolve()
    assert lib.pdf_dir == (store / "shared").resolve()
    # Opening again keeps the link.
    assert Libraries.get(a.state.libraries, "shared") is lib


def test_invalid_library_key(app):
    with pytest.raises(ValueError):
        app.state.libraries.get("../etc")
    with pytest.raises(ValueError):
        app.state.libraries.get("u0")


def test_pdf_view_checks_own_library_folder(admin, alice, settings, libs):
    key = alice.user["library"]
    inside = settings.data_dir / "libraries" / key / "pdfs" / "a.pdf"
    root_pdf = settings.pdf_dir / "b.pdf"
    _ids(alice)
    inside.write_bytes(b"%PDF-1.4 x")
    root_pdf.write_bytes(b"%PDF-1.4 y")
    libs.fakes[key].on("pdf", "path", result=lambda argv: {"path": str(inside)})
    assert alice.get("/api/papers/x/pdf").status_code == 200
    # A path in another library's folder is refused.
    libs.fakes[key].on("pdf", "path", result={"path": str(root_pdf)})
    assert alice.get("/api/papers/x/pdf").status_code == 403


def test_jobs_filed_per_library_and_user(app, admin, alice):
    jobs = app.state.jobs
    jobs._jobs[1] = Job(id=1, kind="index-sources", library="root", user_id=None)
    jobs._jobs[2] = Job(id=2, kind="index-sources", library="u2", user_id=alice.user["id"])
    assert [j["id"] for j in alice.get("/api/jobs").json()] == [2]
    assert alice.get("/api/jobs/1").status_code == 404
    assert alice.post("/api/jobs/1/cancel", headers=_csrf(alice)).status_code == 404
    assert alice.post("/api/jobs/2/cancel", headers=_csrf(alice)).status_code == 200
    assert {j["id"] for j in admin.get("/api/jobs").json()} == {1, 2}
    # Busy checks look at the caller's library only.
    r = alice.post("/api/backup/restore", files={"file": ("b.db", b"x")}, headers=_csrf(alice))
    assert r.status_code == 409
    jobs._jobs[2].state = "done"
    r = alice.post("/api/backup/restore", files={"file": ("b.db", b"x")}, headers=_csrf(alice))
    assert r.status_code == 400  # past the busy check: not an SQLite file


def test_job_started_in_shared_library(admin, libs):
    r = admin.post("/api/jobs/index-sources", json={"limit": 1}, headers={**_csrf(admin), **SHARED})
    assert r.status_code == 200
    assert r.json()["library"] == "shared"


def test_settings_wake_that_librarys_worker(admin, alice, app, libs):
    key = alice.user["library"]
    lib = app.state.libraries.get(key)
    stored: dict = {}
    libs.fakes[key].on("settings", "get", result=lambda _: stored)
    libs.fakes[key].on(
        "settings", "update", result=lambda argv: stored.update({argv[-2]: argv[-1]})
    )
    woken = []
    lib.worker.wake = lambda: woken.append(key)
    app.state.fulltext_worker.wake = lambda: woken.append("root")
    r = alice.patch("/api/settings", json={"full_text_worker_enabled": True}, headers=_csrf(alice))
    assert r.status_code == 200
    assert woken == [key]
    assert alice.get("/api/sources/worker").status_code == 200


def test_workers_share_one_fetch_lock(app):
    root = app.state.fulltext_worker
    other = app.state.libraries.get("shared").worker
    assert other.fetch_lock is root.fetch_lock and other.library == "shared"


def test_worker_yields_only_to_its_own_librarys_job():
    jobs = Jobs()
    fake = FakeCLI()
    fake.on("settings", "get", result={fw.SETTING: True})
    fake.on("list", result=[])
    w = fw.FullTextWorker(fake, jobs, 30, 120, library="shared")
    jobs._jobs[1] = Job(id=1, kind=fw.MANUAL_JOB_KIND, library="root")
    assert asyncio.run(w.step()) == fw.IDLE
    jobs._jobs[2] = Job(id=2, kind=fw.MANUAL_JOB_KIND, library="shared")
    assert asyncio.run(w.step()) == fw.OFF_POLL
