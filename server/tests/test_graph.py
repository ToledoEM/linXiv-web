from __future__ import annotations

import csv
import io
import zipfile

import defusedxml.ElementTree as ET

PAPERS = [
    {
        "source_fk": 2,
        "source_id": "arxiv:2",
        "title": "Two",
        "category": "cs.LG",
        "tags": ["ML", " ml", "Reading-List"],
        "has_pdf": True,
        "published": "2021-05-01",
        "authors": ["Jane Doe", "Old Name"],
        "url": None,
        "doi": "10.1/x",
        "summary": "s",
    },
    {
        "source_fk": 1,
        "source_id": "local:a",
        "title": "One",
        "category": None,
        "tags": [],
        "has_pdf": False,
        "published": "0001-01-01",
        "authors": ["Jane Doe", "Sam Twin"],
    },
]
AUTHORS = [
    {"author_id": 10, "full_name": "Jane Doe", "paper_count": 2},
    # renamed after the paper was saved: no paper names "New Name"
    {"author_id": 11, "full_name": "New Name", "paper_count": 1},
    # two records with one name
    {"author_id": 12, "full_name": "Sam Twin", "paper_count": 1},
    {"author_id": 13, "full_name": "Sam Twin", "paper_count": 0},
]
PROJECTS = [
    {
        "id": 5,
        "name": "P",
        "color_hex": None,
        "project_tags": ["b", "reading-list", "a"],
        "source_ids": ["arxiv:2"],
    },
    {"id": 6, "name": "Empty", "color_hex": "#112233", "project_tags": [], "source_ids": []},
]


def _setup(fake):
    fake.on("list", result=PAPERS)
    fake.on("author", "list", result=AUTHORS)
    fake.on("project", "list", result=PROJECTS)
    fake.on("tag", "list-all", result=["ml", "Reading-List"])
    fake.on("categories", result=["cs.LG"])
    gets = {
        "11": {"author_id": 11, "papers": [{"source_id": "arxiv:2"}]},
        "12": {"author_id": 12, "papers": [{"source_id": "local:a"}]},
    }
    fake.on("author", "get", result=lambda argv: gets[argv[-1]])


def test_graph_payload(client, fake):
    _setup(fake)
    r = client.get("/api/graph")
    assert r.status_code == 200, r.text
    v = r.json()
    assert [p["id"] for p in v["papers"]] == ["1", "2"]
    one, two = v["papers"]
    assert one["published"] is None
    assert two["tags"] == ["ml", "Reading-List"]
    assert two["tag_keys"] == ["ml", "reading-list"]
    assert two["project_ids"] == [5]
    assert sorted(two["author_keys"]) == ["jane doe", "new name"]
    assert sorted(one["author_keys"]) == ["jane doe", "sam twin"]
    edges = {(e["source"], e["target"]) for e in v["edges"]}
    assert ("2", "author::11") in edges and ("1", "author::12") in edges
    assert ("1", "author::13") not in edges
    authors = {a["author_id"]: a["paper_count"] for a in v["authors"]}
    assert authors == {10: 2, 11: 1, 12: 1}
    assert [t["id"] for t in v["tags"]] == ["tag::ml", "tag::reading-list"]
    projects = {p["id"]: p for p in v["projects"]}
    assert projects[5]["tags"] == ["a", "b"] and projects[5]["color"] == "#5b8dee"
    assert projects[5]["on_graph"] and not projects[6]["on_graph"]
    assert v["categories"] == ["cs.LG"]
    assert ["project", "list", "--status", "active"] in fake.calls
    # only the anomalous authors were looked up
    looked_up = sorted(c[-1] for c in fake.calls if c[:2] == ["author", "get"])
    assert looked_up == ["11", "12"]


def test_exclude_single_authors(client, fake):
    _setup(fake)
    v = client.get("/api/graph", params={"exclude_single_authors": "true"}).json()
    assert [a["author_id"] for a in v["authors"]] == [10]
    assert all(
        e["target"] in ("author::10",) or e["target"].startswith("tag::") for e in v["edges"]
    )


def test_empty_library(client, fake):
    for cmd in (
        ("list",),
        ("author", "list"),
        ("project", "list"),
        ("tag", "list-all"),
        ("categories",),
    ):
        fake.on(*cmd, result=[])
    v = client.get("/api/graph").json()
    assert v == {
        "papers": [],
        "authors": [],
        "tags": [],
        "edges": [],
        "categories": [],
        "projects": [],
    }


GML = "{http://graphml.graphdrawing.org/xmlns}"


def _counts(client) -> tuple[int, int]:
    v = client.get("/api/graph").json()
    return len(v["papers"]) + len(v["authors"]) + len(v["tags"]), len(v["edges"])


def test_export_graphml(client, fake):
    _setup(fake)
    nodes, edges = _counts(client)
    r = client.get("/api/graph/export", params={"format": "graphml"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/graphml+xml")
    assert 'filename="linxiv-graph-' in r.headers["content-disposition"]
    assert r.headers["content-disposition"].endswith('.graphml"')
    graph = ET.fromstring(r.content).find(f"{GML}graph")
    assert len(graph.findall(f"{GML}node")) == nodes
    assert len(graph.findall(f"{GML}edge")) == edges
    two = graph.find(f"{GML}node[@id='2']")
    data = {d.get("key"): d.text for d in two.findall(f"{GML}data")}
    assert data["n_type"] == "paper"
    assert data["n_doi"] == "10.1/x"
    assert data["n_projects"] == "P"
    assert data["n_has_pdf"] == "true"
    assert data["n_tags"] == "ml; Reading-List"


def test_export_csv(client, fake):
    _setup(fake)
    nodes, edges = _counts(client)
    r = client.get("/api/graph/export", params={"format": "csv"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"].endswith('.zip"')
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert sorted(z.namelist()) == ["edges.csv", "nodes.csv"]
        node_rows = list(csv.DictReader(io.StringIO(z.read("nodes.csv").decode())))
        edge_rows = list(csv.DictReader(io.StringIO(z.read("edges.csv").decode())))
    assert len(node_rows) == nodes and len(edge_rows) == edges
    assert {"source": "2", "target": "author::11", "type": "author"} in edge_rows
    author = next(n for n in node_rows if n["id"] == "author::10")
    assert author["type"] == "author" and author["paper_count"] == "2"


def test_export_exclude_single_authors(client, fake):
    _setup(fake)
    r = client.get("/api/graph/export", params={"format": "csv", "exclude_single_authors": "true"})
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        rows = list(csv.DictReader(io.StringIO(z.read("nodes.csv").decode())))
    assert [n["id"] for n in rows if n["type"] == "author"] == ["author::10"]


def test_export_bad_format(client, fake):
    _setup(fake)
    assert client.get("/api/graph/export", params={"format": "xml"}).status_code == 422
