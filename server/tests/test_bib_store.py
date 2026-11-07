from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app import bib_store


@dataclass
class Lib:
    data_dir: Path


def _run(coro):
    return asyncio.run(coro)


def test_no_row_is_all_null(tmp_path):
    lib = Lib(tmp_path)
    got = _run(bib_store.get(lib, "doi:10.1/x"))
    assert got == {"bib": {}, "metadata_source": None, "metadata_fetched_at": None}
    assert not (tmp_path / bib_store.FILE).exists()  # reading creates nothing


def test_clean_keeps_known_fields_and_normalizes():
    got = bib_store.clean(
        {
            "volume": " 12 ",
            "month": "05",
            "entry_type": "InProceedings",
            "note": "  two\n lines ",
            "pages": "",
            "unknown": "x",
            "issn": None,
        }
    )
    assert got == {
        "volume": "12",
        "month": "may",
        "entry_type": "inproceedings",
        "note": "two lines",
    }
    assert bib_store.clean({"entry_type": "webpage", "month": "13"}) == {}
    assert bib_store.month("September") == "sep"
    assert bib_store.month(None) is None


def test_upsert_overwrite_and_fill_only(tmp_path):
    lib = Lib(tmp_path)
    _run(bib_store.upsert(lib, "a", {"volume": "1", "pages": "1--2"}, "crossref", "doi:10.1/a"))
    got = _run(bib_store.get(lib, "a"))
    assert got["bib"] == {"volume": "1", "pages": "1--2"}
    assert got["metadata_source"] == {"source": "crossref", "ref": "doi:10.1/a"}
    assert got["metadata_fetched_at"]
    # fill-only: stored values and source stay, null ones fill
    _run(bib_store.upsert(lib, "a", {"volume": "9", "number": "3"}, "pubmed", "x", False))
    got = _run(bib_store.get(lib, "a"))
    assert got["bib"] == {"volume": "1", "number": "3", "pages": "1--2"}
    assert got["metadata_source"]["source"] == "crossref"
    # overwrite
    _run(bib_store.upsert(lib, "a", {"volume": "9"}, "pubmed", "pubmed:1"))
    got = _run(bib_store.get(lib, "a"))
    assert got["bib"]["volume"] == "9"
    assert got["metadata_source"] == {"source": "pubmed", "ref": "pubmed:1"}
    # unknown source and no fields: nothing written
    _run(bib_store.upsert(lib, "b", {}, "nowhere"))
    assert _run(bib_store.get_many(lib, ["a", "b"])).keys() == {"a"}
    # clear
    _run(bib_store.clear(lib, "a", ["volume", "metadata_source", "nope"]))
    got = _run(bib_store.get(lib, "a"))
    assert "volume" not in got["bib"]
    assert got["metadata_source"]["source"] == "pubmed"


def test_move_delete_prune_all(tmp_path):
    lib = Lib(tmp_path)
    _run(bib_store.upsert(lib, "win", {"volume": "1"}))
    _run(bib_store.upsert(lib, "lose", {"volume": "2", "pages": "5"}, "crossref", "doi:x"))
    _run(bib_store.move(lib, "lose", "win"))
    rows = _run(bib_store.all_rows(lib))
    assert set(rows) == {"win"}
    assert rows["win"]["bib"] == {"volume": "1", "pages": "5"}
    assert rows["win"]["metadata_source"] == {"source": "crossref", "ref": "doi:x"}
    _run(bib_store.move(lib, "gone", "win"))  # no loser row: nothing changes
    _run(bib_store.upsert(lib, "other", {"volume": "3"}))
    assert _run(bib_store.prune(lib, {"win"})) == 1
    assert _run(bib_store.delete(lib, ["win", "missing"])) == 1
    assert _run(bib_store.all_rows(lib)) == {}


def test_backup_copies_rows(tmp_path):
    lib = Lib(tmp_path / "lib")
    lib.data_dir.mkdir()
    target = tmp_path / "copy.db"
    assert _run(bib_store.backup_to(lib, target)) is False
    _run(bib_store.upsert(lib, "a", {"volume": "1"}))
    assert _run(bib_store.backup_to(lib, target)) is True
    rows = sqlite3.connect(target).execute("SELECT source_id, volume FROM paper_bib").fetchall()
    assert rows == [("a", "1")]


def test_libraries_are_separate(tmp_path):
    a, b = Lib(tmp_path / "a"), Lib(tmp_path / "b")
    a.data_dir.mkdir()
    b.data_dir.mkdir()
    _run(bib_store.upsert(a, "x", {"volume": "1"}))
    assert _run(bib_store.get(b, "x"))["bib"] == {}
