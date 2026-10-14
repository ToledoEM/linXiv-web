"""linXiv user settings (`linxiv settings get/update`), limited to an allowlist.

`settings update` accepts any key, and the store also holds p2p relay
credentials, so only the keys below are read or written through the web UI.
"""

from __future__ import annotations

import json
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .. import logs
from ..activity import note_fields
from .common import run
from .feed import clear_feed_cache
from .mcp import settings_changed as mcp_settings_changed

router = APIRouter(prefix="/api", tags=["settings"])

# Contact addresses linXiv sends to arXiv / CrossRef / OpenAlex. An env var of
# the same name wins over the stored setting (linxiv core config::mailto_setting).
MAILTO_KEYS = ("ARXIV_MAILTO", "CROSSREF_MAILTO", "OPENALEX_MAILTO")
DEFAULTS: dict[str, object] = {
    "pdf_save_limit_mb": 1024,
    "tex_rendering_enabled": True,
    **{k: "" for k in MAILTO_KEYS},
    "home_feed_url": "",
    "rss_cache_retention_days": 30,
    "search_history_enabled": True,
    "search_history_max": 200,
    "full_text_worker_enabled": False,
    # Last layout applied in Settings → PDF folders (web-only key; linXiv ignores it).
    "web_pdf_folder_layout": "none",
    # Source preselected in Retrieve metadata (web-only key): "auto" picks by paper id/DOI.
    "web_lookup_source": "auto",
    # Lookup sources switched off in Settings (web-only key): comma list, "" = all on.
    "web_lookup_disabled": "",
    # App log level (web-only key); LINXIV_WEB_LOG_LEVEL applies until it is saved.
    "web_log_level": "",
    # Automatic release check (web-only key): off, daily, weekly or monthly.
    "web_update_check": "off",
    # AI features (web-only keys): off until the user opts in.
    "ai_enabled": False,
    "genai_provider": "gemini",
    "genai_model": "",
    "genai_base_url": "",
    # linXiv MCP over HTTP (web-only keys): off until the user opts in.
    "mcp_enabled": False,
    "mcp_profile": "read",
}
# Same values as SettingsPatch.web_lookup_source.
LOOKUP_SOURCES = ("auto", "crossref", "arxiv", "openalex", "pubmed", "biorxiv")
# Sources that can be switched off; "ai" is the AI cleanup candidate.
TOGGLE_SOURCES = (*LOOKUP_SOURCES[1:], "ai")
_SOURCE = "|".join(TOGGLE_SOURCES)
DISABLED_RE = rf"^$|^({_SOURCE})(,({_SOURCE}))*$"
FEED_KEYS = ("home_feed_url", "rss_cache_retention_days")
# NCBI E-utilities key for PubMed lookups (10 instead of 3 requests/s). A secret:
# stored like any setting but never sent back; the env var of the same name wins.
NCBI_KEY = "NCBI_API_KEY"
NCBI_KEY_RE = r"^$|^[A-Za-z0-9]{20,64}$"
# AI provider keys, write-only like NCBI_API_KEY; GENAI_API_KEY_TAG_GEN belongs
# to the generic OpenAI-compatible endpoint.
AI_KEYS = ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GENAI_API_KEY_TAG_GEN")
AI_KEY_RE = r"^$|^[\x21-\x7e]{8,256}$"
# GitHub token (read:packages) for the release check while the GHCR package is private.
GHCR_KEY = "GHCR_TOKEN"
SECRET_KEYS = (NCBI_KEY, *AI_KEYS, GHCR_KEY)
# Free-text values the CLI would otherwise JSON-parse ("123" -> int).
QUOTED_KEYS = (
    *SECRET_KEYS,
    "genai_provider",
    "genai_model",
    "genai_base_url",
    "mcp_profile",
    "web_lookup_source",
    "web_lookup_disabled",
    "web_log_level",
    "web_update_check",
)
MODEL_RE = r"^[A-Za-z0-9._:/@+-]{0,128}$"
BASE_URL = r"^$|^[Hh][Tt][Tt][Pp][Ss]?://[^\s/?#]+[^\s?#]*$"
EMAIL = r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$"
FEED_URL = r"^$|^[Hh][Tt][Tt][Pp][Ss]?://[^\s/?#]+[^\s]*$"


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    pdf_save_limit_mb: int | None = Field(None, ge=1, le=10_000_000)
    tex_rendering_enabled: bool | None = None
    ARXIV_MAILTO: str | None = Field(None, max_length=254, pattern=EMAIL)
    CROSSREF_MAILTO: str | None = Field(None, max_length=254, pattern=EMAIL)
    OPENALEX_MAILTO: str | None = Field(None, max_length=254, pattern=EMAIL)
    home_feed_url: str | None = Field(None, max_length=512, pattern=FEED_URL)
    rss_cache_retention_days: int | None = Field(None, ge=1, le=3650)
    search_history_enabled: bool | None = None
    search_history_max: int | None = Field(None, ge=1, le=10_000)
    full_text_worker_enabled: bool | None = None
    NCBI_API_KEY: str | None = Field(None, max_length=64, pattern=NCBI_KEY_RE)
    ai_enabled: bool | None = None
    genai_provider: Literal["gemini", "openai", "anthropic", "generic"] | None = None
    genai_model: str | None = Field(None, pattern=MODEL_RE)
    genai_base_url: str | None = Field(None, max_length=512, pattern=BASE_URL)
    GEMINI_API_KEY: str | None = Field(None, pattern=AI_KEY_RE)
    OPENAI_API_KEY: str | None = Field(None, pattern=AI_KEY_RE)
    ANTHROPIC_API_KEY: str | None = Field(None, pattern=AI_KEY_RE)
    GENAI_API_KEY_TAG_GEN: str | None = Field(None, pattern=AI_KEY_RE)
    mcp_enabled: bool | None = None
    mcp_profile: Literal["read", "write", "full"] | None = None
    web_lookup_source: (
        Literal["auto", "crossref", "arxiv", "openalex", "pubmed", "biorxiv"] | None
    ) = None
    web_lookup_disabled: str | None = Field(None, max_length=128, pattern=DISABLED_RE)
    web_log_level: Literal["debug", "info", "warning", "error"] | None = None
    web_update_check: Literal["off", "daily", "weekly", "monthly"] | None = None
    GHCR_TOKEN: str | None = Field(None, pattern=AI_KEY_RE)


async def _current(request: Request) -> dict:
    raw = await run(request, ["settings", "get"])
    raw = raw if isinstance(raw, dict) else {}
    values = {k: raw.get(k, d) for k, d in DEFAULTS.items()}
    for k in (*MAILTO_KEYS, "home_feed_url", "genai_model", "genai_base_url"):
        values[k] = values[k] or ""
    # Not saved yet: show the level in use (LINXIV_WEB_LOG_LEVEL or "info").
    if values["web_log_level"] not in logs.LEVELS:
        values["web_log_level"] = logs.level_name()
    if values["web_update_check"] not in ("off", "daily", "weekly", "monthly"):
        values["web_update_check"] = "off"
    if values["web_lookup_source"] not in LOOKUP_SOURCES:
        values["web_lookup_source"] = "auto"
    values["web_lookup_disabled"] = ",".join(
        s for s in TOGGLE_SOURCES if s in disabled_sources(raw)
    )
    env_overrides = [k for k in (*MAILTO_KEYS, *SECRET_KEYS) if os.environ.get(k)]
    return {
        # write-only: stored keys never leave the server
        "settings": {**values, **{k: "" for k in SECRET_KEYS}},
        "env_overrides": env_overrides,
        "ncbi_api_key": _status(raw, NCBI_KEY),
        "ai_keys": {k: _status(raw, k) for k in AI_KEYS},
        "ghcr_token": _status(raw, GHCR_KEY),
    }


def _status(stored: dict, name: str) -> dict:
    key, source = secret(stored, name)
    return {"set": bool(key), "last4": key[-4:] if key else None, "source": source}


def secret(stored: dict, name: str) -> tuple[str, str | None]:
    """(key, "env" | "settings" | None) — the env var wins over the stored setting."""
    if env := os.environ.get(name, "").strip():
        return env, "env"
    saved = stored.get(name) if isinstance(stored, dict) else None
    if isinstance(saved, str) and saved.strip():
        return saved.strip(), "settings"
    return "", None


def ncbi_api_key(stored: dict) -> tuple[str, str | None]:
    return secret(stored, NCBI_KEY)


def disabled_sources(stored: dict) -> set[str]:
    """Lookup sources switched off in Settings; unknown names are ignored."""
    raw = stored.get("web_lookup_disabled") if isinstance(stored, dict) else None
    if not isinstance(raw, str):
        return set()
    return {s for s in raw.split(",") if s in TOGGLE_SOURCES}


async def _check_lookup(request: Request, patch: dict) -> None:
    """Keep at least one non-AI source on and the default source switched on.
    Rewrites the disabled list in a fixed order."""
    stored = await run(request, ["settings", "get"])
    stored = stored if isinstance(stored, dict) else {}
    if "web_lookup_disabled" in patch:
        names = [s for s in patch["web_lookup_disabled"].split(",") if s]
        if len(names) != len(set(names)):
            raise HTTPException(status_code=400, detail="Lookup source listed twice")
        off = set(names)
        patch["web_lookup_disabled"] = ",".join(s for s in TOGGLE_SOURCES if s in off)
    else:
        off = disabled_sources(stored)
    if all(s in off for s in LOOKUP_SOURCES[1:]):
        raise HTTPException(status_code=400, detail="Keep at least one lookup source on")
    default = patch.get("web_lookup_source", stored.get("web_lookup_source"))
    if default in off:
        raise HTTPException(
            status_code=400, detail=f"Default lookup source {default} is switched off"
        )


@router.get("/settings")
async def get_settings(request: Request):
    return await _current(request)


@router.patch("/settings")
async def update_settings(request: Request, body: SettingsPatch):
    patch = body.model_dump(exclude_none=True)
    note_fields(request, patch)  # key names only, never values (API keys)
    if "web_lookup_disabled" in patch or "web_lookup_source" in patch:
        await _check_lookup(request, patch)
    for key, value in patch.items():
        # The CLI JSON-parses the value, so bools/ints go as JSON; an email is
        # never valid JSON and stays a string.
        arg = json.dumps(value) if isinstance(value, bool | int) else value
        if key in QUOTED_KEYS:
            arg = json.dumps(value)  # quoted, so an all-digit value stays a string
        await run(request, ["settings", "update", "--", key, arg])
    if any(k in patch for k in FEED_KEYS):
        clear_feed_cache(request)
    if any(k.startswith("mcp_") for k in patch):
        await mcp_settings_changed(request.app, patch)
    if "web_log_level" in patch:
        logs.set_level(patch["web_log_level"])
    if "full_text_worker_enabled" in patch:
        # Start or stop the background indexer now, not at its next poll.
        request.app.state.fulltext_worker.wake()
    if "web_update_check" in patch or GHCR_KEY in patch:
        request.app.state.update_checker.wake()
    return await _current(request)
