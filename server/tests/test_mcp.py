from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.mcp_bridge import ALWAYS_BLOCKED, PROFILES, call_refusal

FAKE = [sys.executable, str(Path(__file__).parent / "fixtures" / "fake_mcp.py")]
TOKEN = "lxmcp_test-token-0123456789"


def _stored(**extra) -> dict:
    return {
        "mcp_enabled": True,
        "mcp_profile": "read",
        "web_mcp_token_hash": hashlib.sha256(TOKEN.encode()).hexdigest(),
        **extra,
    }


@pytest.fixture
def mcp(settings, fake):
    app = create_app(settings, fake)
    app.state.mcp.command = FAKE
    with TestClient(app) as c:
        yield c


def _rpc(c, method, params=None, *, sid=None, msg_id=1, token=TOKEN):
    headers = {"Authorization": f"Bearer {token}"}
    if sid:
        headers["Mcp-Session-Id"] = sid
    body = {"jsonrpc": "2.0", "method": method}
    if msg_id is not None:
        body["id"] = msg_id
    if params is not None:
        body["params"] = params
    return c.post("/mcp", json=body, headers=headers)


def _init(c) -> str:
    r = _rpc(c, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["serverInfo"] == {"name": "fake"}
    return r.headers["mcp-session-id"]


# ---- policy ----


def test_profiles_never_include_blocked_tools():
    for tools in PROFILES.values():
        assert not tools & ALWAYS_BLOCKED
    assert PROFILES["read"] < PROFILES["write"] < PROFILES["full"]
    assert "list_papers" in PROFILES["read"] and "create_note" not in PROFILES["read"]
    assert "create_note" in PROFILES["write"] and "merge_papers" not in PROFILES["write"]
    assert "merge_papers" in PROFILES["full"]


def test_policy_covers_every_real_tool():
    # Captured from the real linxiv-mcp (v0.6.0) in discovery: every tool is
    # classified, so a new upstream tool shows up here instead of silently hidden.
    names = {
        "ack_version",
        "add_paper_to_project",
        "add_papers_to_project",
        "add_tags_to_paper",
        "add_tags_to_project",
        "archive_project",
        "author_merge_candidates",
        "backup_database",
        "check_versions",
        "create_annotation",
        "create_feed_rule",
        "create_note",
        "create_project",
        "create_tag",
        "delete_annotation",
        "delete_author",
        "delete_feed_rule",
        "delete_note",
        "delete_paper",
        "delete_pdf",
        "delete_project",
        "delete_tag",
        "dismiss_feed_entry",
        "download_pdf",
        "export_project",
        "export_project_bibtex",
        "export_project_obsidian",
        "export_project_zotero",
        "fetch_full_text",
        "fetch_paper",
        "find_doi_candidates",
        "full_text_pending",
        "get_annotation",
        "get_author",
        "get_feed",
        "get_note",
        "get_notes_for_paper",
        "get_notes_for_project",
        "get_paper",
        "get_paper_tags",
        "get_paper_versions",
        "get_pdf_path",
        "get_pdf_storage",
        "get_project",
        "get_project_tags",
        "get_settings",
        "get_stats",
        "hard_delete_project_from_trash",
        "import_bibtex",
        "import_pdf",
        "import_project",
        "import_zotero",
        "list_all_tags",
        "list_annotations",
        "list_authors",
        "list_categories",
        "list_feed_rules",
        "list_new_versions",
        "list_notes",
        "list_papers",
        "list_pdfs",
        "list_projects",
        "list_trash",
        "merge_authors",
        "merge_papers",
        "orcid_backfill",
        "paper_ref",
        "remove_paper_from_all_projects",
        "remove_paper_from_project",
        "remove_tags_from_paper",
        "remove_tags_from_project",
        "repair_paper",
        "resolve_doi",
        "resolve_refs",
        "restore_database",
        "restore_paper",
        "restore_project",
        "restore_project_from_trash",
        "save_doi",
        "search_full_text",
        "search_papers",
        "trash_hard_delete_paper",
        "update_annotation",
        "update_author",
        "update_note",
        "update_project",
        "update_setting",
    }
    assert len(names) == 87
    assert names == PROFILES["full"] | ALWAYS_BLOCKED


def test_download_pdf_url_refused():
    assert call_refusal("write", {"name": "download_pdf", "arguments": {"paper_id": "x"}}) is None
    assert "url" in call_refusal(
        "write", {"name": "download_pdf", "arguments": {"paper_id": "x", "url": "http://10.0.0.1/"}}
    )


# ---- endpoint ----


def test_disabled_is_404(mcp, fake):
    fake.on("settings", "get", result=_stored(mcp_enabled=False))
    assert _rpc(mcp, "initialize", {}).status_code == 404


def test_token_required(mcp, fake):
    fake.on("settings", "get", result=_stored())
    r = _rpc(mcp, "initialize", {}, token="wrong")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert (
        mcp.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}).status_code
        == 401
    )
    # No token configured at all: nothing matches, not even an empty bearer.
    fake.on("settings", "get", result=_stored(web_mcp_token_hash=""))
    mcp.app.state.mcp_conf = None
    assert _rpc(mcp, "initialize", {}, token="").status_code == 401


def test_cross_origin_refused(mcp, fake):
    fake.on("settings", "get", result=_stored())
    r = mcp.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={"Authorization": f"Bearer {TOKEN}", "Origin": "http://evil.example"},
    )
    assert r.status_code == 403


def test_session_flow_and_filtering(mcp, fake):
    fake.on("settings", "get", result=_stored())
    sid = _init(mcp)
    assert _rpc(mcp, "notifications/initialized", sid=sid, msg_id=None).status_code == 202
    tools = [t["name"] for t in _rpc(mcp, "tools/list", sid=sid).json()["result"]["tools"]]
    assert tools == ["list_papers"]  # read profile: blocked, write-only and unknown tools hidden
    r = _rpc(mcp, "tools/call", {"name": "list_papers", "arguments": {}}, sid=sid, msg_id=7)
    assert r.json()["id"] == 7
    assert json.loads(r.json()["result"]["content"][0]["text"])["called"] == "list_papers"
    for name in ("get_settings", "create_note", "brand_new_tool"):
        r = _rpc(mcp, "tools/call", {"name": name, "arguments": {}}, sid=sid)
        assert r.json()["error"]["code"] == -32602, name
    # Unknown session -> 404 (client re-initializes); missing header -> 400.
    assert _rpc(mcp, "tools/list", sid="nope").status_code == 404
    assert _rpc(mcp, "tools/list").status_code == 400
    assert (
        mcp.delete(
            "/mcp", headers={"Authorization": f"Bearer {TOKEN}", "Mcp-Session-Id": sid}
        ).status_code
        == 204
    )
    assert _rpc(mcp, "tools/list", sid=sid).status_code == 404


def test_write_profile(mcp, fake):
    fake.on("settings", "get", result=_stored(mcp_profile="write"))
    sid = _init(mcp)
    tools = [t["name"] for t in _rpc(mcp, "tools/list", sid=sid).json()["result"]["tools"]]
    assert tools == ["list_papers", "create_note", "download_pdf"]
    r = _rpc(
        mcp,
        "tools/call",
        {"name": "download_pdf", "arguments": {"paper_id": "a", "url": "http://x/"}},
        sid=sid,
    )
    assert "url argument" in r.json()["error"]["message"]


def test_get_is_405_and_bad_bodies(mcp, fake):
    fake.on("settings", "get", result=_stored())
    r = mcp.get("/mcp", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 405 and r.headers["allow"] == "POST, DELETE"
    h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    assert mcp.post("/mcp", content=b"{bad", headers=h).json()["error"]["code"] == -32700
    assert mcp.post("/mcp", content=b"[]", headers=h).json()["error"]["code"] == -32600
    assert mcp.post("/mcp", content=b"x" * (1024 * 1024 + 1), headers=h).status_code == 413


def test_crashed_session_ends(mcp, fake):
    fake.on("settings", "get", result=_stored())
    sid = _init(mcp)
    assert _rpc(mcp, "crash", sid=sid).status_code == 502
    assert _rpc(mcp, "tools/list", sid=sid).status_code == 404


def test_timeout_kills_session(mcp, fake):
    fake.on("settings", "get", result=_stored())
    mcp.app.state.mcp.timeout = 0.5
    sid = _init(mcp)
    assert _rpc(mcp, "slow", sid=sid).status_code == 504
    assert sid not in mcp.app.state.mcp.sessions


def test_session_cap_evicts_idle(mcp, fake):
    fake.on("settings", "get", result=_stored())
    first = _init(mcp)
    for _ in range(4):
        _init(mcp)
    assert len(mcp.app.state.mcp.sessions) == 4 and first not in mcp.app.state.mcp.sessions


# ---- token + settings (browser API) ----


def test_token_create_revoke_and_status(mcp, fake):
    stored: dict = {"mcp_enabled": True}
    fake.on("settings", "get", result=lambda _: stored)
    fake.on(
        "settings", "update", result=lambda argv: stored.update({argv[-2]: json.loads(argv[-1])})
    )
    s = mcp.get("/api/mcp").json()
    assert s["token"] == {"set": False, "hint": None, "created": None}
    assert s["tool_counts"]["read"] < s["tool_counts"]["write"] < s["tool_counts"]["full"]
    tok = mcp.post("/api/mcp/token").json()
    assert tok["token"].startswith("lxmcp_") and tok["hint"] == tok["token"][-4:]
    assert tok["token"] not in json.dumps(stored)  # only the hash is stored
    assert stored["web_mcp_token_hash"] == hashlib.sha256(tok["token"].encode()).hexdigest()
    assert mcp.get("/api/mcp").json()["token"]["set"] is True
    # The settings API never shows the hash.
    assert "web_mcp_token" not in mcp.get("/api/settings").text
    r = _rpc(mcp, "initialize", {}, token=tok["token"])
    assert r.status_code == 200
    mcp.delete("/api/mcp/token")
    assert mcp.app.state.mcp.sessions == {}
    assert _rpc(mcp, "initialize", {}, token=tok["token"]).status_code == 401


def test_settings_patch_toggles_and_validates(mcp, fake):
    stored: dict = _stored()
    fake.on("settings", "get", result=lambda _: stored)
    fake.on(
        "settings", "update", result=lambda argv: stored.update({argv[-2]: json.loads(argv[-1])})
    )
    sid = _init(mcp)
    r = mcp.patch("/api/settings", json={"mcp_enabled": False})
    assert r.status_code == 200 and r.json()["settings"]["mcp_enabled"] is False
    assert sid not in mcp.app.state.mcp.sessions
    assert _rpc(mcp, "initialize", {}).status_code == 404
    assert mcp.patch("/api/settings", json={"mcp_profile": "admin"}).status_code == 422
    assert mcp.patch("/api/settings", json={"web_mcp_token_hash": "x"}).status_code == 422


def test_token_routes_need_browser_login(settings, fake):
    with TestClient(create_app(replace(settings, password="hunter2"), fake)) as c:
        assert c.post("/api/mcp/token").status_code == 401
        assert c.get("/api/mcp").status_code == 401


# ---- real linxiv-mcp (Docker test image) ----

MCP_BIN = os.environ.get("LINXIV_MCP_BIN")


@pytest.mark.integration
@pytest.mark.skipif(not MCP_BIN or not shutil.which(MCP_BIN), reason="LINXIV_MCP_BIN not set")
def test_real_linxiv_mcp(settings, fake):
    fake.on("settings", "get", result=_stored(mcp_profile="write"))
    app = create_app(replace(settings, mcp_bin=MCP_BIN), fake)
    with TestClient(app) as c:
        r = _rpc(
            c,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "0"},
            },
        )
        assert r.status_code == 200, r.text
        sid = r.headers["mcp-session-id"]
        assert _rpc(c, "notifications/initialized", sid=sid, msg_id=None).status_code == 202
        tools = {t["name"] for t in _rpc(c, "tools/list", sid=sid).json()["result"]["tools"]}
        assert tools == PROFILES["write"]
        r = _rpc(c, "tools/call", {"name": "get_stats", "arguments": {}}, sid=sid)
        stats = json.loads(r.json()["result"]["content"][0]["text"])
        assert stats["paper_count"] == 0
        assert (settings.data_dir / "papers.db").is_file()
