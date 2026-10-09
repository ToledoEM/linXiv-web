"""App log: one rotating file in `<data>/logs/` plus stderr (`docker logs`).

Every line starts with a UTC timestamp (`2026-10-09T12:00:00.123Z`), so a time
window is a string compare. Lines without one (tracebacks) belong to the record
above them.
"""

from __future__ import annotations

import logging
import re
import sys
from collections import deque
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

FILE = "linxiv-web.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUPS = 3
LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}
WINDOWS = {
    "1h": timedelta(hours=1),
    "24h": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}
# Chatty libraries: their debug lines can carry request headers (API keys).
QUIET = ("httpx", "httpcore", "multipart", "asyncio", "python_multipart")
_STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z ")
_SECRET = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.IGNORECASE)
ARG_MAX = 200

_handlers: list[logging.Handler] = []


class _Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        t = datetime.fromtimestamp(record.created, UTC)
        return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def log_dir(data_dir: Path) -> Path:
    return data_dir / "logs"


def level_name() -> str:
    level = logging.getLogger().level
    return next((n for n, v in LEVELS.items() if v == level), "info")


def set_level(name: str) -> None:
    logging.getLogger().setLevel(LEVELS.get(name, logging.INFO))


def setup(data_dir: Path, level: str = "info") -> None:
    """Attach the file + stderr handlers to the root logger. Safe to call again
    (tests build many apps): the previous handlers are replaced."""
    root = logging.getLogger()
    for h in _handlers:
        root.removeHandler(h)
        h.close()
    _handlers.clear()
    fmt = _Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(fmt)
    _handlers.append(stream)
    try:
        folder = log_dir(data_dir)
        folder.mkdir(exist_ok=True)
        file = RotatingFileHandler(
            folder / FILE, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
        )
        file.setFormatter(fmt)
        _handlers.append(file)
    except OSError as e:
        print(f"linxiv-web: log file disabled ({e})", file=sys.stderr)
    for h in _handlers:
        root.addHandler(h)
    set_level(level)
    for name in QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)
    # uvicorn's own loggers propagate to the root handlers above.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True


def redact(args: list[str]) -> str:
    """CLI argv for a log line: secret setting values masked, long values cut."""
    out = [a if len(a) <= ARG_MAX else a[:ARG_MAX] + "…" for a in args]
    if out[:2] == ["settings", "update"]:
        for i in range(2, len(out) - 1):
            if out[i] != "--" and _SECRET.search(out[i]):
                out[i + 1] = "***"
    return " ".join(out)


def files(data_dir: Path) -> list[Path]:
    """Log files, oldest first."""
    folder = log_dir(data_dir)
    rotated = [folder / f"{FILE}.{n}" for n in range(BACKUPS, 0, -1)]
    return [p for p in (*rotated, folder / FILE) if p.is_file()]


def _cutoff(window: str) -> str | None:
    span = WINDOWS[window]
    if span is None:
        return None
    return (datetime.now(UTC) - span).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def iter_window(data_dir: Path, window: str) -> Iterator[str]:
    """Lines (with newline) of records newer than `window`, oldest first."""
    cutoff = _cutoff(window)
    keep = cutoff is None
    for path in files(data_dir):
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if _STAMP.match(line):
                    keep = cutoff is None or line[:24] >= cutoff
                if keep:
                    yield line if line.endswith("\n") else line + "\n"


def read(data_dir: Path, window: str, limit: int) -> tuple[list[str], bool]:
    """Last `limit` lines in the window, and whether older ones were left out."""
    tail: deque[str] = deque(maxlen=limit)
    total = 0
    for line in iter_window(data_dir, window):
        tail.append(line.rstrip("\n"))
        total += 1
    return list(tail), total > limit


def clear(data_dir: Path) -> None:
    """Empty the current file and delete rotated ones."""
    current = log_dir(data_dir) / FILE
    for h in _handlers:
        if isinstance(h, RotatingFileHandler) and Path(h.baseFilename) == current:
            h.acquire()
            try:
                if h.stream:
                    h.stream.seek(0)
                    h.stream.truncate()
            finally:
                h.release()
            break
    else:
        if current.is_file():
            current.write_text("")
    for n in range(1, BACKUPS + 1):
        (log_dir(data_dir) / f"{FILE}.{n}").unlink(missing_ok=True)
