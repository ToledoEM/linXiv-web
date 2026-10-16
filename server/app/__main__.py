"""`python -m app`: startup checks, then uvicorn. `python -m app hash-password` prints
an argon2 hash for LINXIV_WEB_PASSWORD_HASH. `python -m app reset-password` stores a
new admin password and logs every browser out."""

from __future__ import annotations

import getpass
import os
import sys

from . import settings as settings_mod
from .auth import stored_hash
from .netguard import parse_networks


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
    try:
        parse_networks(s.trusted_proxies)
    except ValueError as exc:
        _fail(str(exc))
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


def reset_password(s: settings_mod.Settings) -> None:
    """Set the stored admin password and log every browser out. PASSWORD env or prompt."""
    from argon2 import PasswordHasher

    from .auth import PASSWORD_MAX, PASSWORD_MIN, replace_stored_hash
    from .state_db import StateDB

    if not s.data_dir.is_dir():
        _fail(f"LINXIV_WEB_DATA_DIR={s.data_dir} does not exist or is not a directory")
    pw = os.environ.get("PASSWORD") or getpass.getpass("New password: ")
    if not PASSWORD_MIN <= len(pw) <= PASSWORD_MAX:
        _fail("password must be 8 to 256 characters")
    replace_stored_hash(s.data_dir, PasswordHasher().hash(pw))
    ended = StateDB(s.data_dir).drop_all_sessions()
    print(f"linxiv-web: password stored; {ended} session(s) logged out.")
    if s.auth_enabled:
        print(
            "linxiv-web: LINXIV_WEB_PASSWORD(_HASH) is set and wins over the stored password",
            file=sys.stderr,
        )


def main() -> None:
    if sys.argv[1:2] == ["hash-password"]:
        from argon2 import PasswordHasher

        pw = os.environ.get("PASSWORD") or getpass.getpass("Password: ")
        print(PasswordHasher().hash(pw))
        return

    if sys.argv[1:2] == ["reset-password"]:
        reset_password(settings_mod.load())
        return

    s = settings_mod.load()
    check(s)
    import uvicorn

    # Our own handlers (app/logs.py) format every line, access lines included.
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=s.host,
        port=s.port,
        proxy_headers=False,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
