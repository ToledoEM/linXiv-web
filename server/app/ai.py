"""One small client for the AI features: Gemini, OpenAI, Anthropic, or any
OpenAI-compatible endpoint (OpenRouter, Ollama, LM Studio, vLLM...).

Opt-in: nothing here runs unless the user turned `ai_enabled` on in Settings.
Keys come from the env var or the stored setting of the same name (env wins)
and never appear in errors: provider messages are redacted, network errors
report the exception type only.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from .routes.user_settings import secret

PROVIDERS = ("gemini", "openai", "anthropic", "generic")
LABELS = {
    "gemini": "Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "generic": "OpenAI-compatible endpoint",
}
KEY_FOR = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "generic": "GENAI_API_KEY_TAG_GEN",
}
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
OPENAI = "https://api.openai.com/v1"
ANTHROPIC = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"

TIMEOUT = 90
# Local models (LM Studio, Ollama...) read long prompts slowly: a summary with
# PDF text can take minutes on a laptop-class GPU.
GENERIC_TIMEOUT = 300
MAX_BYTES = 2 * 1024 * 1024
MAX_PROMPT_CHARS = 200_000
# OpenAI's /models lists every model; keep the ones that answer chat requests.
OPENAI_NON_CHAT = re.compile(
    r"embedding|tts|whisper|dall-e|moderation|audio|realtime|transcribe|image|davinci|babbage|sora"
)


class AIError(Exception):
    def __init__(self, message: str, status: int = 502, upstream: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        # HTTP status the provider answered with, when it answered.
        self.upstream = upstream


@dataclass(frozen=True)
class AIConfig:
    provider: str
    model: str
    key: str
    base_url: str = ""

    @property
    def label(self) -> str:
        return LABELS[self.provider]


def config_from(stored: dict) -> AIConfig:
    """The provider set in Settings, with its key. Raises AIError when it can't be used."""
    if stored.get("ai_enabled") is not True:
        raise AIError("AI features are off. Turn them on in Settings → AI.", 409)
    provider = stored.get("genai_provider") or "gemini"
    if provider not in PROVIDERS:
        raise AIError(f"Unknown AI provider {provider!r}", 400)
    key, _ = secret(stored, KEY_FOR[provider])
    base_url = (stored.get("genai_base_url") or "").strip().rstrip("/")
    if provider == "generic" and not base_url:
        raise AIError("Set the base URL of the OpenAI-compatible endpoint in Settings → AI.", 400)
    if provider != "generic" and not key:
        raise AIError(f"No {LABELS[provider]} API key. Add one in Settings → AI.", 400)
    return AIConfig(provider, (stored.get("genai_model") or "").strip(), key, base_url)


# The OpenAI-compatible base URL may point at the LAN (LM Studio, Ollama), so only
# addresses that are never an AI server are refused: cloud instance metadata.
METADATA_NETS = [
    ipaddress.ip_network(n) for n in ("169.254.0.0/16", "fd00:ec2::254/128", "100.100.100.200/32")
]


def _allowed_hosts() -> set[str]:
    raw = os.environ.get("LINXIV_WEB_AI_ALLOWED_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


async def check_base_url(url: str) -> None:
    """Refuse a generic base URL whose host resolves to cloud metadata, or that is
    not in LINXIV_WEB_AI_ALLOWED_HOSTS when that list is set."""
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        raise AIError("The AI base URL has no host.", 400)
    allowed = _allowed_hosts()
    if allowed and host not in allowed:
        raise AIError(f"AI host {host!r} is not in LINXIV_WEB_AI_ALLOWED_HOSTS.", 400)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as e:
        raise AIError(f"Cannot resolve AI host {host!r}") from e
    for info in infos:
        ip = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if any(ip in net for net in METADATA_NETS):
            raise AIError(f"AI host {host!r} resolves to a blocked address ({ip}).", 400)


def _http() -> httpx.AsyncClient:
    # No redirects: a key must never follow a redirect to another host.
    return httpx.AsyncClient(
        timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": "linxiv-web"}
    )


def _headers(cfg: AIConfig) -> dict[str, str]:
    if cfg.provider == "gemini":
        return {"x-goog-api-key": cfg.key}
    if cfg.provider == "anthropic":
        return {"x-api-key": cfg.key, "anthropic-version": ANTHROPIC_VERSION}
    return {"Authorization": f"Bearer {cfg.key}"} if cfg.key else {}


def _redact(text: str, cfg: AIConfig) -> str:
    if cfg.key:
        text = text.replace(cfg.key, "…")
    return text[:300]


async def _call(cfg: AIConfig, method: str, url: str, body: dict | None = None) -> Any:
    if cfg.provider == "generic":
        await check_base_url(url)
    try:
        async with _http() as client:
            timeout = GENERIC_TIMEOUT if cfg.provider == "generic" else TIMEOUT
            r = await client.request(method, url, json=body, headers=_headers(cfg), timeout=timeout)
    except httpx.HTTPError as e:
        # Exception type only: messages can carry the request URL.
        raise AIError(f"{cfg.label} request failed ({type(e).__name__})") from e
    if len(r.content) > MAX_BYTES:
        raise AIError(f"{cfg.label} response too large")
    if r.status_code != 200:
        try:
            err = r.json().get("error")
            msg = err.get("message") if isinstance(err, dict) else err
        except (ValueError, AttributeError):
            msg = None
        detail = f": {_redact(str(msg), cfg)}" if msg else ""
        raise AIError(f"{cfg.label} error {r.status_code}{detail}", upstream=r.status_code)
    try:
        return r.json()
    except ValueError as e:
        raise AIError(f"{cfg.label} returned invalid JSON") from e


def _openai_base(cfg: AIConfig) -> str:
    return cfg.base_url if cfg.provider == "generic" else OPENAI


async def list_models(cfg: AIConfig) -> list[str]:
    """Model ids the key can use, sorted."""
    if cfg.provider == "gemini":
        data = await _call(cfg, "GET", f"{GEMINI}/models?pageSize=1000")
        ids = [
            m["name"].removeprefix("models/")
            for m in data.get("models", [])
            if isinstance(m, dict)
            and isinstance(m.get("name"), str)
            and "generateContent" in (m.get("supportedGenerationMethods") or [])
        ]
    else:
        url = f"{ANTHROPIC}/models?limit=1000" if cfg.provider == "anthropic" else None
        data = await _call(cfg, "GET", url or f"{_openai_base(cfg)}/models")
        ids = [
            m["id"]
            for m in data.get("data", [])
            if isinstance(m, dict) and isinstance(m.get("id"), str)
        ]
        if cfg.provider == "openai":
            ids = [i for i in ids if not OPENAI_NON_CHAT.search(i)]
    return sorted(set(ids))


def _schema_note(schema: dict, example: Any = None) -> str:
    note = (
        "Reply with JSON only (no prose, no code fences), valid against this "
        "JSON Schema (draft 2020-12):\n" + json.dumps(schema)
    )
    if example is not None:
        note += "\nExample of a valid reply:\n" + json.dumps(example)
    return note


THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _parse_json(text: str, cfg: AIConfig) -> Any:
    # Reasoning models may put their thinking (which can contain braces) in the reply.
    text = THINK_BLOCK.sub("", text).strip()
    try:
        return json.loads(text)
    except ValueError:
        # Models sometimes wrap JSON in prose or ``` fences.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except ValueError:
                pass
    raise AIError(f"{cfg.label} did not return valid JSON")


async def complete(
    cfg: AIConfig,
    prompt: str,
    *,
    system: str = "",
    schema: dict | None = None,
    example: Any = None,
    max_tokens: int = 2048,
) -> Any:
    """Text reply, or the parsed JSON object when `schema` is given. The schema
    and a valid `example` reply go in the system prompt for every provider."""
    if not cfg.model:
        raise AIError("Choose a model in Settings → AI.", 400)
    if len(prompt) + len(system) > MAX_PROMPT_CHARS:
        raise AIError("Prompt too long", 413)
    if schema is not None:
        system = f"{system}\n\n{_schema_note(schema, example)}".strip()

    if cfg.provider == "gemini":
        body: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if schema is not None:
            body["generationConfig"] = {"responseMimeType": "application/json"}
        data = await _call(
            cfg, "POST", f"{GEMINI}/models/{quote(cfg.model, safe='')}:generateContent", body
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        except (KeyError, IndexError, TypeError) as e:
            raise AIError(f"{cfg.label} returned no answer") from e

    elif cfg.provider == "anthropic":
        body = {
            "model": cfg.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        if schema is not None:
            # A forced tool call is Anthropic's structured-output path.
            body["tools"] = [
                {"name": "result", "description": "Return the result.", "input_schema": schema}
            ]
            body["tool_choice"] = {"type": "tool", "name": "result"}
        data = await _call(cfg, "POST", f"{ANTHROPIC}/messages", body)
        blocks = data.get("content") if isinstance(data, dict) else None
        if not isinstance(blocks, list):
            raise AIError(f"{cfg.label} returned no answer")
        if schema is not None:
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    return b.get("input")
        text = "".join(
            b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
        )

    else:
        messages = [{"role": "user", "content": prompt}]
        if system:
            messages.insert(0, {"role": "system", "content": system})
        body = {"model": cfg.model, "messages": messages}
        body["max_completion_tokens" if cfg.provider == "openai" else "max_tokens"] = max_tokens
        if schema is not None:
            # Structured output: the server constrains the reply to the schema, which
            # also keeps thinking models (Qwen, DeepSeek...) from spending the token
            # budget on reasoning before the JSON.
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": schema},
            }
        url = f"{_openai_base(cfg)}/chat/completions"
        try:
            data = await _call(cfg, "POST", url, body)
        except AIError as e:
            # Some OpenAI-compatible servers reject json_schema: retry once with the
            # schema in the prompt only.
            if (
                cfg.provider != "generic"
                or "response_format" not in body
                or e.upstream
                not in (
                    400,
                    422,
                )
            ):
                raise
            del body["response_format"]
            data = await _call(cfg, "POST", url, body)
        try:
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise AIError(f"{cfg.label} returned no answer") from e
        if not text.strip() and choice.get("finish_reason") == "length":
            raise AIError(
                f"{cfg.label}: the model used its whole token budget before answering "
                "(thinking models spend it on reasoning). Try a non-thinking model."
            )

    return _parse_json(text, cfg) if schema is not None else text
