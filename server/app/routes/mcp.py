"""linXiv MCP over HTTP for Claude Code / Codex (opt-in).

`/mcp` speaks MCP Streamable HTTP (JSON responses, no SSE stream) and is
authenticated by its own bearer token, not the browser session: it sits
outside the cookie/CSRF guard. `/api/mcp/*` (guarded) shows the status and
creates or revokes the token. The token is shown once; only its SHA-256 is
stored, in web-only linXiv settings that the settings API never returns.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from ..mcp_bridge import PROFILES, BridgeError, McpBridge, call_refusal, filter_tools
from .common import run_root

router = APIRouter(prefix="/api/mcp", tags=["mcp"])
endpoint = APIRouter(tags=["mcp"])

HASH_KEY = "web_mcp_token_hash"
HINT_KEY = "web_mcp_token_hint"
CREATED_KEY = "web_mcp_token_created"
MAX_BODY = 1024 * 1024


def _bridge(request: Request) -> McpBridge:
    return request.app.state.mcp


async def _conf(request: Request) -> dict:
    """MCP settings, cached: only this server writes them (the MCP tool
    `update_setting` is never exposed), and it drops the cache when it does."""
    conf = getattr(request.app.state, "mcp_conf", None)
    if conf is None:
        raw = await run_root(request, ["settings", "get"])
        raw = raw if isinstance(raw, dict) else {}
        profile = raw.get("mcp_profile")
        conf = {
            "enabled": raw.get("mcp_enabled") is True,
            "profile": profile if profile in PROFILES else "read",
            "hash": raw.get(HASH_KEY) if isinstance(raw.get(HASH_KEY), str) else "",
            "hint": raw.get(HINT_KEY) or None,
            "created": raw.get(CREATED_KEY) or None,
        }
        request.app.state.mcp_conf = conf
    return conf


async def settings_changed(app: FastAPI, patch: dict) -> None:
    """Called by the settings route after it saved `mcp_*` keys."""
    app.state.mcp_conf = None
    if patch.get("mcp_enabled") is False:
        await app.state.mcp.close_all()


# --- status + token (browser, guarded) -------------------------------------


@router.get("")
async def status(request: Request):
    conf = await _conf(request)
    return {
        "enabled": conf["enabled"],
        "profile": conf["profile"],
        "token": {"set": bool(conf["hash"]), "hint": conf["hint"], "created": conf["created"]},
        "sessions": len(_bridge(request).sessions),
        "tool_counts": {k: len(v) for k, v in PROFILES.items()},
    }


async def _store_token(request: Request, digest: str, hint: str, created: str) -> None:
    for key, value in ((HASH_KEY, digest), (HINT_KEY, hint), (CREATED_KEY, created)):
        await run_root(request, ["settings", "update", "--", key, json.dumps(value)])
    request.app.state.mcp_conf = None
    # Sessions opened with the old token end now.
    await _bridge(request).close_all()


@router.post("/token")
async def create_token(request: Request):
    """New token, returned this once; replaces any previous one."""
    token = "lxmcp_" + secrets.token_urlsafe(32)
    created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    await _store_token(request, hashlib.sha256(token.encode()).hexdigest(), token[-4:], created)
    return {"token": token, "hint": token[-4:], "created": created}


@router.delete("/token")
async def revoke_token(request: Request):
    await _store_token(request, "", "", "")
    return {"ok": True}


# --- /mcp (MCP clients, bearer token) --------------------------------------


def _rpc_error(msg_id: object, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
    )


async def _authorize(request: Request) -> dict:
    conf = await _conf(request)
    if not conf["enabled"]:
        raise HTTPException(status_code=404, detail="Not Found")
    # Browsers send Origin; a page on another site must not reach /mcp (DNS rebinding).
    origin = request.headers.get("origin")
    if origin and urlparse(origin).netloc != request.headers.get("host"):
        raise HTTPException(status_code=403, detail="Origin not allowed")
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    ok = (
        scheme.lower() == "bearer"
        and conf["hash"]
        and hmac.compare_digest(hashlib.sha256(token.strip().encode()).hexdigest(), conf["hash"])
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid MCP token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return conf


@endpoint.post("/mcp")
async def mcp_post(request: Request):
    conf = await _authorize(request)
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(status_code=413, detail="Message too large")
    try:
        msg = json.loads(body)
    except ValueError:
        return _rpc_error(None, -32700, "Parse error")
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _rpc_error(None, -32600, "Invalid request (one JSON-RPC 2.0 object per POST)")
    method = msg.get("method")
    bridge = _bridge(request)
    try:
        if method == "initialize":
            session = await bridge.open()
            reply = await bridge.send(session, msg)
            return JSONResponse(reply, headers={"Mcp-Session-Id": session.id})
        sid = request.headers.get("mcp-session-id")
        if not sid:
            raise HTTPException(status_code=400, detail="Missing Mcp-Session-Id")
        session = bridge.get(sid)
        if session is None:
            raise HTTPException(status_code=404, detail="Unknown or expired session")
        if method == "tools/call" and (refusal := call_refusal(conf["profile"], msg.get("params"))):
            return _rpc_error(msg.get("id"), -32602, refusal)
        reply = await bridge.send(session, msg)
    except BridgeError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    if reply is None:
        return Response(status_code=202)
    if method == "tools/list" and "result" in reply:
        reply["result"] = filter_tools(conf["profile"], reply["result"])
    return JSONResponse(reply)


@endpoint.get("/mcp")
async def mcp_get(request: Request):
    await _authorize(request)
    # No server-initiated stream: linxiv-mcp sends no notifications to relay.
    return Response(status_code=405, headers={"Allow": "POST, DELETE"})


@endpoint.delete("/mcp")
async def mcp_delete(request: Request):
    await _authorize(request)
    if not await _bridge(request).close(request.headers.get("mcp-session-id") or ""):
        raise HTTPException(status_code=404, detail="Unknown or expired session")
    return Response(status_code=204)
