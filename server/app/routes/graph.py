"""Knowledge Graph payload (`GET /api/graph`).

linXiv desktop builds this in core (`linxiv_core::graph::graph_view`) from SQL;
the CLI has no such command, so it is assembled here from `list`, `author
list`, `project list`, `tag list-all` and `categories`, in the same shape.

Paper rows only carry author NAMES, so author nodes are joined by name. Names
that resolve to no author (renamed or merged since the paper was saved) or to
several (two records, one name) are settled with `author get`, which lists the
author's papers; only those authors cost a CLI call.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Request

from .common import run

router = APIRouter(prefix="/api", tags=["graph"])

DEFAULT_PROJECT_COLOR = "#5b8dee"
READING_LIST_TAG = "reading-list"
# Upper bound on `author get` calls per request; beyond it, anomalies stay name-only.
MAX_AUTHOR_LOOKUPS = 200
NO_PUBLISHED_DATE = {"", "0001-01-01"}


def norm_tag(raw: str) -> str:
    return raw.strip().lower()


def _name(raw: object) -> str:
    return str(raw or "").strip().casefold()


async def _author_links(request: Request, papers: list[dict], authors: list[dict]):
    """Paper SOURCE_FK -> [author dict] in the paper's author order."""
    by_name: dict[str, list[dict]] = defaultdict(list)
    for a in authors:
        if a.get("full_name"):
            by_name[_name(a["full_name"])].append(a)
    by_id = {a["author_id"]: a for a in authors}

    links: dict[int, list[dict]] = defaultdict(list)
    named: set[str] = set()
    unresolved_papers: set[int] = set()
    for p in papers:
        for raw in p.get("authors") or []:
            key = _name(raw)
            named.add(key)
            hits = by_name.get(key, [])
            if len(hits) == 1:
                links[p["source_fk"]].append(hits[0])
            else:
                unresolved_papers.add(p["source_fk"])

    # Authors that no paper names (renamed/merged), or that share a name with
    # another record, can only be placed by asking for their papers.
    suspects = [
        a
        for a in authors
        if (a.get("paper_count") or 0) > 0
        and (_name(a.get("full_name")) not in named or len(by_name[_name(a.get("full_name"))]) > 1)
    ]
    if suspects and unresolved_papers:
        fk_by_sid = {p["source_id"]: p["source_fk"] for p in papers}
        for a in suspects[:MAX_AUTHOR_LOOKUPS]:
            detail = await run(request, ["author", "get", "--", str(a["author_id"])])
            for row in (detail or {}).get("papers") or []:
                fk = fk_by_sid.get(row.get("source_id"))
                if fk is not None and fk in unresolved_papers:
                    linked = links[fk]
                    if all(x["author_id"] != a["author_id"] for x in linked):
                        linked.append(by_id[a["author_id"]])
    return links


@router.get("/graph")
async def graph_view(request: Request, exclude_single_authors: bool = False):
    papers = [p for p in (await run(request, ["list"]) or []) if isinstance(p, dict)]
    authors = [a for a in (await run(request, ["author", "list"]) or []) if isinstance(a, dict)]
    projects = await run(request, ["project", "list", "--status", "active"]) or []
    all_tags = await run(request, ["tag", "list-all"]) or []
    categories = await run(request, ["categories"]) or []

    canonical = {norm_tag(t): t.strip() for t in all_tags if isinstance(t, str)}
    paper_projects: dict[str, list[int]] = defaultdict(list)
    for proj in projects:
        for sid in proj.get("source_ids") or []:
            paper_projects[sid].append(proj["id"])

    links = await _author_links(request, papers, authors)
    if exclude_single_authors:
        keep = {a["author_id"] for a in authors if (a.get("paper_count") or 0) > 1}
        links = {fk: [a for a in lst if a["author_id"] in keep] for fk, lst in links.items()}

    edges: list[dict] = []
    out_papers: list[dict] = []
    tag_acc: dict[str, list] = {}
    author_degree: dict[int, int] = defaultdict(int)
    on_graph: set[int] = set()

    for p in sorted(papers, key=lambda p: p["source_fk"]):
        node_id = str(p["source_fk"])
        project_ids = sorted(set(paper_projects.get(p["source_id"], [])))
        on_graph.update(project_ids)

        tags: list[str] = []
        tag_keys: list[str] = []
        for raw in p.get("tags") or []:
            key = norm_tag(str(raw))
            if not key or key in tag_keys:
                continue
            label = canonical.get(key, str(raw).strip())
            tag_acc.setdefault(key, [label, 0])[1] += 1
            edges.append({"source": node_id, "target": f"tag::{key}"})
            tags.append(label)
            tag_keys.append(key)

        author_keys: list[str] = []
        linked = links.get(p["source_fk"], [])
        for a in linked:
            author_keys.append(str(a["full_name"]).lower())
            author_degree[a["author_id"]] += 1
            edges.append({"source": node_id, "target": f"author::{a['author_id']}"})
        # Names that matched no author still count for the Author filter.
        if not linked or len(linked) < len(p.get("authors") or []):
            for raw in p.get("authors") or []:
                if str(raw).lower() not in author_keys:
                    author_keys.append(str(raw).lower())

        published = p.get("published")
        out_papers.append(
            {
                "id": node_id,
                "source_fk": p["source_fk"],
                "source_id": p["source_id"],
                "label": p.get("title") or "",
                "category": p.get("category"),
                "tags": tags,
                "tag_keys": tag_keys,
                "has_pdf": bool(p.get("has_pdf")),
                "published": None if published in NO_PUBLISHED_DATE else published,
                "url": p.get("url"),
                "doi": p.get("doi"),
                "summary": p.get("summary"),
                "project_ids": project_ids,
                "author_keys": author_keys,
            }
        )

    out_authors = [
        {
            "id": f"author::{a['author_id']}",
            "author_id": a["author_id"],
            "label": a.get("full_name") or "",
            "paper_count": author_degree[a["author_id"]],
        }
        for a in authors
        if author_degree.get(a["author_id"], 0) > 0
    ]
    out_tags = [
        {"id": f"tag::{key}", "key": key, "label": label, "paper_count": count}
        for key, (label, count) in sorted(tag_acc.items())
    ]
    out_projects = sorted(
        (
            {
                "id": proj["id"],
                "name": proj.get("name") or "",
                "color": proj.get("color_hex") or DEFAULT_PROJECT_COLOR,
                "tags": sorted(
                    t for t in proj.get("project_tags") or [] if t.lower() != READING_LIST_TAG
                ),
                "on_graph": proj["id"] in on_graph,
            }
            for proj in projects
        ),
        key=lambda x: x["id"],
    )
    return {
        "papers": out_papers,
        "authors": out_authors,
        "tags": out_tags,
        "edges": edges,
        "categories": categories,
        "projects": out_projects,
    }
