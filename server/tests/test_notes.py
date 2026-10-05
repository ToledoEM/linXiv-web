from __future__ import annotations

from app.cli import CLIError

from .conftest import fixture

SID = "arxiv:2204.12985"


def test_list_filters(client, fake):
    fake.on("note", "list", result=fixture("note-list.json"))
    assert len(client.get("/api/notes").json()) == 3
    assert fake.calls[-1] == ["note", "list"]
    client.get("/api/notes", params={"paper": SID, "project": 4})
    assert fake.calls[-1] == ["note", "list", f"--paper-id={SID}", "--project-id=4"]


def test_create(client, fake):
    fake.on("note", "create", result=fixture("note-list.json")[1])
    r = client.post(
        "/api/notes",
        json={"source_id": SID, "title": "-t", "content": "-c\nline", "project_id": 4},
    )
    assert r.status_code == 200, r.text
    assert fake.calls[-1] == [
        "note",
        "create",
        "--title=-t",
        "--project-id=4",
        "--",
        SID,
        "-c\nline",
    ]


def test_create_validation(client, fake):
    bad = [
        {"source_id": SID},
        {"source_id": SID, "title": " ", "content": "\n"},
        {"source_id": "", "content": "x"},
        {"source_id": SID, "content": "x" * 100_001},
        {"source_id": SID, "content": "é" * 50_001},
        {"source_id": SID, "content": "x", "project_id": "4"},
        {"source_id": SID, "content": "x", "extra": 1},
    ]
    for body in bad:
        assert client.post("/api/notes", json=body).status_code in (400, 422), body
    assert fake.calls == []


def test_update(client, fake):
    fake.on("note", "update", result=fixture("note-list.json")[0])
    assert client.patch("/api/notes/1", json={"content": ""}).status_code == 200
    assert fake.calls[-1] == ["note", "update", "--content=", "--", "1"]
    client.patch("/api/notes/1", json={"title": "T", "content": "C"})
    assert fake.calls[-1] == ["note", "update", "--title=T", "--content=C", "--", "1"]
    assert client.patch("/api/notes/1", json={}).status_code == 422
    assert len(fake.calls) == 2


def test_delete_and_not_found(client, fake):
    fake.on("note", "delete", result={"deleted_note_id": 3})
    assert client.delete("/api/notes/3").json() == {"deleted_note_id": 3}
    fake.on("note", "delete", result=CLIError(404, "Note 3 not found"))
    assert client.delete("/api/notes/3").status_code == 404
    assert client.delete("/api/notes/x").status_code == 422
