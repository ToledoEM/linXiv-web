from __future__ import annotations

from app.cli import CLIError

from .conftest import fixture

SID = "arxiv:2204.12985"


def test_list_and_restore(client, fake):
    fake.on("trash", "list", result=fixture("trash-list.json"))
    fake.on("trash", "restore", result={"ok": True, "restored": SID})
    assert client.get("/api/trash").json()["papers"][0]["source_id"] == SID
    r = client.post(f"/api/trash/papers/{SID}/restore")
    assert r.json()["restored"] == SID
    assert fake.calls[-1] == ["trash", "restore", "--", SID]


def test_hard_delete_ok(client, fake):
    fake.on("trash", "list", result=fixture("trash-list.json"))
    fake.on("trash", "hard-delete", result={"ok": True, "hard_deleted": SID})
    r = client.delete(f"/api/trash/papers/{SID}")
    assert r.json() == {"ok": True, "hard_deleted": SID}


def test_hard_delete_not_in_trash_never_calls_cli(client, fake):
    fake.on("trash", "list", result={"papers": [], "projects": []})
    r = client.delete("/api/trash/papers/arxiv:1706.03762")
    assert r.status_code == 404
    assert ["trash", "hard-delete", "--", "arxiv:1706.03762"] not in fake.calls


def test_hard_delete_v060_not_found_quirk(client, fake):
    """v0.6.0 deletes, then exits 1 with 'not found': gone from trash means success."""
    listings = iter([fixture("trash-list.json"), {"papers": [], "projects": []}])
    fake.on("trash", "list", result=lambda _: next(listings))
    fake.on("trash", "hard-delete", result=CLIError(404, f"Paper {SID} not found"))
    r = client.delete(f"/api/trash/papers/{SID}")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "hard_deleted": SID}


def test_hard_delete_real_failure_still_errors(client, fake):
    fake.on("trash", "list", result=fixture("trash-list.json"))
    fake.on("trash", "hard-delete", result=CLIError(404, f"Paper {SID} not found"))
    assert client.delete(f"/api/trash/papers/{SID}").status_code == 404


def test_projects(client, fake):
    fake.on("trash", "restore-project", result={"ok": True, "restored_project_id": 3})
    fake.on("trash", "hard-delete-project", result={"ok": True, "hard_deleted_project_id": 3})
    assert client.post("/api/trash/projects/3/restore").status_code == 200
    assert client.delete("/api/trash/projects/3").status_code == 200
    assert fake.calls == [
        ["trash", "restore-project", "--", "3"],
        ["trash", "hard-delete-project", "--", "3"],
    ]
    assert client.delete("/api/trash/projects/abc").status_code == 422
