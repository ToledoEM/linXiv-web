"""Home RSS/Atom feed (`linxiv feed ...`).

The feed URL is the stored `home_feed_url` setting, never a request parameter,
so this route can't be pointed at arbitrary hosts per request. The CLI itself
only fetches http(s) URLs that resolve to public addresses (re-checked per
redirect), with a 15 s budget and a 2 MB cap.

`feed get` re-downloads the feed on every call, so the page is cached here for
a few minutes per URL; rule and settings changes clear it, dismissals prune it.
"""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..cli import CLIError
from .common import ident, run

router = APIRouter(prefix="/api", tags=["feed"])

CACHE_TTL = 300.0
ARXIV_ID = r"^(\d{4}\.\d{4,5}|[a-z-]+(\.[A-Z]{2})?/\d{7})$"


def _cache(request: Request) -> dict[str, tuple[float, object]]:
    state = request.app.state
    if not hasattr(state, "feed_cache"):
        state.feed_cache = {}
    return state.feed_cache


def clear_feed_cache(request: Request) -> None:
    _cache(request).clear()


class DismissBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    arxiv_id: str = Field(pattern=ARXIV_ID, max_length=64)
    version: int = Field(ge=1, le=10_000)
    permanent: bool = False


class RuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: Literal["TITLE", "SUMMARY", "AUTHOR"]
    keywords: str = Field(min_length=1, max_length=1000)
    action: Literal["DENY", "ALLOW"] = "DENY"


@router.get("/feed")
async def get_feed(request: Request, refresh: bool = False):
    """`{configured: false}` when no feed URL is set; else the CLI page plus `url`."""
    stored = await run(request, ["settings", "get"])
    url = (stored.get("home_feed_url") if isinstance(stored, dict) else None) or ""
    url = url.strip()
    if not url:
        return {"configured": False}
    cache = _cache(request)
    hit = cache.get(url)
    if hit and not refresh and time.monotonic() - hit[0] < CACHE_TTL:
        page = hit[1]
    else:
        page = await run(request, ["feed", "get", "--", ident(url, "feed URL")], long=True)
        cache.clear()
        cache[url] = (time.monotonic(), page)
    return {"configured": True, "url": url, **(page if isinstance(page, dict) else {})}


@router.post("/feed/dismiss")
async def dismiss(request: Request, body: DismissBody):
    args = ["feed", "dismiss", f"--version={body.version}"]
    if body.permanent:
        args.append("--permanent")
    out = await run(request, [*args, "--", body.arxiv_id])
    # Drop the entry from cached pages instead of refetching the feed.
    for _, page in _cache(request).values():
        if isinstance(page, dict) and isinstance(page.get("entries"), list):
            page["entries"] = [
                e
                for e in page["entries"]
                if not (
                    isinstance(e, dict)
                    and e.get("arxiv_id") == body.arxiv_id
                    and (body.permanent or e.get("version") == body.version)
                )
            ]
    return out


@router.get("/feed/rules")
async def list_rules(request: Request):
    return await run(request, ["feed", "rules", "list"])


@router.post("/feed/rules")
async def add_rule(request: Request, body: RuleBody):
    keywords = ",".join(k.strip() for k in body.keywords.split(",") if k.strip())
    keywords = ident(keywords, "keywords")
    out = await run(
        request,
        [
            "feed",
            "rules",
            "add",
            f"--field={body.field}",
            f"--keywords={keywords}",
            f"--action={body.action}",
        ],
    )
    clear_feed_cache(request)
    return out


@router.delete("/feed/rules/{rule_id}")
async def delete_rule(request: Request, rule_id: int):
    try:
        out = await run(request, ["feed", "rules", "delete", "--", str(rule_id)])
    except CLIError as e:
        if "no such rule" in e.message:
            raise HTTPException(status_code=404, detail="rule not found") from e
        raise
    clear_feed_cache(request)
    return out
