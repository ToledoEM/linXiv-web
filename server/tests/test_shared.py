from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

# Multi-user fixtures (owner `boss`, user `alice`, one FakeCLI per library).
from .test_libraries import SHARED, admin, alice, app, libs  # noqa: F401
from .test_users import _csrf

IDS = ["arxiv:2401.00001", "doi:10.1234/ab.5"]


def test_user_reads_but_cannot_write_shared(admin, alice, libs):  # noqa: F811
    _ = admin.get("/api/papers", headers=SHARED)
    libs.fakes["shared"].on("paper", "delete", result={})
    h = {**_csrf(alice), **SHARED}
    assert alice.get("/api/papers", headers=SHARED).status_code == 200
    r = alice.delete("/api/papers/x", headers=h)
    assert r.status_code == 403 and "read-only" in r.json()["detail"]
    assert alice.post("/api/projects", json={"name": "p"}, headers=h).status_code == 403
    assert ["paper", "delete", "--", "x"] not in libs.fakes["shared"].calls
    # Own library: writes as usual.
    key = alice.user["library"]
    alice.get("/api/papers")
    libs.fakes[key].on("paper", "delete", result={})
    assert alice.delete("/api/papers/x", headers=_csrf(alice)).status_code == 200
    # Admins write to the shared library with the same routes.
    assert admin.delete("/api/papers/x", headers={**_csrf(admin), **SHARED}).status_code == 200
    assert ["paper", "delete", "--", "x"] in libs.fakes["shared"].calls


def test_bibtex_export_open_on_shared(admin, alice, libs):  # noqa: F811
    admin.get("/api/papers", headers=SHARED)
    libs.fakes["shared"].on("list", result=[{"source_id": "local:a", "title": "A"}])
    r = alice.post(
        "/api/export/bibtex", json={"source_ids": ["local:a"]}, headers={**_csrf(alice), **SHARED}
    )
    assert r.status_code != 403


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/logs"),
        ("get", "/api/activity"),
        ("get", "/api/update"),
        ("get", "/api/system/status"),
        ("get", "/api/mcp"),
        ("post", "/api/mcp/token"),
    ],
)
def test_server_routes_admin_only(admin, alice, fake, method, path):  # noqa: F811
    fake.on("settings", "get", result={})
    fake.on("settings", "update", result={})
    fake.on("stats", result={})
    r = getattr(alice, method)(path, headers=_csrf(alice))
    assert r.status_code == 403
    assert getattr(admin, method)(path, headers=_csrf(admin)).status_code == 200


def test_server_wide_settings(admin, alice, app, fake, libs):  # noqa: F811
    key = alice.user["library"]
    alice.get("/api/papers")
    mine: dict = {"web_log_level": "debug", "GHCR_TOKEN": "ghp_secret_value"}
    libs.fakes[key].on("settings", "get", result=lambda _: mine)
    libs.fakes[key].on("settings", "update", result=lambda a: mine.update({a[-2]: a[-1]}))
    got = alice.get("/api/settings").json()
    assert "web_log_level" not in got["settings"] and "mcp_enabled" not in got["settings"]
    assert "ghcr_token" not in got
    r = alice.patch("/api/settings", json={"web_log_level": "error"}, headers=_csrf(alice))
    assert r.status_code == 403
    ok = alice.patch("/api/settings", json={"ARXIV_MAILTO": "a@b.org"}, headers=_csrf(alice))
    assert ok.status_code == 200 and mine["ARXIV_MAILTO"] == "a@b.org"

    # Admin in the shared view: server-wide keys still read from and go to root.
    root: dict = {"web_update_check": "weekly"}
    fake.on("settings", "get", result=lambda _: root)
    fake.on("settings", "update", result=lambda a: root.update({a[-2]: a[-1]}))
    shared: dict = {}
    app.state.libraries.get("shared")
    libs.fakes["shared"].on("settings", "get", result=lambda _: shared)
    libs.fakes["shared"].on("settings", "update", result=lambda a: shared.update({a[-2]: a[-1]}))
    h = {**_csrf(admin), **SHARED}
    assert admin.get("/api/settings", headers=h).json()["settings"]["web_update_check"] == "weekly"
    body = {"web_update_check": "daily", "OPENALEX_MAILTO": "x@y.org"}
    assert admin.patch("/api/settings", json=body, headers=h).status_code == 200
    assert root["web_update_check"] == '"daily"' and "web_update_check" not in shared
    assert shared["OPENALEX_MAILTO"] == "x@y.org"


def _archive(argv) -> dict:
    path = Path(argv[-1])
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("manifest.json", "{}")
    return {"path": str(path), "project_id": 7}


def test_copy_from_shared(admin, alice, libs):  # noqa: F811
    admin.get("/api/papers", headers=SHARED)
    alice.get("/api/papers")
    src, dst = libs.fakes["shared"], libs.fakes[alice.user["library"]]
    src.on("project", "create", result={"id": 7, "name": "x"})
    src.on("project", "add-papers", result={"added": [IDS[0]], "failed": [IDS[1]]})
    src.on("project", "export", result=_archive)
    dst.on("project", "import", result={"project_id": 3, "skipped_pdfs": ["a.pdf"]})
    for f in (src, dst):
        f.on("project", "delete", result={})
        f.on("trash", "hard-delete-project", result={})
    r = alice.post("/api/shared/copy", json={"source_ids": IDS}, headers={**_csrf(alice), **SHARED})
    assert r.status_code == 200, r.text
    assert r.json() == {"copied": [IDS[0]], "failed": [IDS[1]], "skipped_pdfs": ["a.pdf"]}
    assert ["project", "add-papers", "--", "7", *IDS] in src.calls
    export = next(c for c in src.calls if c[:2] == ["project", "export"])
    assert export[2] == "--pdfs"
    imp = next(c for c in dst.calls if c[:2] == ["project", "import"])
    assert imp[2] == "--on-conflict=merge" and imp[-1] == export[-1]
    assert ["trash", "hard-delete-project", "--", "3"] in dst.calls
    assert ["trash", "hard-delete-project", "--", "7"] in src.calls
    # Temp archive removed.
    assert not Path(export[-1]).exists()


def test_copy_nothing_found_cleans_up(admin, alice, libs):  # noqa: F811
    admin.get("/api/papers", headers=SHARED)
    src = libs.fakes["shared"]
    src.on("project", "create", result={"id": 9})
    src.on("project", "add-papers", result={"added": [], "failed": IDS})
    src.on("project", "delete", result={})
    src.on("trash", "hard-delete-project", result={})
    r = alice.post("/api/shared/copy", json={"source_ids": IDS}, headers=_csrf(alice))
    assert r.status_code == 404
    assert ["trash", "hard-delete-project", "--", "9"] in src.calls


def test_copy_needs_multi_user(client):
    r = client.post("/api/shared/copy", json={"source_ids": IDS})
    assert r.status_code == 409


def test_query_param_selects_shared_and_is_guarded(admin, alice, libs):  # noqa: F811
    admin.get("/api/papers", headers=SHARED)
    libs.fakes["shared"].on("paper", "delete", result={})
    rows = alice.get("/api/papers?library=shared").json()
    assert [p["source_id"] for p in rows] == ["local:shared"]
    r = alice.delete("/api/papers/x?library=shared", headers=_csrf(alice))
    assert r.status_code == 403
