from __future__ import annotations

import json

from .conftest import fixture


def test_get_settings_hides_unlisted_keys(client, fake, monkeypatch):
    monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
    monkeypatch.setenv("CROSSREF_MAILTO", "env@example.org")
    fake.on("settings", "get", result=fixture("settings-get.json"))
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["settings"] == {
        "pdf_save_limit_mb": 1024,
        "tex_rendering_enabled": True,
        "ARXIV_MAILTO": "",
        "CROSSREF_MAILTO": "",
        "OPENALEX_MAILTO": "",
        "home_feed_url": "",
        "rss_cache_retention_days": 30,
        "search_history_enabled": True,
        "search_history_max": 200,
        "full_text_worker_enabled": False,
        "web_pdf_folder_layout": "none",
        "ai_enabled": False,
        "genai_provider": "gemini",
        "genai_model": "",
        "genai_base_url": "",
        "mcp_enabled": False,
        "mcp_profile": "read",
        "NCBI_API_KEY": "",
        "GEMINI_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "GENAI_API_KEY_TAG_GEN": "",
    }
    assert "p2p_relay_auth_token" not in r.text
    assert body["env_overrides"] == ["CROSSREF_MAILTO"]


def test_patch_settings_sends_json_values(client, fake):
    stored = fixture("settings-get.json")

    def update(argv):
        key, value = argv[-2], argv[-1]
        stored[key] = value
        return {key: value}

    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=update)
    r = client.patch(
        "/api/settings",
        json={
            "pdf_save_limit_mb": 2048,
            "tex_rendering_enabled": False,
            "OPENALEX_MAILTO": "me@example.org",
        },
    )
    assert r.status_code == 200, r.text
    updates = [c for c in fake.calls if c[:2] == ["settings", "update"]]
    assert updates == [
        ["settings", "update", "--", "pdf_save_limit_mb", "2048"],
        ["settings", "update", "--", "tex_rendering_enabled", "false"],
        ["settings", "update", "--", "OPENALEX_MAILTO", "me@example.org"],
    ]
    assert r.json()["settings"]["OPENALEX_MAILTO"] == "me@example.org"


def test_patch_can_clear_mailto(client, fake):
    fake.on("settings", "get", result={})
    fake.on("settings", "update", result={})
    r = client.patch("/api/settings", json={"ARXIV_MAILTO": ""})
    assert r.status_code == 200
    assert ["settings", "update", "--", "ARXIV_MAILTO", ""] in fake.calls


def test_patch_rejects_unlisted_and_invalid(client, fake):
    fake.on("settings", "update", result={})
    for body in (
        {"p2p_relay_auth_token": "x"},
        {"OPENALEX_MAILTO": "not-an-email"},
        {"pdf_save_limit_mb": 0},
        {"tex_rendering_enabled": "yes"},
        {"home_feed_url": "file:///etc/passwd"},
        {"home_feed_url": "https://"},
        {"home_feed_url": "https://a b"},
        {"rss_cache_retention_days": 0},
        {"rss_cache_retention_days": "7"},
        {"search_history_max": 0},
        {"search_history_max": 10_001},
        {"search_history_enabled": "no"},
    ):
        assert client.patch("/api/settings", json=body).status_code == 422, body
    assert not [c for c in fake.calls if c[:2] == ["settings", "update"]]


def test_patch_feed_settings(client, fake):
    stored: dict = {}
    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=lambda argv: stored.update({argv[-2]: argv[-1]}))
    r = client.patch(
        "/api/settings",
        json={"home_feed_url": "https://rss.arxiv.org/rss/cs.LG", "rss_cache_retention_days": 7},
    )
    assert r.status_code == 200, r.text
    updates = [c[-2:] for c in fake.calls if c[:2] == ["settings", "update"]]
    assert updates == [
        ["home_feed_url", "https://rss.arxiv.org/rss/cs.LG"],
        ["rss_cache_retention_days", "7"],
    ]
    assert client.patch("/api/settings", json={"home_feed_url": ""}).status_code == 200


def test_patch_search_history_settings(client, fake):
    stored: dict = {}
    fake.on("settings", "get", result=lambda _: stored)
    fake.on("settings", "update", result=lambda argv: stored.update({argv[-2]: argv[-1]}))
    body = {"search_history_enabled": False, "search_history_max": 50}
    assert client.patch("/api/settings", json=body).status_code == 200
    updates = [c[-2:] for c in fake.calls if c[:2] == ["settings", "update"]]
    assert updates == [["search_history_enabled", "false"], ["search_history_max", "50"]]


def test_ncbi_api_key_is_write_only(client, fake, monkeypatch):
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    stored: dict = {}
    fake.on("settings", "get", result=lambda _: stored)
    fake.on(
        "settings", "update", result=lambda argv: stored.update({argv[-2]: json.loads(argv[-1])})
    )
    key = "abcdef0123456789abcdef0123456789ab12"
    r = client.patch("/api/settings", json={"NCBI_API_KEY": key})
    assert r.status_code == 200, r.text
    assert ["settings", "update", "--", "NCBI_API_KEY", f'"{key}"'] in fake.calls
    body = client.get("/api/settings").json()
    assert key not in str(body)
    assert body["settings"]["NCBI_API_KEY"] == ""
    assert body["ncbi_api_key"] == {"set": True, "last4": "ab12", "source": "settings"}

    monkeypatch.setenv("NCBI_API_KEY", "ENVKEY0123456789ENVzz99")
    body = client.get("/api/settings").json()
    assert body["ncbi_api_key"]["source"] == "env" and "NCBI_API_KEY" in body["env_overrides"]
    monkeypatch.delenv("NCBI_API_KEY")

    assert (
        client.patch("/api/settings", json={"NCBI_API_KEY": ""}).json()["ncbi_api_key"]["set"]
        is False
    )
    for bad in ("short", "has space in it 12345678", "x" * 65, "abc$def0123456789abcdef"):
        assert client.patch("/api/settings", json={"NCBI_API_KEY": bad}).status_code == 422, bad
