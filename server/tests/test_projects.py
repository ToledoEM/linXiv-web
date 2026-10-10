from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app import notes_md
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


def _writes(content: bytes, seen: list):
    """Fake `project export*`: write `content` to the dest argv, like the CLI."""

    def run(argv):
        dest = Path(argv[-1])
        dest.write_bytes(content)
        seen.append(dest)
        return {"path": str(dest), "project_id": int(argv[-2])}

    return run


def test_export_bibtex_download(client, fake):
    seen: list[Path] = []
    fake.on("project", "get", result={**fixture("project-get.json"), "name": 'My: "Proj" x'})
    fake.on("project", "export-bibtex", result=_writes(b"@article{a}\n", seen))
    r = client.get("/api/projects/1/export", params={"format": "bibtex"})
    assert r.status_code == 200, r.text
    assert r.content == b"@article{a}\n"
    assert r.headers["content-type"].startswith("application/x-bibtex")
    assert 'filename="my_proj_x.bib"' in r.headers["content-disposition"]
    assert fake.calls[-1][:4] == ["project", "export-bibtex", "--", "1"]
    assert not seen[0].parent.exists()  # temp dir removed after sending


def test_export_lxproj_with_pdfs(client, fake):
    seen: list[Path] = []
    fake.on("project", "get", result={**fixture("project-get.json"), "name": "***"})
    fake.on("project", "export", result=_writes(b"PK\x03\x04", seen))
    r = client.get("/api/projects/7/export", params={"pdfs": "true"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert 'filename="project-7.lxproj"' in r.headers["content-disposition"]
    assert fake.calls[-1][:5] == ["project", "export", "--pdfs", "--", "7"]
    assert seen[0].name == "export.lxproj"


def test_export_pdfs_flag_only_for_lxproj(client, fake):
    fake.on("project", "get", result=fixture("project-get.json"))
    fake.on("project", "export-zotero", result=_writes(b"[]", []))
    client.get("/api/projects/1/export", params={"format": "zotero", "pdfs": "true"})
    assert "--pdfs" not in fake.calls[-1]


def test_export_errors_clean_up(client, fake):
    seen: list[Path] = []

    def outside(argv):
        seen.append(Path(argv[-1]))
        return {"path": "/etc/passwd", "project_id": 1}

    fake.on("project", "get", result=fixture("project-get.json"))
    fake.on("project", "export-obsidian", result=outside)
    r = client.get("/api/projects/1/export", params={"format": "obsidian"})
    assert r.status_code == 502
    assert not seen[0].parent.exists()

    fake.on("project", "get", result=CLIError(404, "Project 9 not found"))
    assert client.get("/api/projects/9/export").status_code == 404
    assert client.get("/api/projects/1/export", params={"format": "pdf"}).status_code == 422


def _lxproj(entries: dict[str, bytes], compress=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


GOOD = {"manifest.json": b'{"project": {"name": "P"}}', "pdfs/doi:10.1/x_v1.pdf": b"%PDF-1.4"}


def test_import_preview(client, fake):
    seen = {}

    def preview(argv):
        seen["path"] = Path(argv[-1])
        seen["exists"] = seen["path"].is_file()
        return fixture("project-import-preview.json")

    fake.on("project", "import", result=preview)
    r = client.post("/api/projects/import/preview", files={"file": ("p.lxproj", _lxproj(GOOD))})
    assert r.status_code == 200, r.text
    assert r.json()["project_name"] == "Test Proej"
    assert fake.calls[-1][:4] == ["project", "import", "--preview", "--"]
    assert seen["exists"] and not seen["path"].exists()


def test_import_commit(client, fake):
    # linxiv v0.7.0 reports bundled PDFs it could not attach.
    fake.on("project", "import", result={"project_id": 7, "skipped_pdfs": ["x_v1.pdf"]})
    data = _lxproj(GOOD)
    r = client.post(
        "/api/projects/import",
        files={"file": ("p.lxproj", data)},
        data={"on_conflict": "overwrite"},
    )
    assert r.json() == {"project_id": 7, "skipped_pdfs": ["x_v1.pdf"]}
    assert fake.calls[-1][:4] == ["project", "import", "--on-conflict=overwrite", "--"]
    client.post("/api/projects/import", files={"file": ("p.lxproj", data)})
    assert fake.calls[-1][2] == "--on-conflict=merge"
    bad = client.post(
        "/api/projects/import", files={"file": ("p.lxproj", data)}, data={"on_conflict": "replace"}
    )
    assert bad.status_code == 422


def test_import_rejects_bad_archives(client, fake):
    fake.on("project", "import", result={"project_id": 1})
    cases = {
        "not a zip": b"hello",
        "no manifest": _lxproj({"x.txt": b"hi"}),
        "traversal": _lxproj({"manifest.json": b"{}", "pdfs/../../etc/x.pdf": b"x"}),
        "absolute": _lxproj({"manifest.json": b"{}", "/abs.pdf": b"x"}),
        "backslash": _lxproj({"manifest.json": b"{}", "pdfs\\..\\x.pdf": b"x"}),
    }
    for label, data in cases.items():
        r = client.post("/api/projects/import/preview", files={"file": (f"{label}.lxproj", data)})
        assert r.status_code == 400, (label, r.text)
    # 1 MB upload cap in tests; unpacked size is capped at 4x that
    big = _lxproj(
        {"manifest.json": b"{}", **{f"pdfs/{i}.pdf": b"\0" * 1_000_000 for i in range(5)}}
    )
    r = client.post("/api/projects/import/preview", files={"file": ("big.lxproj", big)})
    assert r.status_code in (400, 413), r.text
    assert fake.calls == []


def test_import_cli_rejects_manifest(client, fake):
    fake.on("project", "import", result=CLIError(502, "key must be a string at line 1 column 2"))
    r = client.post("/api/projects/import/preview", files={"file": ("p.lxproj", _lxproj(GOOD))})
    assert r.status_code == 400
    assert "not a valid .lxproj" in r.json()["detail"]


NOTES_PAPER = {
    "source_id": "arxiv:2204.12985",
    "title": 'Deep: Learning "Fast"',
    "authors": ["Ada Lovelace", "Alan Turing"],
    "doi": "10.1/xyz",
    "published": "2022-04-27",
    "url": "https://arxiv.org/pdf/2204.12985v1",
    "tags": ["machine learning", "nlp"],
}
NOTES = [
    {
        "id": 1,
        "project_id": None,
        "title": "Key idea",
        "content": "Uses $x^2$ and **bold**.\n\n",
        "created_at": "2026-10-01T09:30:00Z",
        "updated_at": "2026-10-02T10:00:00Z",
    },
    {
        "id": 2,
        "project_id": 1,
        "title": " ",
        "content": "Second.",
        "created_at": "2026-10-03T08:00:00Z",
        "updated_at": "2026-10-03T08:00:00Z",
    },
]


def test_notes_md_matches_golden():
    text = notes_md.render(NOTES_PAPER, NOTES, lambda pid: "Global" if pid is None else "Disc Proj")
    golden = (Path(__file__).parent / "fixtures" / "notes-md-golden.md").read_text()
    assert text == golden
    assert notes_md.file_name(NOTES_PAPER) == "Deep Learning Fast"
    assert notes_md.file_name({"source_id": "doi:10.1/a", "title": ""}) == "doi_10.1_a"


def test_export_notes_md_zip(client, fake):
    fake.on("project", "get", result=fixture("project-get.json"))
    fake.on("list", result=[NOTES_PAPER])
    fake.on("project", "list", result=[{"id": 1, "name": "Disc Proj"}])
    fake.on(
        "note",
        "list",
        result=lambda argv: NOTES if argv[-1] == "--paper-id=arxiv:2204.12985" else [],
    )
    r = client.get("/api/projects/1/export", params={"format": "notes-md"})
    assert r.status_code == 200, r.text
    assert 'filename="disc_proj-notes.zip"' in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert z.namelist() == ["Deep Learning Fast.md"]
    assert "*Disc Proj · created" in z.read("Deep Learning Fast.md").decode()


def test_export_notes_md_none(client, fake):
    fake.on("project", "get", result=fixture("project-get.json"))
    fake.on("list", result=[])
    fake.on("project", "list", result=[])
    fake.on("note", "list", result=[])
    r = client.get("/api/projects/1/export", params={"format": "notes-md"})
    assert r.status_code == 404
