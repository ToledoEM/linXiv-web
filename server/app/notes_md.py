"""Paper notes as Obsidian Markdown: YAML frontmatter with the paper's metadata,
then one section per note. Same layout as the web's per-paper export
(`web/src/notesMarkdown.ts`); keep the two in step."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

_BAD_NAME = re.compile(r'[\\/:*?"<>|#^\[\]]')


def _q(value: str) -> str:
    # A JSON string is a valid YAML double-quoted scalar.
    return json.dumps(value, ensure_ascii=False)


def _when(ts: str) -> str:
    return str(ts or "").replace("T", " ")[:16]


def _tag(tag: str) -> str:
    """Obsidian tags may not contain spaces."""
    return re.sub(r"\s+", "-", tag.strip())


def file_name(paper: dict) -> str:
    """File name without extension: title minus characters Obsidian/filesystems reject."""

    def clean(s: str) -> str:
        return re.sub(r"\s+", " ", _BAD_NAME.sub("", s)).strip()[:100].strip()

    sid = re.sub(r"[:/]", "_", str(paper.get("source_id") or ""))
    return clean(str(paper.get("title") or "")) or clean(sid) or "paper"


def render(paper: dict, notes: list[dict], scope_label: Callable[[int | None], str]) -> str:
    title = str(paper.get("title") or "").strip() or str(paper.get("source_id") or "")
    lines = ["---", f"title: {_q(title)}"]
    authors = [str(a) for a in paper.get("authors") or [] if str(a).strip()]
    if authors:
        lines += ["authors:", *(f"  - {_q(a)}" for a in authors)]
    doi = str(paper.get("doi") or "").strip()
    if doi:
        lines.append(f"doi: {_q(doi)}")
    lines.append(f"source_id: {_q(str(paper.get('source_id') or ''))}")
    if paper.get("published"):
        lines.append(f"published: {_q(str(paper['published']))}")
    if paper.get("url"):
        lines.append(f"url: {_q(str(paper['url']))}")
    tags = [t for t in (_tag(str(t)) for t in paper.get("tags") or []) if t]
    if tags:
        lines += ["tags:", *(f"  - {_q(t)}" for t in tags)]
    lines += ["---", "", f"# {title}", ""]
    for n in notes:
        lines.append(f"## {str(n.get('title') or '').strip() or 'Untitled note'}")
        created, updated = _when(n.get("created_at")), _when(n.get("updated_at"))
        lines += [
            f"*{scope_label(n.get('project_id'))} · created {created} · updated {updated}*",
            "",
        ]
        lines += [str(n.get("content") or "").rstrip(), ""]
    return "\n".join(lines)
