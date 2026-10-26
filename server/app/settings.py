"""Environment-driven configuration. Read once at import; tests rebuild via `load()`."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class Settings:
    linxiv_bin: str
    data_dir: Path
    pdf_dir: Path
    static_dir: Path | None
    host: str
    port: int
    password_hash: str | None
    password: str | None
    secret_key: str | None
    cookie_secure: bool
    max_upload_mb: int
    timeout_long: float
    timeout_short: float
    # linXiv's stdio MCP server, bridged to /mcp when enabled in Settings.
    mcp_bin: str = "linxiv-mcp"
    # Session lifetime when "Remember me" is ticked at login.
    remember_days: int = 90
    # Start-up app log level; Settings → Logs overrides it once saved.
    log_level: str = "info"
    # Serve clients outside loopback/private LAN/link-local (app/netguard.py).
    allow_external: bool = False
    # Reverse proxies (IPs or CIDRs) whose X-Forwarded-For is believed.
    trusted_proxies: tuple[str, ...] = ()
    # Send Strict-Transport-Security (only when served over HTTPS).
    hsts: bool = False
    # Multi-user mode: where the shared and per-user libraries keep their PDFs
    # (`<dir>/<library>`); unset = inside each library's own folder.
    libraries_pdf_dir: Path | None = None

    @property
    def auth_enabled(self) -> bool:
        return bool(self.password_hash or self.password)


def load() -> Settings:
    static = os.environ.get("LINXIV_WEB_STATIC_DIR")
    lib_pdfs = os.environ.get("LINXIV_WEB_LIBRARIES_PDF_DIR")
    data_dir = Path(os.environ.get("LINXIV_WEB_DATA_DIR", "/data"))
    return Settings(
        linxiv_bin=os.environ.get("LINXIV_BIN", "linxiv"),
        data_dir=data_dir,
        pdf_dir=Path(os.environ.get("LINXIV_WEB_PDF_DIR", str(data_dir / "pdfs"))),
        static_dir=Path(static) if static else None,
        host=os.environ.get("LINXIV_WEB_HOST", "127.0.0.1"),
        port=int(os.environ.get("LINXIV_WEB_PORT", "8000")),
        password_hash=os.environ.get("LINXIV_WEB_PASSWORD_HASH") or None,
        password=os.environ.get("LINXIV_WEB_PASSWORD") or None,
        secret_key=os.environ.get("LINXIV_WEB_SECRET_KEY") or None,
        cookie_secure=_bool("LINXIV_WEB_COOKIE_SECURE"),
        max_upload_mb=int(os.environ.get("LINXIV_WEB_MAX_UPLOAD_MB", "200")),
        timeout_long=float(os.environ.get("LINXIV_WEB_TIMEOUT_LONG", "120")),
        timeout_short=float(os.environ.get("LINXIV_WEB_TIMEOUT_SHORT", "30")),
        mcp_bin=os.environ.get("LINXIV_MCP_BIN", "linxiv-mcp"),
        remember_days=max(1, int(os.environ.get("LINXIV_WEB_REMEMBER_DAYS", "90"))),
        log_level=os.environ.get("LINXIV_WEB_LOG_LEVEL", "info").strip().lower() or "info",
        allow_external=_bool("LINXIV_WEB_ALLOW_EXTERNAL"),
        hsts=_bool("LINXIV_WEB_HSTS"),
        libraries_pdf_dir=Path(lib_pdfs) if lib_pdfs else None,
        trusted_proxies=tuple(
            p.strip()
            for p in os.environ.get("LINXIV_WEB_TRUSTED_PROXIES", "").split(",")
            if p.strip()
        ),
    )
