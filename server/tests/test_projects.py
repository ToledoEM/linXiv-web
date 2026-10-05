from __future__ import annotations

from app.cli import CLIError

from .conftest import fixture


def test_list_defaults_to_active(client, fake):
    fake.on("project", "list", result=fixture("project-list.json"))
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json()[0]["name"] == "Disc Proj"
    assert fake.calls[-1] == ["project", "list", "--status=active"]
    client.get("/api/projects", params={"status": "archived"})
    assert fake.calls[-1] == ["project", "list", "--status=archived"]


def test_list_rejects_deleted_status(client, fake):
    """Deleted projects live in the trash listing."""
    assert client.get("/api/projects", params={"status": "deleted"}).status_code == 422
    assert fake.calls == []


def test_create(client, fake):
    fake.on("project", "create", result={"id": 7, "name": "-x", "status": "active"})
    r = client.post(
        "/api/projects",
        json={
            "name": " -x ",
            "description": "-dash",
            "color_hex": "#4f86f7",
            "project_tags": [" alpha", "beta"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == 7
    assert fake.calls[-1] == [
        "project",
        "create",
        "--description=-dash",
        "--color=#4f86f7",
        "--tags=alpha",
        "--tags=beta",
        "--",
        "-x",
    ]


def test_create_minimal(client, fake):
    fake.on("project", "create", result={"id": 1, "name": "P", "status": "active"})
    assert client.post("/api/projects", json={"name": "P"}).status_code == 200
    assert fake.calls[-1] == ["project", "create", "--description=", "--", "P"]


def test_create_validation(client, fake):
    bad = [
        {"name": ""},
        {"name": "   "},
        {"name": "P", "color_hex": "#abc"},
        {"name": "P", "color_hex": "red"},
        {"name": "P", "project_tags": [""]},
        {"name": "P", "project_tags": ["a\nb"]},
        {"name": "P", "extra": 1},
    ]
    for body in bad:
        assert client.post("/api/projects", json=body).status_code in (400, 422), body
    assert fake.calls == []


def test_update_partial(client, fake):
    fake.on("project", "update", result=fixture("project-get.json"))
    r = client.patch("/api/projects/1", json={"name": "New", "project_tags": ["a", "b"]})
    assert r.status_code == 200, r.text
    assert fake.calls[-1] == [
        "project",
        "update",
        "--name=New",
        "--tags=a",
        "--tags=b",
        "--",
        "1",
    ]


def test_update_clears_tags_and_description(client, fake):
    fake.on("project", "update", result=fixture("project-get.json"))
    client.patch("/api/projects/1", json={"description": "", "project_tags": []})
    assert fake.calls[-1] == ["project", "update", "--description=", "--tags", "--", "1"]


def test_update_bad_id(client, fake):
    assert client.patch("/api/projects/abc", json={"name": "x"}).status_code == 422
    assert fake.calls == []


def test_status_actions(client, fake):
    fake.on("project", "archive", result={"archived_project_id": 3})
    fake.on("project", "restore", result={"ok": True, "restored_project_id": 3})
    fake.on("project", "delete", result={"deleted_project_id": 3})
    assert client.post("/api/projects/3/archive").status_code == 200
    assert client.post("/api/projects/3/restore").status_code == 200
    assert client.delete("/api/projects/3").status_code == 200
    assert fake.calls == [
        ["project", "archive", "--", "3"],
        ["project", "restore", "--", "3"],
        ["project", "delete", "--", "3"],
    ]


def test_not_found(client, fake):
    fake.on("project", "archive", result=CLIError(404, "Project 99 not found"))
    r = client.post("/api/projects/99/archive")
    assert r.status_code == 404
    assert r.json()["detail"] == "Project 99 not found"


def test_get(client, fake):
    fake.on("project", "get", result=fixture("project-get.json"))
    assert client.get("/api/projects/1").json()["source_ids"][0] == "arxiv:2204.12985"
    assert fake.calls[-1] == ["project", "get", "--", "1"]


def test_project_papers_in_project_order(client, fake):
    """Members missing from `list` (trashed) are dropped."""
    project = {**fixture("project-get.json"), "source_ids": ["b", "gone", "a"]}
    fake.on("project", "get", result=project)
    fake.on("list", result=[{"source_id": s, "title": s} for s in ("a", "b", "c")])
    r = client.get("/api/projects/1/papers")
    assert [p["source_id"] for p in r.json()] == ["b", "a"]
    assert fake.calls[-1] == ["list"]


def test_project_papers_not_found(client, fake):
    fake.on("project", "get", result=CLIError(404, "Project 9 not found"))
    assert client.get("/api/projects/9/papers").status_code == 404
    assert fake.calls == [["project", "get", "--", "9"]]


def test_add_papers(client, fake):
    fake.on("project", "add-papers", result=fixture("project-add-papers-partial.json"))
    r = client.post("/api/projects/1/papers", json={"source_ids": ["nope:x", " -y "]})
    assert r.status_code == 200
    assert r.json()["failed"] == ["nope:x"]
    assert fake.calls[-1] == ["project", "add-papers", "--", "1", "nope:x", "-y"]


def test_add_papers_validation(client, fake):
    for body in ({"source_ids": []}, {"source_ids": "a"}, {"ids": ["a"]}, {"source_ids": [""]}):
        assert client.post("/api/projects/1/papers", json=body).status_code in (400, 422), body
    assert fake.calls == []


def test_remove_paper_keeps_slashes(client, fake):
    fake.on("project", "remove-paper", result={"ok": True, "paper_count": 0})
    r = client.delete("/api/projects/1/papers/arxiv:hep-th/9901001")
    assert r.status_code == 200
    assert fake.calls[-1] == ["project", "remove-paper", "--", "1", "arxiv:hep-th/9901001"]
