from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app import tag_store
from app.routes.tag_vocab import parse_csv
from app.tag_norm import norm_key


@dataclass
class Lib:
    data_dir: Path


def _upload(client, text: str, replace: bool = False):
    url = "/api/tags/vocabulary/import" + ("?replace=true" if replace else "")
    return client.post(url, files={"file": ("tags.csv", text.encode())})


def test_parse_plain_layout():
    tags, aliases, errors, layout, siblings = parse_csv(
        "Tag,Aliases,Weight\n"
        "RNA-seq,RNA sequencing|RNAseq|bulk RNA-seq,40\n"
        "organoid,,\n"
        ",x,1\n"
        "reading-list,,\n"
        "autophagy,,lots\n"
        "Organoids,3D culture,7\n"
    )
    assert layout == "tags" and siblings == 0
    assert tags == {"rnaseq": ("RNA-seq", 40.0), "organoid": ("Organoids", 7.0)}
    # Same-key spellings are not aliases; the rest are.
    assert aliases == {
        norm_key("bulk RNA-seq"): ("bulk RNA-seq", "RNA-seq"),
        norm_key("3D culture"): ("3D culture", "Organoids"),
    }
    assert errors == [
        "line 4: empty or invalid tag",
        "line 5: reserved tag",
        "line 6: weight is not a number from 0",
    ]


def test_parse_tag_map_layout():
    tags, aliases, errors, layout, siblings = parse_csv(
        "old_tag,new_tag,cluster,papers\n"
        "wnt pathway,wnt signaling,4,3\n"
        "wnt signalling,wnt signaling,4,2\n"
        "wnt signaling,wnt signaling,4,10\n"
        "IL-6,IL-6,9,5\n"
        "STAT5,stat3,7,2\n"
        "stat3,stat3,7,9\n"
    )
    assert layout == "tag_map"
    assert tags == {
        "wntsignaling": ("wnt signaling", 15.0),
        "il6": ("IL-6", 5.0),
        "stat3": ("stat3", 11.0),
    }
    # STAT5 is a sibling of stat3, not another name for it.
    assert aliases == {"wntpathway": ("wnt pathway", "wnt signaling")}
    assert errors == [] and siblings == 1


def test_import_export_and_replace(client, fake):
    r = _upload(client, "tag,aliases,weight\nRNA-seq,RNA sequencing|bulk RNA-seq,40\nOrganoid,,\n")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "tags": 2,
        "aliases": 1,
        "layout": "tags",
        "replaced": False,
        "skipped_siblings": 0,
        "errors": [],
    }
    got = client.get("/api/tags/vocabulary").json()
    assert [(v["tag"], v["weight"]) for v in got["vocab"]] == [("Organoid", None), ("RNA-seq", 40)]
    assert [(a["alias"], a["canonical"], a["origin"]) for a in got["aliases"]] == [
        ("bulk RNA-seq", "RNA-seq", "csv")
    ]
    assert got["pending"] == 0

    csv_text = client.get("/api/tags/vocabulary/export.csv").text
    assert csv_text == "tag,aliases,weight\nOrganoid,,\nRNA-seq,bulk RNA-seq,40\n"

    client.post("/api/tags/vocabulary/aliases", json={"alias": "DL", "canonical": "deep learning"})
    r = _upload(client, "tag\nautophagy\n", replace=True)
    assert r.json()["replaced"] is True
    got = client.get("/api/tags/vocabulary").json()
    assert [v["tag"] for v in got["vocab"]] == ["autophagy"]
    # CSV aliases go with a replace; hand-made ones stay.
    assert [a["alias"] for a in got["aliases"]] == ["DL"]
    assert "deep learning,DL," in client.get("/api/tags/vocabulary/export.csv").text


def test_import_rejects_bad_files(client, fake):
    assert _upload(client, "name,count\nx,1\n").status_code == 400
    assert _upload(client, "tag\n,\n").status_code == 400
    r = client.post("/api/tags/vocabulary/import", files={"file": ("t.csv", b"\xff\xfe")})
    assert r.status_code == 400


def test_aliases(client, fake):
    r = client.post("/api/tags/vocabulary/aliases", json={"alias": "AD", "canonical": "Alzheimer"})
    assert r.status_code == 200 and r.json()["alias_key"] == "ad"
    bad = [
        {"alias": "RNA seq", "canonical": "RNA-seq"},
        {"alias": "!!", "canonical": "x"},
        {"alias": "rl", "canonical": "reading-list"},
    ]
    for body in bad:
        assert client.post("/api/tags/vocabulary/aliases", json=body).status_code == 400
    assert client.delete("/api/tags/vocabulary/aliases/ad").status_code == 200
    assert client.delete("/api/tags/vocabulary/aliases/ad").status_code == 404


def test_pending_queue(client, fake, settings):
    lib = Lib(settings.data_dir)
    n = asyncio.run(
        tag_store.propose(
            lib, [("AD", "Alzheimer's disease"), ("PD", "Parkinson's disease")], "p1", "m"
        )
    )
    assert n == 2
    assert [p["alias"] for p in client.get("/api/tags/vocabulary/pending").json()] == ["AD", "PD"]
    assert client.post("/api/tags/vocabulary/pending/ad/approve").json() == {
        "alias_key": "ad",
        "approved": True,
    }
    assert client.post("/api/tags/vocabulary/pending/pd/reject").status_code == 200
    assert client.post("/api/tags/vocabulary/pending/pd/reject").status_code == 404
    assert client.get("/api/tags/vocabulary/pending").json() == []
    got = client.get("/api/tags/vocabulary").json()["aliases"]
    assert [(a["alias"], a["origin"]) for a in got] == [("AD", "llm")]
    # Neither an approved nor a rejected alias is proposed again.
    again = [("AD", "x"), ("PD", "Parkinson's disease")]
    assert asyncio.run(tag_store.propose(lib, again, "p2", "m")) == 0


def test_alias_resolves_on_the_next_suggestion(settings):
    lib = Lib(settings.data_dir)
    asyncio.run(tag_store.add_alias(lib, "neural nets", "neural network"))
    assert asyncio.run(tag_store.alias_map(lib)) == {"neuralnet": "neural network"}


def test_backup(tmp_path):
    lib = Lib(tmp_path)
    target = tmp_path / "tags-copy.db"
    assert asyncio.run(tag_store.backup_to(lib, target)) is False
    asyncio.run(tag_store.add_alias(lib, "AD", "Alzheimer"))
    assert asyncio.run(tag_store.backup_to(lib, target)) is True
    rows = sqlite3.connect(target).execute("SELECT alias, canonical FROM alias").fetchall()
    assert rows == [("AD", "Alzheimer")]
