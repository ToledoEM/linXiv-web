from __future__ import annotations

from pathlib import Path

import pytest

BIB = b"@article{a, title={A}, author={Doe, Jane}, year={2020}}\n"
CSL = b'[{"id": "x", "type": "article-journal", "title": "X"}]'


@pytest.mark.parametrize(
    ("kind", "name", "body", "suffix"),
    [("bibtex", "refs.bib", BIB, ".bib"), ("zotero", "lib.json", CSL, ".json")],
)
def test_import_passes_temp_file_and_cleans_up(client, fake, kind, name, body, suffix):
    seen = {}

    def imp(argv):
        seen["path"] = Path(argv[-1])
        seen["body"] = seen["path"].read_bytes()
        return {"saved_count": 1, "source_ids": ["local:a"]}

    fake.on(kind, "import", result=imp)
    r = client.post(f"/api/import/{kind}", files={"file": (name, body)})
    assert r.status_code == 200, r.text
    assert r.json() == {"saved_count": 1, "source_ids": ["local:a"]}
    assert fake.calls[-1][:3] == [kind, "import", "--"]
    assert seen["body"] == body
    assert seen["path"].suffix == suffix
    assert not seen["path"].exists()


@pytest.mark.parametrize(
    ("kind", "body", "status"),
    [
        ("bibtex", b"", 400),
        ("bibtex", b"just some words", 400),
        ("bibtex", b"@misc{x,\xff\xfe}", 400),
        ("zotero", b"{not json", 400),
        ("zotero", b'{"items": []}', 400),
        ("bibtex", b"@" + b"x" * (2 << 20), 413),
    ],
)
def test_import_rejects_bad_files(client, fake, kind, body, status):
    r = client.post(f"/api/import/{kind}", files={"file": ("f", body)})
    assert r.status_code == status, r.text
    assert not fake.calls


def test_import_unknown_kind_is_404(client):
    assert client.post("/api/import/endnote", files={"file": ("f", BIB)}).status_code == 404
