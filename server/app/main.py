from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from . import settings as settings_mod
from .auth import Auth, require_auth
from .cli import CLIError, LinxivCLI, Runner
from .routes import add, authors, imports, library, notes, pdfs, projects, trash, user_settings
from .routes import auth as auth_routes

__version__ = "0.1.0"


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        # The PDF viewer embeds /api/papers/*/pdf in a same-origin <iframe>.
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; frame-src 'self'; object-src 'self'; frame-ancestors 'self'",
        )
        return response


def create_app(
    settings: settings_mod.Settings | None = None, runner: Runner | None = None
) -> FastAPI:
    settings = settings or settings_mod.load()
    app = FastAPI(title="linXiv-web", version=__version__, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.auth = Auth(settings)
    app.state.cli = runner or LinxivCLI(
        settings.linxiv_bin, env={"LINXIV_DATA_DIR": str(settings.data_dir)}
    )
    app.add_middleware(SecurityHeaders)

    @app.exception_handler(CLIError)
    async def _cli_error(_: Request, exc: CLIError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "version": __version__}

    app.include_router(auth_routes.router)
    guarded = [Depends(require_auth)]
    # pdfs first: its /papers/{id:path}/pdf routes must win over library's bare
    # /papers/{id:path}.
    app.include_router(pdfs.router, dependencies=guarded)
    app.include_router(user_settings.router, dependencies=guarded)
    app.include_router(add.router, dependencies=guarded)
    app.include_router(trash.router, dependencies=guarded)
    app.include_router(imports.router, dependencies=guarded)
    app.include_router(authors.router, dependencies=guarded)
    app.include_router(projects.router, dependencies=guarded)
    app.include_router(notes.router, dependencies=guarded)
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
