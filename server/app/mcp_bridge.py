"""Bridge from MCP Streamable HTTP (`/mcp`) to linXiv's stdio MCP server.

Each MCP session (one `initialize`) gets its own `linxiv-mcp` subprocess;
JSON-RPC messages are written to its stdin one per line and the matching
response is read back from stdout. Requests in one session run one at a time.

Which tools a client may see and call is decided here (allowlist per profile);
tools that touch server settings or server file paths are never exposed.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

# --- tool policy -----------------------------------------------------------

# Never exposed: settings hold API keys; the rest read or write server paths.
ALWAYS_BLOCKED = frozenset(
    {
        "get_settings",
        "update_setting",
        "backup_database",
        "restore_database",
        "import_pdf",
        "import_bibtex",
        "import_zotero",
        "import_project",
        "export_project",
        "export_project_bibtex",
        "export_project_obsidian",
        "export_project_zotero",
        "set_full_text",
    }
)
READ_TOOLS = frozenset(
    {
        "author_merge_candidates",
        "find_doi_candidates",
        "full_text_pending",
        "get_annotation",
        "get_author",
        "get_note",
        "get_notes_for_paper",
        "get_notes_for_project",
        "get_paper",
        "get_paper_tags",
        "get_paper_versions",
        "get_pdf_path",
        "get_pdf_storage",
        "get_project",
        "get_project_tags",
        "get_stats",
        "list_all_tags",
        "list_annotations",
        "list_authors",
        "list_categories",
        "list_feed_rules",
        "list_new_versions",
        "list_notes",
        "list_papers",
        "list_pdfs",
        "list_projects",
        "list_trash",
        "paper_ref",
        "resolve_doi",
        "resolve_refs",
        "search_full_text",
        "search_papers",
    }
)
# Library edits that can be undone (soft deletes go to the trash).
WRITE_TOOLS = READ_TOOLS | {
    "ack_version",
    "add_paper_to_project",
    "add_papers_to_project",
    "add_tags_to_paper",
    "add_tags_to_project",
    "archive_project",
    "check_versions",
    "create_annotation",
    "create_feed_rule",
    "create_note",
    "create_project",
    "create_tag",
    "delete_annotation",
    "delete_feed_rule",
    "delete_note",
    "delete_paper",
    "delete_project",
    "delete_tag",
    "dismiss_feed_entry",
    "download_pdf",
    "fetch_full_text",
    "fetch_paper",
    "get_feed",
    "orcid_backfill",
    "remove_paper_from_all_projects",
    "remove_paper_from_project",
    "remove_tags_from_paper",
    "remove_tags_from_project",
    "restore_paper",
    "restore_project",
    "restore_project_from_trash",
    "save_doi",
    "update_annotation",
    "update_author",
    "update_note",
    "update_project",
}
# Also permanent changes: hard deletes, merges, metadata overwrite.
FULL_TOOLS = WRITE_TOOLS | {
    "delete_author",
    "delete_pdf",
    "hard_delete_project_from_trash",
    "merge_authors",
    "merge_papers",
    "repair_paper",
    "trash_hard_delete_paper",
}
PROFILES: dict[str, frozenset[str]] = {
    "read": READ_TOOLS - ALWAYS_BLOCKED,
    "write": frozenset(WRITE_TOOLS - ALWAYS_BLOCKED),
    "full": frozenset(FULL_TOOLS - ALWAYS_BLOCKED),
}
# Repeating the call with the same arguments changes nothing further.
IDEMPOTENT_TOOLS = frozenset(
    {
        "ack_version",
        "add_paper_to_project",
        "add_papers_to_project",
        "add_tags_to_paper",
        "add_tags_to_project",
        "archive_project",
        "create_tag",
        "remove_paper_from_all_projects",
        "remove_paper_from_project",
        "remove_tags_from_paper",
        "remove_tags_from_project",
        "restore_paper",
        "restore_project",
        "restore_project_from_trash",
    }
)
# Reach outside services (arXiv, DOI resolvers, feeds, ORCID sources).
OPEN_WORLD_TOOLS = frozenset(
    {
        "check_versions",
        "download_pdf",
        "fetch_full_text",
        "fetch_paper",
        "get_feed",
        "orcid_backfill",
        "resolve_doi",
        "save_doi",
        "search_papers",
    }
)


def allowed(profile: str, name: object) -> bool:
    return isinstance(name, str) and name in PROFILES.get(profile, PROFILES["read"])


def annotations_for(name: str) -> dict[str, Any]:
    """MCP tool annotations (client hints) derived from the tool's tier; linxiv-mcp sets none."""
    hints: dict[str, Any] = {"title": name.replace("_", " ").capitalize()}
    if name in READ_TOOLS:
        hints["readOnlyHint"] = True
    else:
        hints["readOnlyHint"] = False
        hints["destructiveHint"] = name not in WRITE_TOOLS
        hints["idempotentHint"] = name in IDEMPOTENT_TOOLS
    hints["openWorldHint"] = name in OPEN_WORLD_TOOLS
    return hints


def call_refusal(profile: str, params: object) -> str | None:
    """Why a `tools/call` must not reach linxiv-mcp, or None."""
    params = params if isinstance(params, dict) else {}
    name = params.get("name")
    if not allowed(profile, name):
        return f"Tool not available on this server: {name}"
    args = params.get("arguments")
    # download_pdf with a caller-chosen URL would fetch any host from the server.
    if name == "download_pdf" and isinstance(args, dict) and args.get("url"):
        return "download_pdf: the url argument is not allowed here; the paper's stored link is used"
    return None


def filter_tools(profile: str, result: object) -> object:
    if isinstance(result, dict) and isinstance(result.get("tools"), list):
        # Upstream annotations, if linXiv ever sets them, win over the derived ones.
        tools = [
            {**t, "annotations": {**annotations_for(t["name"]), **(t.get("annotations") or {})}}
            for t in result["tools"]
            if isinstance(t, dict) and allowed(profile, t.get("name"))
        ]
        return {**result, "tools": tools}
    return result


# --- sessions --------------------------------------------------------------


class BridgeError(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class Session:
    id: str
    proc: asyncio.subprocess.Process
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default_factory=time.monotonic)


class McpBridge:
    MAX_SESSIONS = 4
    IDLE_SECONDS = 30 * 60
    LINE_LIMIT = 16 * 1024 * 1024

    def __init__(self, command: list[str], env: dict[str, str], timeout: float = 300) -> None:
        self.command = command
        self.env = env
        self.timeout = timeout
        self.sessions: dict[str, Session] = {}

    async def open(self) -> Session:
        await self.reap()
        if len(self.sessions) >= self.MAX_SESSIONS:
            # Make room by dropping the least recently used idle session.
            idle = [s for s in self.sessions.values() if not s.lock.locked()]
            if not idle:
                raise BridgeError("Too many MCP sessions", 503)
            await self.close(min(idle, key=lambda s: s.last_used).id)
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={**os.environ, "RUST_LOG": "warn", **self.env},
                limit=self.LINE_LIMIT,
            )
        except FileNotFoundError as e:
            raise BridgeError(f"MCP server binary not found: {self.command[0]}", 500) from e
        session = Session(secrets.token_urlsafe(24), proc)
        self.sessions[session.id] = session
        return session

    def get(self, session_id: str | None) -> Session | None:
        return self.sessions.get(session_id or "")

    async def send(self, session: Session, message: dict) -> Any:
        """Forward one message; for a request, return the matching response."""
        async with session.lock:
            session.last_used = time.monotonic()
            proc = session.proc
            if proc.stdin is None or proc.stdout is None or proc.returncode is not None:
                await self.close(session.id)
                raise BridgeError("MCP session ended", 404)
            try:
                proc.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
                await proc.stdin.drain()
                if "id" not in message or "method" not in message:
                    return None  # notification or client response: nothing comes back
                return await asyncio.wait_for(self._response(proc, message["id"]), self.timeout)
            except TimeoutError:
                await self.close(session.id)
                raise BridgeError("linxiv-mcp did not answer in time", 504) from None
            except (BrokenPipeError, ConnectionResetError, ValueError) as e:
                # ValueError: a stdout line over LINE_LIMIT; the stream can't recover.
                await self.close(session.id)
                raise BridgeError(f"MCP session failed ({type(e).__name__})") from e
            finally:
                session.last_used = time.monotonic()

    @staticmethod
    async def _response(proc: asyncio.subprocess.Process, request_id: object) -> dict:
        if proc.stdout is None:
            raise BrokenPipeError("linxiv-mcp has no stdout")
        while True:
            line = await proc.stdout.readline()
            if not line:
                raise BrokenPipeError("linxiv-mcp exited")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            # Skip server notifications/requests; linxiv-mcp sends none we relay.
            if isinstance(msg, dict) and msg.get("id") == request_id and "method" not in msg:
                return msg

    async def close(self, session_id: str) -> bool:
        session = self.sessions.pop(session_id, None)
        if session is None:
            return False
        proc = session.proc
        if proc.returncode is None:
            if proc.stdin is not None:
                proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), 2)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        return True

    async def reap(self) -> None:
        now = time.monotonic()
        for s in list(self.sessions.values()):
            if s.proc.returncode is not None or (
                not s.lock.locked() and now - s.last_used > self.IDLE_SECONDS
            ):
                await self.close(s.id)

    async def close_all(self) -> None:
        for sid in list(self.sessions):
            await self.close(sid)
