from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app import ai

KEYS = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "generic": "GENAI_API_KEY_TAG_GEN",
}
SECRET = "sk-test-SECRET-0123456789"


@pytest.fixture(autouse=True)
def _no_env_keys(monkeypatch):
    for k in KEYS.values():
        monkeypatch.delenv(k, raising=False)


def _stored(provider: str, **extra) -> dict:
    return {
        "ai_enabled": True,
        "genai_provider": provider,
        "genai_model": "m-1",
        KEYS[provider]: SECRET,
        **({"genai_base_url": "http://192.168.1.5:11434/v1/"} if provider == "generic" else {}),
        **extra,
    }


def _mock(monkeypatch, handler, seen: list):
    def wrapped(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    monkeypatch.setattr(
        ai, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    )


# ---- settings: keys are write-only, new keys validated ----


def test_ai_keys_write_only(client, fake, monkeypatch):
    stored: dict = {}
    fake.on("settings", "get", result=lambda _: stored)
    fake.on(
        "settings", "update", result=lambda argv: stored.update({argv[-2]: json.loads(argv[-1])})
    )
    body = {
        "ai_enabled": True,
        "genai_provider": "openai",
        "genai_model": "123",
        "OPENAI_API_KEY": SECRET,
    }
    r = client.patch("/api/settings", json=body)
    assert r.status_code == 200, r.text
    assert ["settings", "update", "--", "OPENAI_API_KEY", f'"{SECRET}"'] in fake.calls
    assert ["settings", "update", "--", "genai_model", '"123"'] in fake.calls
    assert stored["genai_model"] == "123"
    got = client.get("/api/settings").json()
    assert SECRET not in json.dumps(got)
    assert got["settings"]["OPENAI_API_KEY"] == ""
    assert got["settings"]["ai_enabled"] is True
    assert got["ai_keys"]["OPENAI_API_KEY"] == {"set": True, "last4": "6789", "source": "settings"}
    assert got["ai_keys"]["GEMINI_API_KEY"]["set"] is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-abcdefgh")
    got = client.get("/api/settings").json()
    assert got["ai_keys"]["ANTHROPIC_API_KEY"]["source"] == "env"
    assert "ANTHROPIC_API_KEY" in got["env_overrides"]


def test_ai_settings_defaults_off(client, fake):
    fake.on("settings", "get", result={})
    s = client.get("/api/settings").json()["settings"]
    assert s["ai_enabled"] is False
    assert s["genai_provider"] == "gemini"
    assert s["genai_model"] == "" and s["genai_base_url"] == ""


@pytest.mark.parametrize(
    "body",
    [
        {"genai_provider": "mistral"},
        {"genai_model": "has space"},
        {"genai_model": "x" * 129},
        {"genai_base_url": "file:///etc/passwd"},
        {"genai_base_url": "http://host/v1?x=1"},
        {"OPENAI_API_KEY": "short"},
        {"OPENAI_API_KEY": "has space 12345678"},
        {"GEMINI_API_KEY": "x" * 257},
        {"ai_enabled": "yes"},
    ],
)
def test_ai_settings_rejects_invalid(client, fake, body):
    fake.on("settings", "update", result={})
    assert client.patch("/api/settings", json=body).status_code == 422


# ---- config ----


def test_routes_refuse_when_disabled(client, fake):
    fake.on("settings", "get", result={**_stored("openai"), "ai_enabled": False})
    r = client.get("/api/ai/models")
    assert r.status_code == 409 and "off" in r.json()["detail"]
    assert client.post("/api/ai/test").status_code == 409


def test_missing_key_and_base_url(client, fake):
    fake.on("settings", "get", result={**_stored("anthropic"), "ANTHROPIC_API_KEY": ""})
    r = client.get("/api/ai/models")
    assert r.status_code == 400 and "Anthropic API key" in r.json()["detail"]
    fake.on("settings", "get", result={**_stored("generic"), "genai_base_url": ""})
    assert client.get("/api/ai/models").status_code == 400


def test_env_key_wins(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key-abcdefgh")
    assert ai.config_from(_stored("openai")).key == "env-key-abcdefgh"


# ---- models ----


def test_models_gemini(client, fake, monkeypatch):
    seen: list = []
    _mock(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-2.5-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/text-embedding-004",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            },
        ),
        seen,
    )
    fake.on("settings", "get", result=_stored("gemini"))
    r = client.get("/api/ai/models")
    assert r.status_code == 200, r.text
    assert r.json() == {"provider": "gemini", "models": ["gemini-2.5-flash"]}
    assert seen[0].url.host == "generativelanguage.googleapis.com"
    assert seen[0].headers["x-goog-api-key"] == SECRET
    assert SECRET not in str(seen[0].url)


def test_models_openai_filters_non_chat(client, fake, monkeypatch):
    seen: list = []
    ids = ["gpt-5-mini", "text-embedding-3-small", "whisper-1", "gpt-4o", "gpt-4o"]
    _mock(
        monkeypatch, lambda req: httpx.Response(200, json={"data": [{"id": i} for i in ids]}), seen
    )
    fake.on("settings", "get", result=_stored("openai"))
    assert client.get("/api/ai/models").json()["models"] == ["gpt-4o", "gpt-5-mini"]
    assert str(seen[0].url) == "https://api.openai.com/v1/models"
    assert seen[0].headers["authorization"] == f"Bearer {SECRET}"


def test_models_anthropic(client, fake, monkeypatch):
    seen: list = []
    _mock(
        monkeypatch,
        lambda req: httpx.Response(200, json={"data": [{"id": "claude-haiku-4-5"}]}),
        seen,
    )
    fake.on("settings", "get", result=_stored("anthropic"))
    assert client.get("/api/ai/models").json()["models"] == ["claude-haiku-4-5"]
    assert seen[0].url.host == "api.anthropic.com"
    assert seen[0].headers["x-api-key"] == SECRET
    assert seen[0].headers["anthropic-version"] == ai.ANTHROPIC_VERSION


def test_models_generic_without_key(client, fake, monkeypatch):
    seen: list = []
    _mock(monkeypatch, lambda req: httpx.Response(200, json={"data": [{"id": "llama3.2"}]}), seen)
    fake.on("settings", "get", result={**_stored("generic"), "GENAI_API_KEY_TAG_GEN": ""})
    assert client.get("/api/ai/models").json()["models"] == ["llama3.2"]
    assert str(seen[0].url) == "http://192.168.1.5:11434/v1/models"
    assert "authorization" not in seen[0].headers


# ---- errors ----


def test_provider_error_is_redacted(client, fake, monkeypatch):
    msg = f"Incorrect API key provided: {SECRET}."
    _mock(monkeypatch, lambda req: httpx.Response(401, json={"error": {"message": msg}}), [])
    fake.on("settings", "get", result=_stored("openai"))
    r = client.get("/api/ai/models")
    assert r.status_code == 502
    assert r.json()["detail"].startswith("OpenAI error 401: Incorrect API key provided")
    assert SECRET not in r.text


def test_network_error_reports_type_only(client, fake, monkeypatch):
    def down(req):
        raise httpx.ConnectError(f"cannot reach {req.url}")

    _mock(monkeypatch, down, [])
    fake.on("settings", "get", result=_stored("gemini"))
    r = client.post("/api/ai/test")
    assert r.status_code == 502
    assert r.json()["detail"] == "Gemini request failed (ConnectError)"


def test_redirect_not_followed(client, fake, monkeypatch):
    seen: list = []
    _mock(
        monkeypatch,
        lambda req: httpx.Response(302, headers={"Location": "https://evil.example/"}),
        seen,
    )
    fake.on("settings", "get", result=_stored("openai"))
    assert client.get("/api/ai/models").status_code == 502
    assert len(seen) == 1


def test_oversize_response(client, fake, monkeypatch):
    _mock(monkeypatch, lambda req: httpx.Response(200, content=b"x" * (ai.MAX_BYTES + 1)), [])
    fake.on("settings", "get", result=_stored("openai"))
    r = client.get("/api/ai/models")
    assert r.status_code == 502 and "too large" in r.json()["detail"]


# ---- test connection / complete ----


def test_connection_openai(client, fake, monkeypatch):
    seen: list = []
    _mock(
        monkeypatch,
        lambda req: httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok": true}'}}]}
        ),
        seen,
    )
    fake.on("settings", "get", result=_stored("openai"))
    r = client.post("/api/ai/test")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["model"] == "m-1"
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://api.openai.com/v1/chat/completions"
    assert body["model"] == "m-1" and body["max_completion_tokens"] == 256
    assert body["response_format"]["type"] == "json_schema"
    assert body["messages"][0]["role"] == "system"


def test_connection_generic_parses_fenced_json(client, fake, monkeypatch):
    seen: list = []
    reply = 'Sure!\n```json\n{"ok": true}\n```'
    _mock(
        monkeypatch,
        lambda req: httpx.Response(200, json={"choices": [{"message": {"content": reply}}]}),
        seen,
    )
    fake.on("settings", "get", result=_stored("generic"))
    assert client.post("/api/ai/test").json()["ok"] is True
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == "http://192.168.1.5:11434/v1/chat/completions"
    assert "response_format" not in body and body["max_tokens"] == 256
    assert "JSON Schema" in body["messages"][0]["content"]


def test_connection_gemini(client, fake, monkeypatch):
    seen: list = []
    parts = [{"text": "thinking…", "thought": True}, {"text": '{"ok": true}'}]
    _mock(
        monkeypatch,
        lambda req: httpx.Response(200, json={"candidates": [{"content": {"parts": parts}}]}),
        seen,
    )
    fake.on("settings", "get", result={**_stored("gemini"), "genai_model": "gemini-2.5-flash"})
    assert client.post("/api/ai/test").json()["ok"] is True
    assert seen[0].url.path == "/v1beta/models/gemini-2.5-flash:generateContent"
    body = json.loads(seen[0].content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "systemInstruction" in body


def test_connection_anthropic_uses_forced_tool(client, fake, monkeypatch):
    seen: list = []
    content = [{"type": "tool_use", "name": "result", "input": {"ok": True}}]
    _mock(monkeypatch, lambda req: httpx.Response(200, json={"content": content}), seen)
    fake.on("settings", "get", result=_stored("anthropic"))
    assert client.post("/api/ai/test").json()["ok"] is True
    body = json.loads(seen[0].content)
    assert body["tool_choice"] == {"type": "tool", "name": "result"}
    assert body["tools"][0]["input_schema"]["required"] == ["ok"]
    assert body["max_tokens"] == 256 and "system" not in body


def test_bad_json_reply(client, fake, monkeypatch):
    _mock(
        monkeypatch,
        lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "nope"}}]}),
        [],
    )
    fake.on("settings", "get", result=_stored("openai"))
    r = client.post("/api/ai/test")
    assert r.status_code == 502 and "valid JSON" in r.json()["detail"]


def test_no_model(client, fake):
    fake.on("settings", "get", result={**_stored("openai"), "genai_model": ""})
    r = client.post("/api/ai/test")
    assert r.status_code == 400 and "model" in r.json()["detail"]


def test_complete_text_and_prompt_cap(monkeypatch):
    _mock(
        monkeypatch,
        lambda req: httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}]}),
        [],
    )
    cfg = ai.AIConfig("anthropic", "m", SECRET)
    assert asyncio.run(ai.complete(cfg, "hello", system="be brief")) == "hi"
    with pytest.raises(ai.AIError) as e:
        asyncio.run(ai.complete(cfg, "x" * (ai.MAX_PROMPT_CHARS + 1)))
    assert e.value.status == 413


# ---- tag suggestions ----


def _tag_reply(tags):
    return lambda req: httpx.Response(
        200, json={"choices": [{"message": {"content": json.dumps({"tags": tags})}}]}
    )


def test_suggest_tags(client, fake, monkeypatch):
    seen: list = []
    reply = [
        "NLP",
        " #attention  mechanism ",
        "nlp",
        "Transformers",
        "",
        "x" * 65,
        7,
        "machine translation",
    ]
    _mock(monkeypatch, _tag_reply(reply), seen)
    fake.on("settings", "get", result=_stored("openai"))
    fake.on(
        "paper",
        "get",
        result={
            "title": "Attention Is All You Need",
            "summary": "The dominant sequence transduction models…",
            "categories": ["cs.CL", "cs.LG"],
            "tags": ["transformers"],
        },
    )
    fake.on("tag", "list-all", result=["nlp", "transformers", "vision"])
    r = client.post("/api/ai/tags/1706.03762")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "source_id": "1706.03762",
        "suggested": [
            {"tag": "nlp", "known": True},
            {"tag": "attention mechanism", "known": False},
            {"tag": "machine translation", "known": False},
        ],
    }
    assert ["paper", "get", "--", "1706.03762"] in fake.calls
    prompt = json.loads(seen[0].content)["messages"][1]["content"]
    assert "Title: Attention Is All You Need" in prompt
    assert "Categories: cs.CL, cs.LG" in prompt
    assert "Current tags: transformers" in prompt
    assert "Existing vocabulary: nlp, transformers, vision" in prompt
    # Suggestions only: nothing written.
    assert not any(c[:2] == ["tag", "add"] for c in fake.calls)


def test_suggest_tags_caps_count(client, fake, monkeypatch):
    _mock(monkeypatch, _tag_reply([f"t{i}" for i in range(20)]), [])
    fake.on("settings", "get", result=_stored("openai"))
    fake.on("paper", "get", result={"title": "T", "tags": []})
    fake.on("tag", "list-all", result=[])
    assert len(client.post("/api/ai/tags/p1").json()["suggested"]) == 8


def test_suggest_tags_disabled_and_bad_reply(client, fake, monkeypatch):
    fake.on("settings", "get", result={**_stored("openai"), "ai_enabled": False})
    assert client.post("/api/ai/tags/p1").status_code == 409
    assert not any(c[:2] == ["paper", "get"] for c in fake.calls)

    _mock(
        monkeypatch,
        lambda req: httpx.Response(200, json={"choices": [{"message": {"content": '{"x": 1}'}}]}),
        [],
    )
    fake.on("settings", "get", result=_stored("openai"))
    fake.on("paper", "get", result={"title": "T", "tags": []})
    fake.on("tag", "list-all", result=[])
    r = client.post("/api/ai/tags/p1")
    assert r.status_code == 502 and "no tags" in r.json()["detail"]
