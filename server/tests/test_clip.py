"""Browser add-on: token, automatic list, imports that leave stored records alone."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cli import CLIError
from app.libraries import HEADER
from app.main import create_app

from .conftest import FakeCLI
from .test_libraries import PerLibrary
from .test_users import ALICE_PW, OWNER_PW, _csrf, _login

PDF = b"%PDF-1.4 test"
EXT = "moz-extension://1234-abcd"


def _bearer(token: str, origin: str | None = EXT) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if origin:
        headers["Origin"] = origin
    return headers


def _library(fake: FakeCLI) -> None:
    """Answers for an empty library with a working list."""
    store: dict = {}
    fake.on("settings", "get", result=lambda _: dict(store))

    def update(args):
        store[args[-2]] = int(args[-1])

    fake.on("settings", "update", result=update)
    fake.on("list", result=[])
    fake.on("paper", "get", result=CLIError(404, "Paper not found"))
    fake.on("project", "create", result={"id": 7, "name": "x", "status": "active"})
    fake.on("project", "get", result={"id": 7, "status": "active", "source_ids": []})
    fake.on("project", "add-papers", result={"ok": True, "added": [], "failed": []})
    fake.on("pdf", "import", result={"source_id": "doi:10.1/a", "title": "A"})
    fake.on("bibtex", "import", result={"saved_count": 1, "source_ids": ["doi:10.1234/new"]})


@pytest.fixture
def token(client, fake) -> str:
    _library(fake)
    return client.post("/api/clip/token").json()["token"]


def _calls(fake: FakeCLI, *prefix: str) -> list[list[str]]:
    return [c for c in fake.calls if tuple(c[: len(prefix)]) == prefix]


def _clip_pdf(client, token: str):
    return client.post("/api/clip/pdf", files={"file": ("a.pdf", PDF)}, headers=_bearer(token))


def _clip_bib(client, token: str, text: str):
    return client.post(
        "/api/clip/bibtex", files={"file": ("a.bib", text.encode())}, headers=_bearer(token)
    )


# --- token -------------------------------------------------------------------


def test_token_shown_once_and_only_hash_stored(client, fake, settings):
    created = client.post("/api/clip/token").json()
    assert created["token"].startswith("lxclip_")
    status = client.get("/api/clip/token").json()
    assert status == {"set": True, "hint": created["hint"], "created": created["created"]}
    assert "token" not in status
    raw = (settings.data_dir / "linxiv-web-state.db").read_bytes()
    assert created["token"].encode() not in raw


def test_ping_needs_a_valid_token(client, token):
    assert client.get("/api/clip/ping").status_code == 401
    bad = client.get("/api/clip/ping", headers=_bearer("lxclip_wrong"))
    assert bad.status_code == 401
    assert bad.headers["www-authenticate"] == "Bearer"
    assert client.get("/api/clip/ping", headers={"Authorization": token}).status_code == 401
    ok = client.get("/api/clip/ping", headers=_bearer(token))
    assert ok.status_code == 200
    assert ok.json()["ok"] is True


def test_replaced_and_revoked_tokens_stop_working(client, token):
    newer = client.post("/api/clip/token").json()["token"]
    assert client.get("/api/clip/ping", headers=_bearer(token)).status_code == 401
    assert client.get("/api/clip/ping", headers=_bearer(newer)).status_code == 200
    assert client.delete("/api/clip/token").status_code == 200
    assert client.get("/api/clip/ping", headers=_bearer(newer)).status_code == 401
    assert client.get("/api/clip/token").json()["set"] is False


@pytest.mark.parametrize("origin", ["https://evil.example", "http://testserver", "null"])
def test_web_page_origins_refused_even_with_the_token(client, token, origin):
    r = client.get("/api/clip/ping", headers=_bearer(token, origin))
    assert r.status_code == 403


def test_no_origin_passes(client, token):
    assert client.get("/api/clip/ping", headers=_bearer(token, None)).status_code == 200


def test_session_routes_still_refuse_the_addon(client, token):
    r = client.post("/api/projects", json={"name": "x"}, headers=_bearer(token))
    assert r.status_code == 403


def test_token_opens_clip_routes_only(auth_client, fake):
    _library(fake)
    assert _login(auth_client, "hunter2") == 200
    r = auth_client.post("/api/clip/token", headers=_csrf(auth_client))
    token = r.json()["token"]
    addon = TestClient(auth_client.app)
    assert addon.get("/api/clip/ping", headers=_bearer(token)).status_code == 200
    assert addon.get("/api/papers", headers=_bearer(token, None)).status_code == 401
    assert addon.get("/api/clip/token", headers=_bearer(token, None)).status_code == 401


def test_setup_mode_refuses(settings, fake):
    c = TestClient(create_app(replace(settings, host="0.0.0.0"), fake))  # noqa: S104
    assert c.get("/api/clip/ping", headers=_bearer("lxclip_x")).status_code == 403


# --- accounts and libraries --------------------------------------------------


@pytest.fixture
def multi(settings, fake):
    """Owner and alice logged in, each library with its own fake."""
    libs = PerLibrary()
    _library(fake)
    app = create_app(replace(settings, password=OWNER_PW), fake)
    app.state.libraries.factory = libs
    owner = TestClient(app)
    assert _login(owner, OWNER_PW) == 200
    owner.post(
        "/api/admin/multi-user", json={"enabled": True, "username": "boss"}, headers=_csrf(owner)
    )
    user = owner.post(
        "/api/users",
        json={"username": "alice", "password": ALICE_PW, "role": "user"},
        headers=_csrf(owner),
    ).json()
    alice = TestClient(app)
    assert _login(alice, ALICE_PW, "alice") == 200
    token = alice.post("/api/clip/token", headers=_csrf(alice)).json()["token"]
    library = user["library"]
    _library(libs(library, settings.data_dir))
    return {
        "app": app,
        "owner": owner,
        "alice": alice,
        "user": user,
        "token": token,
        "libs": libs,
        "fake": fake,
    }


def test_clip_writes_to_token_owners_library(multi):
    addon = TestClient(multi["app"])
    r = _clip_pdf(addon, multi["token"])
    assert r.status_code == 200
    mine = multi["libs"].fakes[multi["user"]["library"]]
    assert _calls(mine, "project", "add-papers")
    assert not _calls(multi["fake"], "project", "add-papers")


def test_shared_header_cannot_reach_the_shared_library(multi):
    addon = TestClient(multi["app"])
    headers = {**_bearer(multi["token"]), HEADER: "shared"}
    r = addon.post("/api/clip/pdf", files={"file": ("a.pdf", PDF)}, headers=headers)
    assert r.status_code == 200
    shared = multi["libs"].fakes.get("shared")
    assert shared is None or not _calls(shared, "project", "add-papers")
    assert _calls(multi["libs"].fakes[multi["user"]["library"]], "project", "add-papers")


def test_token_of_two_accounts_are_separate(multi):
    owner = multi["owner"]
    assert owner.get("/api/clip/token").json()["set"] is False
    multi["alice"].delete("/api/clip/token", headers=_csrf(multi["alice"]))
    assert (
        TestClient(multi["app"]).get("/api/clip/ping", headers=_bearer(multi["token"])).status_code
        == 401
    )


def test_deleted_account_loses_its_token(multi):
    owner = multi["owner"]
    r = owner.delete(f"/api/users/{multi['user']['id']}", headers=_csrf(owner))
    assert r.status_code < 300
    addon = TestClient(multi["app"])
    assert addon.get("/api/clip/ping", headers=_bearer(multi["token"])).status_code == 401


def test_multi_user_off_ends_named_tokens(multi):
    owner = multi["owner"]
    owner.post("/api/admin/multi-user", json={"enabled": False}, headers=_csrf(owner))
    addon = TestClient(multi["app"])
    assert addon.get("/api/clip/ping", headers=_bearer(multi["token"])).status_code == 401


def test_owner_token_survives_multi_user_on(settings, fake):
    _library(fake)
    app = create_app(replace(settings, password=OWNER_PW), fake)
    owner = TestClient(app)
    assert _login(owner, OWNER_PW) == 200
    token = owner.post("/api/clip/token", headers=_csrf(owner)).json()["token"]
    owner.post(
        "/api/admin/multi-user", json={"enabled": True, "username": "boss"}, headers=_csrf(owner)
    )
    r = TestClient(app).get("/api/clip/ping", headers=_bearer(token))
    assert r.status_code == 200
    assert r.json()["username"] == "boss"


# --- list --------------------------------------------------------------------


def test_list_created_once_and_tagged(client, fake, token):
    assert client.get("/api/clip/list").json() == {"project_id": None}
    assert _clip_pdf(client, token).json()["project_id"] == 7
    assert _clip_pdf(client, token).json()["project_id"] == 7
    made = _calls(fake, "project", "create")
    assert made == [["project", "create", "--tags=reading-list", "--", "Imported - to check"]]
    assert client.get("/api/clip/list").json() == {"project_id": 7}


def test_renamed_list_is_kept(client, fake, token):
    _clip_pdf(client, token)
    fake.on("project", "get", result={"id": 7, "name": "Renamed", "status": "active"})
    _clip_pdf(client, token)
    assert len(_calls(fake, "project", "create")) == 1


@pytest.mark.parametrize(
    "gone",
    [CLIError(404, "Project 7 not found"), {"id": 7, "status": "archived"}],
    ids=["deleted", "archived"],
)
def test_gone_list_is_replaced(client, fake, token, gone):
    _clip_pdf(client, token)
    fake.on("project", "get", result=gone)
    fake.on("project", "create", result={"id": 8, "status": "active"})
    assert _clip_pdf(client, token).json()["project_id"] == 8


def test_concurrent_clips_make_one_list(settings):
    state: dict = {}
    calls: list[list[str]] = []

    async def cli(args, timeout, raw=False):
        calls.append(args)
        await asyncio.sleep(0)
        if args[:2] == ["settings", "get"]:
            return dict(state)
        if args[:2] == ["settings", "update"]:
            state[args[-2]] = int(args[-1])
            return None
        if args[:2] == ["paper", "get"]:
            raise CLIError(404, "not found")
        if args[:2] == ["project", "create"]:
            return {"id": 7, "status": "active"}
        if args[:2] == ["project", "get"]:
            return {"id": 7, "status": "active"}
        if args[:2] == ["project", "add-papers"]:
            return {"ok": True, "failed": []}
        if args[:2] == ["pdf", "import"]:
            return {"source_id": "doi:10.1/a", "title": "A"}
        raise AssertionError(args)

    app = create_app(settings, cli)
    token = TestClient(app).post("/api/clip/token").json()["token"]

    async def go():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1))
        async with httpx.AsyncClient(transport=transport, base_url="http://x") as c:
            return await asyncio.gather(
                *(
                    c.post("/api/clip/pdf", files={"file": ("a.pdf", PDF)}, headers=_bearer(token))
                    for _ in range(4)
                )
            )

    results = asyncio.run(go())
    assert [r.status_code for r in results] == [200] * 4
    assert len([c for c in calls if c[:2] == ["project", "create"]]) == 1


def test_list_failure_keeps_the_import(client, fake, token):
    fake.on("project", "create", result=CLIError(502, "boom"))
    r = _clip_pdf(client, token)
    assert r.status_code == 200
    assert r.json()["new"] == ["doi:10.1/a"]
    assert r.json()["project_id"] is None
    assert r.json()["failed"] == ["doi:10.1/a"]


def test_list_id_not_in_settings_api(client, fake, token):
    _clip_pdf(client, token)
    assert "web_clip_list_id" not in client.get("/api/settings").text


# --- PDF ---------------------------------------------------------------------


def test_new_pdf_runs_trial_then_real_import(client, fake, token):
    r = _clip_pdf(client, token)
    assert r.status_code == 200
    body = r.json()
    assert body["new"] == ["doi:10.1/a"]
    assert body["existing"] == []
    assert body["source_ids"] == ["doi:10.1/a"]
    assert len(_calls(fake, "pdf", "import")) == 2
    add = _calls(fake, "project", "add-papers")
    assert add == [["project", "add-papers", "--", "7", "doi:10.1/a"]]


def test_trial_uses_a_throwaway_library(client, fake, token, settings, monkeypatch):
    seen = []
    made = client.app.state.scratch_cli

    def spy(key, data_dir):
        seen.append(data_dir)
        return made(key, data_dir)

    client.app.state.scratch_cli = spy
    _clip_pdf(client, token)
    assert len(seen) == 1
    assert seen[0] != settings.data_dir
    assert not seen[0].exists()


def test_existing_with_pdf_is_left_alone(client, fake, token, tmp_path):
    stored = tmp_path / "stored.pdf"
    stored.write_bytes(PDF)
    fake.on(
        "paper",
        "get",
        result={"source_id": "doi:10.1/a", "title": "Edited", "pdf_path": str(stored)},
    )
    r = _clip_pdf(client, token)
    assert r.status_code == 200
    assert r.json()["existing"] == ["doi:10.1/a"]
    assert r.json()["attached"] == []
    assert len(_calls(fake, "pdf", "import")) == 1  # the trial only
    assert not _calls(fake, "paper", "repair")
    assert _calls(fake, "project", "add-papers")
    assert stored.read_bytes() == PDF


def test_existing_without_pdf_attaches_and_keeps_metadata(client, fake, token):
    fake.on(
        "paper",
        "get",
        result={
            "source_id": "doi:10.1/a",
            "title": "My title",
            "authors": ["Me"],
            "published": "2001-02-03",
            "summary": "S",
            "category": "journal",
            "doi": "10.1/a",
            "url": None,
            "tags": ["keep"],
            "pdf_path": None,
        },
    )
    fake.on("paper", "repair", result={"ok": True})
    r = _clip_pdf(client, token)
    assert r.json()["attached"] == ["doi:10.1/a"]
    assert r.json()["metadata_kept"] is True
    assert len(_calls(fake, "pdf", "import")) == 2
    repair = _calls(fake, "paper", "repair")[0]
    assert "--title=My title" in repair
    assert "--authors=Me" in repair
    assert "--published=2001-02-03" in repair
    assert "--doi=10.1/a" in repair
    assert "--tags=keep" in repair
    assert repair[-2:] == ["--", "doi:10.1/a"]


def test_existing_whose_pdf_file_is_gone_attaches(client, fake, token, tmp_path):
    fake.on(
        "paper",
        "get",
        result={
            "source_id": "doi:10.1/a",
            "title": "T",
            "published": "2001-02-03",
            "pdf_path": str(tmp_path / "gone.pdf"),
        },
    )
    fake.on("paper", "repair", result={"ok": True})
    assert _clip_pdf(client, token).json()["attached"] == ["doi:10.1/a"]


def test_restore_failure_is_reported(client, fake, token):
    fake.on("paper", "get", result={"source_id": "doi:10.1/a", "title": "T"})
    fake.on("paper", "repair", result=CLIError(400, "invalid date"))
    r = _clip_pdf(client, token)
    assert r.status_code == 200
    assert r.json()["metadata_kept"] is False


def test_not_a_pdf_refused(client, fake, token):
    r = client.post("/api/clip/pdf", files={"file": ("a.pdf", b"<html>")}, headers=_bearer(token))
    assert r.status_code == 400
    assert not _calls(fake, "pdf", "import")


def test_web_ui_import_stays_out_of_the_list(client, fake, token):
    assert client.post("/api/pdfs/import", files={"file": ("a.pdf", PDF)}).status_code == 200
    assert not _calls(fake, "project", "add-papers")
    assert not _calls(fake, "project", "create")


# --- BibTeX ------------------------------------------------------------------

KNOWN_DOI = "@article{a, title={Spelled otherwise}, doi={10.1234/KNOWN}}"
KNOWN_ARXIV = "@article{arxiv:1706.03762v7, title={Different words}}"
KNOWN_EPRINT = "@article{e, title={Other words}, eprint={1706.03762v2}, archiveprefix={arXiv}}"
KNOWN_TITLE = "@article{t, title={A {Known} Title}}"
NEW = "@article{n, title={Brand new}, doi={10.1234/new}, volume={3}}"


def _papers(fake):
    fake.on(
        "list",
        result=[
            {"source_id": "doi:10.1234/known", "title": "Known", "doi": "10.1234/known"},
            {"source_id": "arxiv:1706.03762", "title": "Attention", "doi": None},
            {"source_id": "local:abc", "title": "a known title", "doi": None},
        ],
    )


@pytest.mark.parametrize(
    ("entry", "sid"),
    [
        (KNOWN_DOI, "doi:10.1234/known"),
        (KNOWN_ARXIV, "arxiv:1706.03762"),
        (KNOWN_EPRINT, "arxiv:1706.03762"),
        (KNOWN_TITLE, "local:abc"),
    ],
)
def test_known_entry_not_imported_but_joins_list(client, fake, token, entry, sid):
    _papers(fake)
    r = _clip_bib(client, token, entry)
    assert r.status_code == 200
    assert r.json()["existing"] == [sid]
    assert r.json()["new"] == []
    assert not _calls(fake, "bibtex", "import")
    assert _calls(fake, "project", "add-papers") == [["project", "add-papers", "--", "7", sid]]


def test_mixed_file_imports_only_new_entries(client, fake, token, monkeypatch):
    _papers(fake)
    sent = []

    def read(args):
        with open(args[-1], encoding="utf-8") as f:  # noqa: S108
            sent.append(f.read())
        return {"saved_count": 1, "source_ids": ["doi:10.1234/new"]}

    fake.on("bibtex", "import", result=read)
    text = f'@string{{j = "J"}}\n{KNOWN_DOI}\n{NEW}\n'
    r = _clip_bib(client, token, text)
    assert r.json()["new"] == ["doi:10.1234/new"]
    assert r.json()["existing"] == ["doi:10.1234/known"]
    assert "Brand new" in sent[0]
    assert "@string" in sent[0]
    assert "Spelled otherwise" not in sent[0]
    add = _calls(fake, "project", "add-papers")[0]
    assert add[-2:] == ["doi:10.1234/new", "doi:10.1234/known"]


def test_new_entry_stores_bib_fields_without_overwriting(client, fake, token, monkeypatch):
    from app import bib_store

    seen = []

    async def upsert(lib, sid, fields, source=None, ref=None, overwrite=True):
        seen.append((sid, fields.get("volume"), overwrite))

    monkeypatch.setattr(bib_store, "upsert", upsert)
    assert _clip_bib(client, token, NEW).status_code == 200
    assert seen == [("doi:10.1234/new", "3", False)]


def test_web_ui_bibtex_import_still_overwrites(client, fake, token, monkeypatch):
    from app import bib_store

    seen = []

    async def upsert(lib, sid, fields, source=None, ref=None, overwrite=True):
        seen.append(overwrite)

    monkeypatch.setattr(bib_store, "upsert", upsert)
    r = client.post("/api/import/bibtex", files={"file": ("a.bib", NEW.encode())})
    assert r.status_code == 200
    assert seen == [True]


def test_unparsable_file_goes_to_the_cli(client, fake, token):
    fake.on("bibtex", "import", result=CLIError(400, "invalid BibTeX"))
    r = _clip_bib(client, token, "user@example.com")
    assert r.status_code == 400


def test_no_at_sign_refused(client, fake, token):
    assert _clip_bib(client, token, "not bibtex").status_code == 400
    assert not _calls(fake, "bibtex", "import")
