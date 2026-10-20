from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from . import logs
from . import settings as settings_mod
from .activity import ActivityLog
from .auth import Auth, require_auth
from .cli import CLIError, LinxivCLI, Runner
from .fulltext_worker import FullTextWorker
from .jobs import Jobs
from .mcp_bridge import McpBridge
from .netguard import ClientGuard, parse_networks
from .routes import activity as activity_routes
from .routes import (
    add,
    ai,
    annotations,
    authors,
    backup,
    exports,
    feed,
    graph,
    imports,
    library,
    mcp,
    metadata,
    notes,
    pdfs,
    projects,
    sources,
    system,
    trash,
    user_settings,
    versions,
)
from .routes import auth as auth_routes
from .routes import logs as log_routes
from .update_check import UpdateChecker

__version__ = "0.1.2"
log = logging.getLogger("app")
access_log = logging.getLogger("app.access")
# Polled or static: not worth a line each.
ACCESS_SKIP = ("/api/health", "/assets/")
# Read-only job polling (activity tray, Settings cards); starting/cancelling is logged.
ACCESS_SKIP_GET = ("/api/jobs",)


class SecurityHeaders(BaseHTTPMiddleware):
    def __init__(self, app, *, hsts: bool = False):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        # The app needs none of these browser features.
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        if self.hsts:
            # Only when served over HTTPS (LINXIV_WEB_HSTS): browsers then refuse plain HTTP.
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        # The PDF viewer embeds /api/papers/*/pdf in a same-origin <iframe>.
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'wasm-unsafe-eval'; frame-src 'self'; object-src 'self'; frame-ancestors 'self'",
        )
        return response


class AccessLog(BaseHTTPMiddleware):
    """One line per request: method, path (no query string), status, time."""

    async def dispatch(self, request, call_next):
        path = request.url.path
        if path.startswith(ACCESS_SKIP) or (
            request.method == "GET" and path.startswith(ACCESS_SKIP_GET)
        ):
            return await call_next(request)
        start = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            ms = (time.monotonic() - start) * 1000
            level = logging.WARNING if status >= 500 else logging.INFO
            access_log.log(level, "%s %s %d %.0f ms", request.method, path, status, ms)


async def _stored_log_level(cli, timeout: float) -> None:
    """Apply the level saved in Settings → Logs (it wins over LINXIV_WEB_LOG_LEVEL)."""
    try:
        stored = await cli(["settings", "get"], timeout)
    except CLIError:
        return
    level = stored.get("web_log_level") if isinstance(stored, dict) else None
    if level in logs.LEVELS:
        logs.set_level(level)


def create_app(
    settings: settings_mod.Settings | None = None, runner: Runner | None = None
) -> FastAPI:
    settings = settings or settings_mod.load()
    logs.setup(settings.data_dir, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # The background indexer runs against the real CLI only; tests drive
        # FullTextWorker.step() directly.
        task = update_task = None
        if runner is None:
            await _stored_log_level(app.state.cli, settings.timeout_short)
            task = asyncio.create_task(app.state.fulltext_worker.run())
            update_task = asyncio.create_task(app.state.update_checker.run())
        log.info("linxiv-web %s started (log level %s)", __version__, logs.level_name())
        try:
            yield
        finally:
            for t in (task, update_task):
                if t:
                    t.cancel()
            await app.state.mcp.close_all()
            log.info("linxiv-web stopped")

    app = FastAPI(
        title="linXiv-web", version=__version__, docs_url=None, redoc_url=None, lifespan=lifespan
    )
    app.state.settings = settings
    app.state.auth = Auth(settings)
    app.state.jobs = Jobs()
    app.state.cli = runner or LinxivCLI(
        settings.linxiv_bin, env={"LINXIV_DATA_DIR": str(settings.data_dir)}
    )
    app.state.fulltext_worker = FullTextWorker(
        app.state.cli, app.state.jobs, settings.timeout_short, settings.timeout_long
    )
    app.state.update_checker = UpdateChecker(app.state.cli, __version__, settings.timeout_short)
    app.state.mcp = McpBridge(
        [settings.mcp_bin], {"LINXIV_DATA_DIR": str(settings.data_dir)}, settings.timeout_long * 2
    )
    app.state.mcp_conf = None
    app.add_middleware(SecurityHeaders, hsts=settings.hsts)
    app.add_middleware(ActivityLog, data_dir=settings.data_dir)
    app.add_middleware(AccessLog)
    # Outermost: refused public clients never reach the access log (a scanner
    # could fill it); ClientGuard logs them itself, rate-limited.
    app.add_middleware(
        ClientGuard,
        allow_external=settings.allow_external,
        trusted_proxies=parse_networks(settings.trusted_proxies),
    )

    @app.exception_handler(CLIError)
    async def _cli_error(_: Request, exc: CLIError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        # Upstream failures (Crossref, PubMed, bioRxiv, AI, feeds, PDF links) end up
        # here as 5xx; their details are already free of keys.
        if exc.status_code >= 500:
            log.warning("%s %s: %s", request.method, request.url.path, exc.detail)
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        # The traceback reaches the app log through uvicorn; the client gets JSON
        # (api.ts reads `detail`) and no internals.
        return JSONResponse({"detail": "internal server error"}, status_code=500)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "version": __version__}

    app.include_router(auth_routes.router)
    # /mcp has its own bearer-token auth (MCP clients have no browser session).
    app.include_router(mcp.endpoint)
    app.include_router(mcp.router, dependencies=[Depends(require_auth)])
    guarded = [Depends(require_auth)]
    # pdfs first: its /papers/{id:path}/pdf routes must win over library's bare
    # /papers/{id:path}.
    app.include_router(pdfs.router, dependencies=guarded)
    app.include_router(user_settings.router, dependencies=guarded)
    app.include_router(ai.router, dependencies=guarded)
    app.include_router(add.router, dependencies=guarded)
    app.include_router(trash.router, dependencies=guarded)
    app.include_router(imports.router, dependencies=guarded)
    app.include_router(exports.router, dependencies=guarded)
    app.include_router(system.router, dependencies=guarded)
    app.include_router(authors.router, dependencies=guarded)
    app.include_router(feed.router, dependencies=guarded)
    app.include_router(backup.router, dependencies=guarded)
    app.include_router(annotations.router, dependencies=guarded)
    app.include_router(graph.router, dependencies=guarded)
    app.include_router(projects.router, dependencies=guarded)
    app.include_router(notes.router, dependencies=guarded)
    app.include_router(versions.router, dependencies=guarded)
    app.include_router(sources.router, dependencies=guarded)
    app.include_router(log_routes.router, dependencies=guarded)
    app.include_router(activity_routes.router, dependencies=guarded)
    # Before library: its GET /papers/{id:path} would swallow .../lookup.
    app.include_router(metadata.router, dependencies=guarded)
    app.include_router(library.router, dependencies=guarded)

    if settings.static_dir and (settings.static_dir / "index.html").is_file():
        _mount_spa(app, settings.static_dir)
    return app


def _mount_spa(app: FastAPI, static_dir: Path) -> None:
    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    index = static_dir / "index.html"
    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)
