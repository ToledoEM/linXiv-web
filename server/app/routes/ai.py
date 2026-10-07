"""AI provider checks for Settings → AI: list models, test the connection.

Both use the saved settings (never values from the request) and refuse while
`ai_enabled` is off.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from .. import ai
from .common import run

router = APIRouter(prefix="/api/ai", tags=["ai"])

TEST_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
}


async def _config(request: Request) -> ai.AIConfig:
    stored = await run(request, ["settings", "get"])
    try:
        return ai.config_from(stored if isinstance(stored, dict) else {})
    except ai.AIError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e


@router.get("/models")
async def models(request: Request):
    cfg = await _config(request)
    try:
        ids = await ai.list_models(cfg)
    except ai.AIError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    return {"provider": cfg.provider, "models": ids}


@router.post("/test")
async def test(request: Request):
    cfg = await _config(request)
    started = time.monotonic()
    try:
        reply = await ai.complete(
            cfg, 'Connection test. Reply {"ok": true}.', schema=TEST_SCHEMA, max_tokens=256
        )
    except ai.AIError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    return {
        "ok": isinstance(reply, dict) and reply.get("ok") is True,
        "provider": cfg.provider,
        "model": cfg.model,
        "ms": round((time.monotonic() - started) * 1000),
    }
