from __future__ import annotations

import asyncio
import stat
import time
from pathlib import Path

import pytest

from app.cli import CLIError, LinxivCLI


def make_bin(tmp_path: Path, body: str) -> str:
    path = tmp_path / "linxiv"
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def test_parses_json_and_passes_args_verbatim(tmp_path):
    cli = LinxivCLI(make_bin(tmp_path, 'printf \'{"argv": "%s|%s|%s"}\' "$1" "$2" "$3"\n'))
    out = asyncio.run(cli(["paper", "--", "-x; rm"], 5))
    assert out == {"argv": "paper|--|-x; rm"}


def test_raw_returns_text(tmp_path):
    cli = LinxivCLI(make_bin(tmp_path, "echo '# Title'\n"))
    assert asyncio.run(cli(["fetch"], 5, raw=True)) == "# Title"


@pytest.mark.parametrize(
    "msg,status",
    [("Paper 9999.99999 not found", 404), ("Invalid arXiv ID format: x", 400), ("boom", 502)],
)
def test_error_json_maps_status(tmp_path, msg, status):
    cli = LinxivCLI(
        make_bin(tmp_path, f"echo '[x] detail' >&2\necho '{{\"error\": \"{msg}\"}}' >&2\nexit 1\n")
    )
    with pytest.raises(CLIError) as e:
        asyncio.run(cli(["paper", "get"], 5))
    assert e.value.status == status
    assert e.value.message == msg


def test_non_json_is_502(tmp_path):
    cli = LinxivCLI(make_bin(tmp_path, "echo nope\n"))
    with pytest.raises(CLIError) as e:
        asyncio.run(cli(["stats"], 5))
    assert e.value.status == 502


def test_timeout_is_504(tmp_path):
    cli = LinxivCLI(make_bin(tmp_path, "sleep 5\n"))
    with pytest.raises(CLIError) as e:
        asyncio.run(cli(["search"], 0.2))
    assert e.value.status == 504


def test_missing_binary_is_500(tmp_path):
    with pytest.raises(CLIError) as e:
        asyncio.run(LinxivCLI(str(tmp_path / "nope"))(["stats"], 5))
    assert e.value.status == 500


def test_calls_are_serialized(tmp_path):
    # Each call appends start/end markers; with the lock they never interleave.
    log = tmp_path / "log"
    cli = LinxivCLI(
        make_bin(tmp_path, f"echo s >> {log}\nsleep 0.2\necho e >> {log}\necho '{{}}'\n")
    )

    async def many():
        await asyncio.gather(*(cli(["stats"], 5) for _ in range(4)))

    t0 = time.monotonic()
    asyncio.run(many())
    assert time.monotonic() - t0 >= 0.8
    assert log.read_text().split() == ["s", "e"] * 4
