"""BibTeX entries for papers (`linxiv list` JSON).

linXiv's own `project export-bibtex` writes no `author` field and works per
project only, so selections are formatted here. arXiv papers become `@misc`
with `eprint`/`archivePrefix`/`primaryClass` (or `@article` when they carry a
journal reference); everything else is `@article`.
"""

from __future__ import annotations

import re
import unicodedata

from .doi import clean_doi

_MATH = re.compile(r"(\$[^$]*\$)")
_SPECIAL = re.compile(r"(?<!\\)([&%#_])")
_STOP = {"a", "an", "the", "on", "of", "in", "for", "and", "to", "from", "with", "towards"}


def _ascii_word(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]", "", folded).lower()


def escape(value: str) -> str:
    """Escape `& % # _` outside `$…$` math; drop braces when they don't balance."""
    parts = _MATH.split(" ".join(value.split()))
    out = "".join(p if i % 2 else _SPECIAL.sub(r"\\\1", p) for i, p in enumerate(parts))
    depth = 0
    for ch in out:
        depth += {"{": 1, "}": -1}.get(ch, 0)
        if depth < 0:
            break
    if depth != 0:
        out = out.replace("{", "").replace("}", "")
    return out


def _surname(author: str) -> str:
    author = author.strip()
    if "," in author:
        return author.split(",", 1)[0]
    return author.split()[-1] if author.split() else ""


def base_key(paper: dict) -> str:
    authors = paper.get("authors") or []
    who = _ascii_word(_surname(authors[0])) if authors else ""
    year = str(paper.get("published") or "")[:4]
    year = year if year.isdigit() else ""
    words = [_ascii_word(w) for w in str(paper.get("title") or "").split()]
    word = next((w for w in words if w and w not in _STOP), "")
    key = f"{who or 'anon'}{year}{word}"
    return key or _ascii_word(str(paper.get("source_id") or "")) or "paper"


def _arxiv_id(paper: dict) -> str | None:
    sid = str(paper.get("source_id") or "")
    return sid.split(":", 1)[1] if sid.startswith("arxiv:") else None


def entry(paper: dict, key: str) -> str:
    arxiv = _arxiv_id(paper)
    journal = paper.get("journal_ref") or (None if arxiv else paper.get("category"))
    fields: list[tuple[str, str]] = []
    if paper.get("title"):
        fields.append(("title", escape(str(paper["title"]))))
    authors = [escape(str(a)) for a in paper.get("authors") or [] if str(a).strip()]
    if authors:
        fields.append(("author", " and ".join(authors)))
    if journal:
        fields.append(("journal", escape(str(journal))))
    year = str(paper.get("published") or "")[:4]
    if year.isdigit():
        fields.append(("year", year))
    doi = clean_doi(paper.get("doi"))
    if doi:
        fields.append(("doi", doi))
    if arxiv:
        fields += [("eprint", arxiv), ("archivePrefix", "arXiv")]
        if paper.get("category"):
            fields.append(("primaryClass", str(paper["category"])))
        fields.append(("url", f"https://arxiv.org/abs/{arxiv}"))
    elif doi:
        fields.append(("url", f"https://doi.org/{doi}"))
    elif str(paper.get("url") or "").startswith(("http://", "https://")):
        fields.append(("url", str(paper["url"])))
    kind = "misc" if arxiv and not journal else "article"
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
    return f"@{kind}{{{key},\n{body}\n}}\n"


def render(papers: list[dict]) -> str:
    """All entries, keys made unique with a/b/c… suffixes."""
    seen: dict[str, int] = {}
    out = []
    for paper in papers:
        key = base_key(paper)
        n = seen.get(key, 0)
        seen[key] = n + 1
        if n:
            key = f"{key}{_suffix(n)}"
        out.append(entry(paper, key))
    return "\n".join(out)


def _suffix(n: int) -> str:
    """1 → a, 26 → z, 27 → aa."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(97 + r) + s
    return s
