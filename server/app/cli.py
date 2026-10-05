"""The only door to linXiv: run `linxiv <args>` as a subprocess and parse its JSON.

The library is single-writer, so every call goes through one process-wide lock.
No shell: args are passed as a list, and user-supplied positionals always follow
a `--` so a value like `--help` or `-x` can never be read as a flag.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Protocol


class CLIError(Exception):
    """A linxiv call failed. `status` is the HTTP status the API should answer with."""

    def __init__(self, status: int, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.stderr = stderr


def _error_message(stderr: str) -> str:
    """linxiv prints `{"error": "..."}` as the last stderr line on failure."""
    for line in reversed(stderr.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                body = json.loads(line)
            except ValueError:
                continue
            if isinstance(body, dict) and "error" in body:
                return str(body["error"])
    return stderr.strip()[-500:] or "linxiv failed with no output"


def _status_for(message: str) -> int:
    low = message.lower()
    if "not found" in low or "no paper" in low or "no version" in low:
        return 404
    if low.startswith("invalid") or "invalid " in low:
        return 400
    return 502


class Runner(Protocol):
    async def __call__(self, args: list[str], timeout: float, raw: bool = False) -> Any: ...


class LinxivCLI:
    def __init__(self, binary: str, env: dict[str, str] | None = None) -> None:
        self.binary = binary
        self.env = env
        self._lock = asyncio.Lock()

    async def __call__(self, args: list[str], timeout: float, raw: bool = False) -> Any:
        """Run one command. `raw=True` returns stdout text (e.g. `fetch` prints
        Markdown for arXiv papers); otherwise stdout is parsed as JSON."""
        async with self._lock:
            return await self._run(args, timeout, raw)

    async def _run(self, args: list[str], timeout: float, raw: bool) -> Any:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary,
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **(self.env or {})},
            )
        except FileNotFoundError as e:
            raise CLIError(500, f"linxiv binary not found: {self.binary}") from e
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise CLIError(504, f"linxiv {args[0]} timed out after {timeout:g}s") from None

        err = stderr.decode("utf-8", "replace")
        if proc.returncode != 0:
            msg = _error_message(err)
            raise CLIError(_status_for(msg), msg, err)
        out = stdout.decode("utf-8", "replace").strip()
        if raw:
            return out
        if not out:
            return None
        try:
            return json.loads(out)
        except ValueError:
            raise CLIError(502, f"linxiv {args[0]} printed non-JSON output", err) from None
