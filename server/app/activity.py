"""Activity log: who changed what, when. `<data>/logs/activity.jsonl`, one JSON object
per line, newest last.

Every state-changing API request (POST/PUT/PATCH/DELETE under /api/) is recorded
with its route template, path parameters, status and the client address. Request
bodies and values are never written; a Settings save records only the key names
(`note_fields`). Writing never raises: a full disk or read-only volume means no
record, not a failed request. The file rotates at MAX_BYTES, keeping one old copy.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import threading
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware

from .logs import log_dir

FILE = "activity.jsonl"
MAX_BYTES = 5 * 1024 * 1024
CLEAR_PHRASE = "delete activity log"
_UNSAFE = ("POST", "PUT", "PATCH", "DELETE")
CSV_FIELDS = ("at", "client", "method", "route", "target", "status", "fields")

log = logging.getLogger(__name__)
_lock = threading.Lock()


def path(data_dir: Path) -> Path:
    return log_dir(data_dir) / FILE


def _now() -> str:
    t = datetime.now(UTC)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def record(data_dir: Path, event: dict[str, Any]) -> None:
    """Append one event. Never raises."""
    try:
        line = (json.dumps({"at": _now(), **event}, separators=(",", ":")) + "\n").encode()
        p = path(data_dir)
        with _lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists() and p.stat().st_size + len(line) > MAX_BYTES:
                os.replace(p, p.with_name(FILE + ".1"))
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, line)
            finally:
                os.close(fd)
    except Exception:  # the activity log must never break a request
        log.warning("activity log write failed", exc_info=True)


def read(data_dir: Path, limit: int) -> list[dict]:
    """Newest first, at most `limit` events (current file, then the rotated one)."""
    out: deque[dict] = deque(maxlen=limit)
    for p in (path(data_dir).with_name(FILE + ".1"), path(data_dir)):
        try:
            with p.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            continue
    return list(reversed(out))


def to_csv(events: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    w.writeheader()
    for e in events:
        row = dict(e)
        row["target"] = json.dumps(e.get("target") or {}, separators=(",", ":"))
        row["fields"] = " ".join(e.get("fields") or [])
        w.writerow(row)
    return buf.getvalue()


def clear(data_dir: Path) -> None:
    with _lock:
        for p in (path(data_dir), path(data_dir).with_name(FILE + ".1")):
            p.unlink(missing_ok=True)


def note_fields(request, names) -> None:
    """Called by a handler: record these field names (never values) with the request."""
    request.state.activity_fields = sorted(names)


class ActivityLog(BaseHTTPMiddleware):
    def __init__(self, app, *, data_dir: Path):
        super().__init__(app)
        self.data_dir = data_dir

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        p = request.url.path
        if request.method in _UNSAFE and p.startswith("/api/"):
            route = request.scope.get("route")
            event = {
                "client": getattr(request.state, "client_ip", None) or "unknown",
                "method": request.method,
                "route": getattr(route, "path", p),
                "target": dict(request.scope.get("path_params") or {}),
                "status": response.status_code,
            }
            fields = getattr(request.state, "activity_fields", None)
            if fields:
                event["fields"] = fields
            record(self.data_dir, event)
        return response
