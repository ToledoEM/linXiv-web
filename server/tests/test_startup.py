from __future__ import annotations

from dataclasses import replace

import pytest

from app.__main__ import check
from app.main import create_app


def test_ok_on_loopback(settings):
    check(settings)


def test_public_bind_without_password_opens_setup(settings, capsys):
    check(replace(settings, host="0.0.0.0"))
    assert "first-run setup is open" in capsys.readouterr().err


def test_public_bind_with_stored_password(settings, capsys):
    from app.auth import write_stored_hash

    write_stored_hash(settings.data_dir, "$argon2id$v=19$stored")
    check(replace(settings, host="0.0.0.0"))
    assert "setup" not in capsys.readouterr().err


def test_corrupt_auth_file_fails_closed(settings, capsys):
    from app.auth import auth_file

    auth_file(settings.data_dir).write_text("not json")
    with pytest.raises(SystemExit):
        check(replace(settings, host="0.0.0.0"))
    assert "delete it to run first-run setup again" in capsys.readouterr().err


def test_public_bind_with_password(settings):
    check(replace(settings, host="0.0.0.0", password_hash="$argon2id$x"))


def test_missing_pdf_dir(settings, tmp_path, capsys):
    with pytest.raises(SystemExit):
        check(replace(settings, pdf_dir=tmp_path / "missing"))
    assert "LINXIV_WEB_PDF_DIR" in capsys.readouterr().err


def test_pdf_dir_not_linked(settings, tmp_path, capsys):
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(SystemExit):
        check(replace(settings, pdf_dir=other))
    assert "does not point at" in capsys.readouterr().err


def test_spa_fallback_and_api_404(settings, fake, tmp_path):
    from fastapi.testclient import TestClient

    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<div id=root></div>")
    (static / "assets" / "app.js").write_text("x")
    c = TestClient(create_app(replace(settings, static_dir=static), fake))
    assert "root" in c.get("/library").text
    assert c.get("/assets/app.js").text == "x"
    assert c.get("/api/nope").status_code == 404
    assert c.get("/../../etc/passwd").status_code in (200, 404)
    assert "root:" not in c.get("/..%2F..%2Fetc%2Fpasswd").text
