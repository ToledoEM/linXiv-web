"""Diagnostics report for bug reports (Settings → About): Markdown, safe to paste.

Holds versions, configuration, library counts, disk, health issues, running jobs
and whether outside services resolve and accept a connection. Secrets appear only
as set/unset and where they come from; addresses that could locate the server
(AI base URL, feed URL, trusted proxies) appear only as set/unset.
"""

from __future__ import annotations

import asyncio
import os
import platform
import sys
from datetime import UTC, datetime

from .routes.user_settings import SECRET_KEYS, secret

# Services the server talks to (metadata lookups, feed, update check).
SERVICES = (
    "export.arxiv.org",
    "api.crossref.org",
    "api.openalex.org",
    "eutils.ncbi.nlm.nih.gov",
    "api.biorxiv.org",
    "ghcr.io",
)
CONNECT_TIMEOUT = 3.0
# Non-secret settings worth seeing; anything else stays out.
SHOWN_SETTINGS = (
    "ai_enabled",
    "genai_provider",
    "genai_model",
    "mcp_enabled",
    "mcp_profile",
    "full_text_worker_enabled",
    "web_update_check",
    "web_log_level",
    "web_lookup_source",
    "pdf_save_limit_mb",
    "search_history_enabled",
)
SET_ONLY = ("genai_base_url", "home_feed_url")


async def reach(host: str, port: int = 443) -> str:
    """ "ok", or why not: DNS failure or connect failure (type only)."""
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(loop.getaddrinfo(host, port), CONNECT_TIMEOUT)
    except (OSError, TimeoutError) as e:
        return f"DNS failed ({type(e).__name__})"
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), CONNECT_TIMEOUT)
    except (OSError, TimeoutError) as e:
        return f"connect failed ({type(e).__name__})"
    writer.close()
    return "ok"


def _yes(value: object) -> str:
    return "set" if value else "not set"


def render(
    *,
    version: str,
    settings,
    login_from: str | None,
    stored: dict,
    stats: dict | None,
    status: dict,
    jobs: list[dict],
    reachability: dict[str, str],
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# linXiv-web diagnostics",
        "",
        f"Generated {now}.",
        "",
        "## Versions",
        "",
        f"- linXiv-web: {version}",
        f"- linXiv (bundled CLI): {os.environ.get('LINXIV_WEB_LINXIV_REF') or 'unknown'}",
        f"- Python: {sys.version.split()[0]} on {platform.system()} {platform.machine()}",
        "",
        "## Configuration",
        "",
        f"- Listen: {settings.host}:{settings.port}",
        f"- Data dir: {settings.data_dir}",
        f"- PDF dir: {settings.pdf_dir}",
        f"- Login password: {login_from or 'none'}",
        f"- Secure cookies: {settings.cookie_secure}; HSTS: {settings.hsts}",
        f"- Public clients allowed: {settings.allow_external}",
        f"- Trusted proxies: {len(settings.trusted_proxies)} listed",
        f"- Session signing key: {'env' if settings.secret_key else 'stored'}",
        f"- Upload cap: {settings.max_upload_mb} MB; CLI timeouts: "
        f"{settings.timeout_short:g}s / {settings.timeout_long:g}s",
        "",
        "## Settings",
        "",
    ]
    for key in SHOWN_SETTINGS:
        if key in stored:
            lines.append(f"- {key}: {stored[key]}")
    for key in SET_ONLY:
        lines.append(f"- {key}: {_yes(stored.get(key))}")
    for key in SECRET_KEYS:
        _, source = secret(stored, key)
        lines.append(f"- {key}: {f'set ({source})' if source else 'not set'}")

    lines += ["", "## Library", ""]
    if stats is None:
        lines.append("- linxiv CLI did not answer `stats`")
    else:
        for key in ("paper_count", "pdf_count", "tag_count", "category_count"):
            if key in stats:
                lines.append(f"- {key}: {stats[key]}")

    lines += [
        "",
        "## Disk",
        "",
        "| Folder | Used | Files | Free | Total |",
        "|---|---|---|---|---|",
    ]
    for row in status.get("disk", []):
        if row.get("error"):
            lines.append(f"| {row['label']} | error: {row['error']} | | | |")
            continue
        mb = 1024 * 1024
        lines.append(
            f"| {row['label']} | {row['used'] / mb:.1f} MB | {row['files']} | "
            f"{row['free'] / mb / 1024:.1f} GB | {row['total'] / mb / 1024:.1f} GB |"
        )

    lines += ["", "## Health", ""]
    issues = status.get("issues", [])
    lines += [f"- {i['level']}: {i['message']}" for i in issues] or ["- no issues"]

    lines += ["", "## Jobs", ""]
    lines += [
        f"- {j['kind']}: {j['state']} ({j.get('done', 0)}/{j.get('total', 0)})" for j in jobs
    ] or ["- none"]

    lines += ["", "## Outside services (DNS + TCP 443)", ""]
    lines += [f"- {host}: {result}" for host, result in reachability.items()]
    return "\n".join(lines) + "\n"
