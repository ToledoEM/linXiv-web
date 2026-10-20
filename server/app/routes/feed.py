"""Home RSS/Atom feed (`linxiv feed ...`).

The feed URL is the stored `home_feed_url` setting, never a request parameter,
so this route can't be pointed at arbitrary hosts per request. The CLI itself
only fetches http(s) URLs that resolve to public addresses (re-checked per
redirect), with a 15 s budget and a 2 MB cap.

`feed get` re-downloads the feed on every call, so the page is cached here for
a few minutes per URL; rule and settings changes clear it, dismissals prune it.
"""

from __future__ import annotations

import random
import time
from email.utils import parsedate_to_datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
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


def _published_at(entry: dict) -> float:
    """Sort key for merged entries: `published` is RFC-822 ("Tue, 06 Oct 2026 ...")."""
    raw = entry.get("published")
    if isinstance(raw, str) and raw.strip():
        try:
            return parsedate_to_datetime(raw).timestamp()
        except (TypeError, ValueError):
            pass
    return 0.0


async def _page_for(request: Request, feed: dict, refresh: bool) -> object:
    """One feed's page, from the cache when it is still fresh."""
    url = feed["url"]
    cache = _cache(request)
    hit = cache.get(url)
    if hit and not refresh and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1]
    page = await run(request, ["feed", "get", "--", ident(url, "feed URL")], long=True)
    # Keep one entry per URL and drop pages for feeds that are no longer configured.
    now = time.monotonic()
    for key in [k for k, (ts, _) in cache.items() if now - ts > CACHE_TTL * 4]:
        del cache[key]
    cache[url] = (now, page)
    return page


@router.get("/feed")
async def get_feed(
    request: Request,
    refresh: bool = False,
    feed: str = "all",
    sample: int | None = Query(None, ge=1, le=200),
):
    """Entries from every configured feed, merged.

    `feed` picks one by id (default `all`); `sample` returns a random slice of the
    merged page. The URLs come only from stored settings, never from the request.
    """
    # Imported here: user_settings imports clear_feed_cache from this module.
    from .user_settings import parse_feeds

    stored = await run(request, ["settings", "get"])
    stored = stored if isinstance(stored, dict) else {}
    feeds = [f for f in parse_feeds(stored) if f["enabled"]]
    if feed != "all":
        feeds = [f for f in feeds if f["id"] == feed]
    if not feeds:
        return {"configured": False}

    entries: list[dict] = []
    saved: list[str] = []
    errors: list[dict] = []
    titles: list[str] = []
    seen: set[tuple] = set()
    for f in feeds:
        try:
            page = await _page_for(request, f, refresh)
        except CLIError as e:
            # One dead feed must not blank the whole page.
            errors.append({"id": f["id"], "name": f["name"], "error": e.message})
            continue
        if not isinstance(page, dict):
            continue
        if isinstance(page.get("title"), str):
            titles.append(page["title"])
        for sid in page.get("saved_arxiv_ids") or []:
            if sid not in saved:
                saved.append(sid)
        for e in page.get("entries") or []:
            if not isinstance(e, dict):
                continue
            # The same paper can sit in two category feeds; keep the first copy.
            key = (e.get("arxiv_id"), e.get("version"), e.get("link"))
            if key in seen:
                continue
            seen.add(key)
            entries.append({**e, "feed_id": f["id"], "feed_name": f["name"]})

    # Nothing loaded at all: report it as an error rather than as an empty feed.
    if errors and len(errors) == len(feeds):
        raise CLIError(502, "; ".join(f"{e['name']}: {e['error']}" for e in errors))
    if len(feeds) > 1:
        entries.sort(key=_published_at, reverse=True)
    if sample and len(entries) > sample:
        entries = random.sample(entries, sample)
    return {
        "configured": True,
        "url": feeds[0]["url"] if len(feeds) == 1 else "",
        "title": titles[0] if len(titles) == 1 else "Home feed",
        "entries": entries,
        "saved_arxiv_ids": saved,
        "feeds": [{"id": f["id"], "name": f["name"]} for f in parse_feeds(stored) if f["enabled"]],
        "errors": errors,
    }


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
