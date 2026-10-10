"""New linXiv-web releases: the highest x.y.z tag of the GHCR image.

Anonymous pulls work only while the package is public; a GitHub token with
`read:packages` (setting/env `GHCR_TOKEN`) reads a private one. The checker
runs on demand (`check()`) and, when `web_update_check` is daily/weekly/
monthly, in a background loop like the full-text worker. The last result is
kept in the web-only setting `web_update_status` (JSON string, never PATCHable).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import UTC, datetime

import httpx

from .cli import CLIError, Runner

log = logging.getLogger(__name__)

IMAGE = "ghcr.io/toledoem/linxiv-web"
TOKEN_URL = "https://ghcr.io/token?scope=repository:toledoem/linxiv-web:pull&service=ghcr.io"
TAGS_URL = "https://ghcr.io/v2/toledoem/linxiv-web/tags/list?n=1000"
MODE_SETTING = "web_update_check"
STATUS_SETTING = "web_update_status"
TOKEN_SETTING = "GHCR_TOKEN"
INTERVALS = {"daily": 86_400, "weekly": 7 * 86_400, "monthly": 30 * 86_400}
OFF_POLL = 3600  # settings re-read while off (PATCH wakes it sooner)
RETRY_AFTER = 3600  # after a failed scheduled check
MAX_WAIT = 6 * 3600
MAX_BYTES = 1024 * 1024
_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


class UpdateError(Exception):
    pass


def parse_version(tag: str) -> tuple[int, int, int] | None:
    m = _SEMVER.match(tag.strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def latest_tag(tags: list) -> str | None:
    """Highest strict x.y.z (optional v) tag; other tags (sha-…, latest) ignored."""
    best = None
    for tag in tags:
        v = parse_version(str(tag))
        if v and (best is None or v > best[0]):
            best = (v, str(tag))
    return best[1] if best else None


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=15, follow_redirects=False, headers={"User-Agent": "linxiv-web"}
    )


async def _get_json(client: httpx.AsyncClient, url: str, **kw) -> dict:
    async with client.stream("GET", url, **kw) as r:
        if r.status_code in (401, 403):
            raise UpdateError(
                "image not readable: the package is private; add a GitHub token "
                "with read:packages (Settings → About)"
            )
        if r.status_code == 404:
            raise UpdateError("image not found on ghcr.io")
        if r.status_code != 200:
            raise UpdateError(f"ghcr.io answered HTTP {r.status_code}")
        body = b""
        async for chunk in r.aiter_bytes():
            body += chunk
            if len(body) > MAX_BYTES:
                raise UpdateError("ghcr.io reply too large")
    try:
        data = json.loads(body)
    except ValueError as e:
        raise UpdateError("ghcr.io reply is not JSON") from e
    if not isinstance(data, dict):
        raise UpdateError("ghcr.io reply has an unexpected shape")
    return data


async def fetch_tags(token: str = "") -> list:
    async with _client() as client:
        auth = ("token", token) if token else None
        grant = await _get_json(client, TOKEN_URL, auth=auth)
        bearer = grant.get("token")
        if not isinstance(bearer, str) or not bearer:
            raise UpdateError("ghcr.io gave no pull token")
        tags = await _get_json(client, TAGS_URL, headers={"Authorization": f"Bearer {bearer}"})
    found = tags.get("tags")
    return found if isinstance(found, list) else []


def _token(stored: dict) -> str:
    if env := os.environ.get(TOKEN_SETTING, "").strip():
        return env
    saved = stored.get(TOKEN_SETTING)
    return saved.strip() if isinstance(saved, str) else ""


def stored_status(stored: dict) -> dict:
    raw = stored.get(STATUS_SETTING) if isinstance(stored, dict) else None
    try:
        data = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        data = None
    return data if isinstance(data, dict) else {}


def _mode(stored: dict) -> str:
    mode = stored.get(MODE_SETTING) if isinstance(stored, dict) else None
    return mode if mode in INTERVALS else "off"


def _parse_time(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


class UpdateChecker:
    def __init__(self, cli: Runner, version: str, timeout: float, fetch=fetch_tags, now=None):
        self.cli = cli
        self.version = version
        self.timeout = timeout
        self.fetch = fetch
        self.now = now or (lambda: datetime.now(UTC))
        self._wake = asyncio.Event()

    def wake(self) -> None:
        self._wake.set()

    async def _settings(self) -> dict:
        out = await self.cli(["settings", "get"], self.timeout)
        return out if isinstance(out, dict) else {}

    def view(self, stored: dict) -> dict:
        """What the About card shows: last result + current version and mode."""
        status = stored_status(stored)
        latest = status.get("latest")
        current, newest = parse_version(self.version), parse_version(str(latest or ""))
        return {
            "current": self.version,
            "latest": latest,
            "update_available": bool(current and newest and newest > current),
            "checked_at": status.get("checked_at"),
            "error": status.get("error"),
            "image": IMAGE,
            "mode": _mode(stored),
        }

    async def check(self) -> dict:
        """Ask GHCR now, store the result, return the About view."""
        stored = await self._settings()
        status: dict = {"checked_at": self.now().isoformat(timespec="seconds")}
        try:
            status["latest"] = latest_tag(await self.fetch(_token(stored)))
            if status["latest"] is None:
                status["error"] = "no x.y.z release tags on the image"
        except UpdateError as e:
            status["error"] = str(e)
        except httpx.HTTPError as e:
            status["error"] = f"could not reach ghcr.io ({type(e).__name__})"
        if status.get("error"):
            log.warning("update check failed: %s", status["error"])
        else:
            log.info("update check: latest %s, running %s", status["latest"], self.version)
        prev = stored_status(stored)
        if status.get("latest") is None and prev.get("latest"):
            status["latest"] = prev["latest"]  # keep the last known release on failure
        await self.cli(
            ["settings", "update", "--", STATUS_SETTING, json.dumps(json.dumps(status))],
            self.timeout,
        )
        return self.view({**stored, STATUS_SETTING: json.dumps(status)})

    async def step(self) -> float:
        """One loop turn: check when due; seconds to sleep next."""
        try:
            stored = await self._settings()
        except CLIError:
            return OFF_POLL
        mode = _mode(stored)
        if mode == "off":
            return OFF_POLL
        last = _parse_time(stored_status(stored).get("checked_at"))
        due = INTERVALS[mode] - ((self.now() - last).total_seconds() if last else INTERVALS[mode])
        if due > 0:
            return min(due, MAX_WAIT)
        view = await self.check()
        return RETRY_AFTER if view.get("error") else min(INTERVALS[mode], MAX_WAIT)

    async def run(self) -> None:
        while True:
            try:
                wait = await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("update checker step failed")
                wait = OFF_POLL
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=wait)
            except TimeoutError:
                pass
            finally:
                self._wake.clear()
