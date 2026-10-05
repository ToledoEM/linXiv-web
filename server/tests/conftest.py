from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.cli import CLIError
from app.main import create_app
from app.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


class FakeCLI:
    """Records argv and answers from a {command-prefix: response} table.

    A response may be a value, a callable taking argv, or a CLIError to raise.
    The longest matching prefix wins.
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.responses: dict[tuple[str, ...], Any] = {}

    def on(self, *prefix: str, result: Any) -> None:
        self.responses[prefix] = result

    async def __call__(self, args: list[str], timeout: float, raw: bool = False) -> Any:
        self.calls.append(args)
        for n in range(len(args), 0, -1):
            key = tuple(args[:n])
            if key in self.responses:
                result = self.responses[key]
                if isinstance(result, CLIError):
                    raise result
                return result(args) if callable(result) else result
        raise CLIError(502, f"unexpected call {args}")


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    pdfs = tmp_path / "pdfs"
    data.mkdir()
    pdfs.mkdir()
    (data / "pdfs").symlink_to(pdfs)
    return data, pdfs


@pytest.fixture
def settings(dirs) -> Settings:
    data, pdfs = dirs
    return Settings(
        linxiv_bin="linxiv",
        data_dir=data,
        pdf_dir=pdfs,
        static_dir=None,
        host="127.0.0.1",
        port=8000,
        password_hash=None,
        password=None,
        secret_key="test-secret",
        cookie_secure=False,
        max_upload_mb=1,
        timeout_long=120,
        timeout_short=30,
    )


@pytest.fixture
def fake() -> FakeCLI:
    return FakeCLI()


@pytest.fixture
def client(settings, fake) -> TestClient:
    return TestClient(create_app(settings, fake))


@pytest.fixture
def auth_client(settings, fake) -> TestClient:
    return TestClient(create_app(replace(settings, password="hunter2"), fake))
