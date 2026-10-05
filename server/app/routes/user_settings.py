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

router = APIRouter(prefix="/api", tags=["settings"])

# Contact addresses linXiv sends to arXiv / CrossRef / OpenAlex. An env var of
# the same name wins over the stored setting (linxiv core config::mailto_setting).
MAILTO_KEYS = ("ARXIV_MAILTO", "CROSSREF_MAILTO", "OPENALEX_MAILTO")
DEFAULTS: dict[str, object] = {
    "pdf_save_limit_mb": 1024,
    "tex_rendering_enabled": True,
    **{k: "" for k in MAILTO_KEYS},
}
EMAIL = r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$"


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    pdf_save_limit_mb: int | None = Field(None, ge=1, le=10_000_000)
    tex_rendering_enabled: bool | None = None
    ARXIV_MAILTO: str | None = Field(None, max_length=254, pattern=EMAIL)
    CROSSREF_MAILTO: str | None = Field(None, max_length=254, pattern=EMAIL)
    OPENALEX_MAILTO: str | None = Field(None, max_length=254, pattern=EMAIL)


async def _current(request: Request) -> dict:
    raw = await run(request, ["settings", "get"])
    raw = raw if isinstance(raw, dict) else {}
    values = {k: raw.get(k, d) for k, d in DEFAULTS.items()}
    for k in MAILTO_KEYS:
        values[k] = values[k] or ""
    env_overrides = [k for k in MAILTO_KEYS if os.environ.get(k)]
    return {"settings": values, "env_overrides": env_overrides}


@router.get("/settings")
async def get_settings(request: Request):
    return await _current(request)


@router.patch("/settings")
async def update_settings(request: Request, body: SettingsPatch):
    for key, value in body.model_dump(exclude_none=True).items():
        # The CLI JSON-parses the value, so bools/ints go as JSON; an email is
        # never valid JSON and stays a string.
        arg = json.dumps(value) if isinstance(value, bool | int) else value
        await run(request, ["settings", "update", "--", key, arg])
    return await _current(request)
