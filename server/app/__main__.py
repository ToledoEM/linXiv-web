"""`python -m app`: startup checks, then uvicorn. `python -m app hash-password` prints
an argon2 hash for LINXIV_WEB_PASSWORD_HASH."""

from __future__ import annotations

import getpass
import os
import sys

from . import settings as settings_mod


def _fail(msg: str) -> None:
    print(f"linxiv-web: {msg}", file=sys.stderr)
    sys.exit(1)


def check(s: settings_mod.Settings) -> None:
    """Fail closed, mirroring linxiv-headless: no password, no non-loopback bind."""
    if not settings_mod.is_loopback(s.host) and not s.auth_enabled:
        _fail(
            f"refusing to bind {s.host} without a password: set LINXIV_WEB_PASSWORD_HASH "
            "(python -m app hash-password) or bind 127.0.0.1"
        )
    for name, path in (("LINXIV_WEB_DATA_DIR", s.data_dir), ("LINXIV_WEB_PDF_DIR", s.pdf_dir)):
        if not path.is_dir():
            _fail(f"{name}={path} does not exist or is not a directory")
        if not os.access(path, os.W_OK):
            _fail(f"{name}={path} is not writable")
    managed = s.data_dir / "pdfs"
    if managed.resolve() != s.pdf_dir.resolve():
        _fail(
            f"linxiv stores PDFs in {managed}, which does not point at "
            f"LINXIV_WEB_PDF_DIR={s.pdf_dir} (entrypoint.sh links them)"
        )


def main() -> None:
    if sys.argv[1:2] == ["hash-password"]:
        from argon2 import PasswordHasher

        pw = os.environ.get("PASSWORD") or getpass.getpass("Password: ")
        print(PasswordHasher().hash(pw))
        return

    s = settings_mod.load()
    check(s)
    import uvicorn

    uvicorn.run("app.main:create_app", factory=True, host=s.host, port=s.port, proxy_headers=False)


if __name__ == "__main__":
    main()
