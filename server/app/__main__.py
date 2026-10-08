"""`python -m app`: startup checks, then uvicorn. `python -m app hash-password` prints
an argon2 hash for LINXIV_WEB_PASSWORD_HASH."""

from __future__ import annotations

import getpass
import os
import sys

from . import settings as settings_mod
from .auth import stored_hash


def _fail(msg: str) -> None:
    print(f"linxiv-web: {msg}", file=sys.stderr)
    sys.exit(1)


def check(s: settings_mod.Settings) -> None:
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
    if s.auth_enabled:
        return
    try:
        stored = stored_hash(s.data_dir)
    except ValueError as exc:
        _fail(f"{exc}; delete it to run first-run setup again")
    if stored is None and not settings_mod.is_loopback(s.host):
        print(
            f"linxiv-web: no password set; first-run setup is open on {s.host}:{s.port}. "
            "The first visitor creates the admin password.",
            file=sys.stderr,
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
