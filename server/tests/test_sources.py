from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.cli import CLIError
from app.main import create_app
from app.routes import sources

SID = "arxiv:2204.12985"
LIBRARY = [
    {"source_id": "arxiv:1", "downloaded_source": False},
    {"source_id": "arxiv:2", "downloaded_source": True},
    {"source_id": "local:x", "downloaded_source": False},
    {"source_id": "arxiv:3", "downloaded_source": False},
    {"source_id": "arxiv:4", "downloaded_source": False},
]


def test_fetch_source(client, fake):
    fake.on("paper", "fetch-source", result={"source_id": SID, "indexed": True, "chars": 9})
    assert client.post(f"/api/papers/{SID}/source").json()["indexed"] is True
    assert fake.calls[-1] == ["paper", "fetch-source", "--", SID]
    client.post(f"/api/papers/{SID}/source", json={"force": True})
    assert fake.calls[-1] == ["paper", "fetch-source", "--force", "--", SID]


def test_fetch_source_not_arxiv_is_400(client, fake):
    msg = "TeX source is only published by arXiv; local:x is not an arXiv paper"
    fake.on("paper", "fetch-source", result=CLIError(502, msg))
    r = client.post("/api/papers/local:x/source")
    assert (r.status_code, r.json()["detail"]) == (400, msg)


def test_pending(client, fake):
    fake.on("list", result=LIBRARY)
    assert client.get("/api/sources/pending").json() == {"pending": 3, "arxiv_papers": 4}


def _wait(c: TestClient, job_id: int, state: str = "running") -> dict:
    for _ in range(200):
        job = c.get(f"/api/jobs/{job_id}").json()
        if job["state"] != state:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(sources, "PACE_SECONDS", 0.0)


def test_index_job_runs_each_pending_paper(settings, fake, fast):
    fake.on("list", result=LIBRARY)

    def fetch(argv):
        sid = argv[-1]
        if sid == "arxiv:3":
            raise CLIError(502, "arXiv API is temporarily unavailable")
        return {"source_id": sid, "indexed": sid == "arxiv:1", "reason": "no .tex"}

    fake.on("paper", "fetch-source", result=fetch)
    with TestClient(create_app(settings, fake)) as c:
        job = c.post("/api/jobs/index-sources", json={"limit": 10}).json()
        assert job["kind"] == "index-sources"
        job = _wait(c, job["id"])
        assert job["state"] == "done"
        assert (job["total"], job["done"]) == (3, 3)
        assert job["result"] == {"indexed": 1, "skipped": 1, "failed": 1}
        assert job["errors"] == [
            {"source_id": "arxiv:3", "error": "arXiv API is temporarily unavailable"}
        ]
        assert [c[-1] for c in fake.calls if c[:2] == ["paper", "fetch-source"]] == [
            "arxiv:1",
            "arxiv:3",
            "arxiv:4",
        ]
        assert c.get("/api/jobs", params={"kind": "index-sources"}).json()[0]["id"] == job["id"]


def test_index_job_limit_busy_and_cancel(settings, fake, monkeypatch):
    monkeypatch.setattr(sources, "PACE_SECONDS", 30.0)
    fake.on("list", result=LIBRARY)
    fake.on("paper", "fetch-source", result={"indexed": True})
    with TestClient(create_app(settings, fake)) as c:
        job = c.post("/api/jobs/index-sources", json={"limit": 2}).json()
        for _ in range(100):
            if c.get(f"/api/jobs/{job['id']}").json()["done"] == 1:
                break
            time.sleep(0.02)
        r = c.post("/api/jobs/index-sources")
        assert r.status_code == 409
        c.post(f"/api/jobs/{job['id']}/cancel")
        job = _wait(c, job["id"])
        assert (job["state"], job["total"], job["done"]) == ("cancelled", 2, 1)
        assert c.get("/api/jobs/999").status_code == 404
        assert c.post("/api/jobs/index-sources", json={"limit": 0}).status_code == 422


def test_index_job_failure_is_reported(settings, fake, fast):
    fake.on("list", result=CLIError(504, "linxiv list timed out after 120s"))
    with TestClient(create_app(settings, fake)) as c:
        job = _wait(c, c.post("/api/jobs/index-sources").json()["id"])
        assert (job["state"], job["error"]) == ("failed", "linxiv list timed out after 120s")
