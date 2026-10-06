"""linXiv user settings (`linxiv settings get/update`), limited to an allowlist.

`settings update` accepts any key, and the store also holds p2p relay
credentials, so only the keys below are read or written through the web UI.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from .common import run
from .feed import clear_feed_cache

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
}
FEED_KEYS = ("home_feed_url", "rss_cache_retention_days")
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


async def _current(request: Request) -> dict:
    raw = await run(request, ["settings", "get"])
    raw = raw if isinstance(raw, dict) else {}
    values = {k: raw.get(k, d) for k, d in DEFAULTS.items()}
    for k in (*MAILTO_KEYS, "home_feed_url"):
        values[k] = values[k] or ""
    env_overrides = [k for k in MAILTO_KEYS if os.environ.get(k)]
    return {"settings": values, "env_overrides": env_overrides}


@router.get("/settings")
async def get_settings(request: Request):
    return await _current(request)


@router.patch("/settings")
async def update_settings(request: Request, body: SettingsPatch):
    patch = body.model_dump(exclude_none=True)
    for key, value in patch.items():
        # The CLI JSON-parses the value, so bools/ints go as JSON; an email is
        # never valid JSON and stays a string.
        arg = json.dumps(value) if isinstance(value, bool | int) else value
        await run(request, ["settings", "update", "--", key, arg])
    if any(k in patch for k in FEED_KEYS):
        clear_feed_cache(request)
    if "full_text_worker_enabled" in patch:
        # Start or stop the background indexer now, not at its next poll.
        request.app.state.fulltext_worker.wake()
    return await _current(request)
