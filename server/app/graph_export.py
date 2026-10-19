"""Knowledge Graph as files (`GET /api/graph/export`): GraphML, or CSV nodes + edges in a zip.

Both take the `/api/graph` payload. Every node gets `id`, `type` (paper, author or
tag) and `label`; list values (a paper's tags and projects) are joined with "; ".
"""

from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET  # noqa: S405 - builds XML, never parses it
import zipfile

SEP = "; "

# (column, GraphML attr.type), in CSV column order.
NODE_FIELDS = [
    ("id", "string"),
    ("type", "string"),
    ("label", "string"),
    ("source_id", "string"),
    ("category", "string"),
    ("published", "string"),
    ("has_pdf", "boolean"),
    ("doi", "string"),
    ("url", "string"),
    ("summary", "string"),
    ("tags", "string"),
    ("projects", "string"),
    ("author_id", "int"),
    ("key", "string"),
    ("paper_count", "int"),
]
EDGE_FIELDS = [("source", "string"), ("target", "string"), ("type", "string")]


def node_rows(view: dict) -> list[dict]:
    project_names = {p["id"]: p["name"] for p in view.get("projects") or []}
    rows: list[dict] = []
    for p in view.get("papers") or []:
        rows.append(
            {
                "id": p["id"],
                "type": "paper",
                "label": p.get("label") or "",
                "source_id": p.get("source_id"),
                "category": p.get("category"),
                "published": p.get("published"),
                "has_pdf": bool(p.get("has_pdf")),
                "doi": p.get("doi"),
                "url": p.get("url"),
                "summary": p.get("summary"),
                "tags": SEP.join(p.get("tags") or []),
                "projects": SEP.join(
                    project_names[i] for i in p.get("project_ids") or [] if i in project_names
                ),
            }
        )
    for a in view.get("authors") or []:
        rows.append(
            {
                "id": a["id"],
                "type": "author",
                "label": a.get("label") or "",
                "author_id": a.get("author_id"),
                "paper_count": a.get("paper_count"),
            }
        )
    for t in view.get("tags") or []:
        rows.append(
            {
                "id": t["id"],
                "type": "tag",
                "label": t.get("label") or "",
                "key": t.get("key"),
                "paper_count": t.get("paper_count"),
            }
        )
    return rows


def edge_rows(view: dict) -> list[dict]:
    return [
        {"source": e["source"], "target": e["target"], "type": e["target"].split("::", 1)[0]}
        for e in view.get("edges") or []
    ]


def _csv(fields: list[tuple[str, str]], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=[name for name, _ in fields], extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def to_csv_zip(view: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("nodes.csv", _csv(NODE_FIELDS, node_rows(view)))
        z.writestr("edges.csv", _csv(EDGE_FIELDS, edge_rows(view)))
    return buf.getvalue()


def _graphml_value(value: object, kind: str) -> str:
    if kind == "boolean":
        return "true" if value else "false"
    return str(value)


def to_graphml(view: dict) -> bytes:
    root = ET.Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
    # GraphML keys need ids unique across nodes and edges: n_* and e_*.
    for name, kind in NODE_FIELDS[1:]:
        ET.SubElement(
            root, "key", {"id": f"n_{name}", "for": "node", "attr.name": name, "attr.type": kind}
        )
    for name, kind in EDGE_FIELDS[2:]:
        ET.SubElement(
            root, "key", {"id": f"e_{name}", "for": "edge", "attr.name": name, "attr.type": kind}
        )
    graph = ET.SubElement(root, "graph", id="linxiv", edgedefault="undirected")
    for row in node_rows(view):
        node = ET.SubElement(graph, "node", id=row["id"])
        for name, kind in NODE_FIELDS[1:]:
            value = row.get(name)
            if value is None or value == "":
                continue
            ET.SubElement(node, "data", key=f"n_{name}").text = _graphml_value(value, kind)
    for i, row in enumerate(edge_rows(view)):
        edge = ET.SubElement(graph, "edge", id=f"e{i}", source=row["source"], target=row["target"])
        ET.SubElement(edge, "data", key="e_type").text = row["type"]
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
