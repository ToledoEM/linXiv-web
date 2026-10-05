from __future__ import annotations

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
    ):
        assert client.patch("/api/settings", json=body).status_code == 422, body
    assert not [c for c in fake.calls if c[:2] == ["settings", "update"]]
