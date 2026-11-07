"""BibTeX entries for papers (`linxiv list` JSON).

linXiv's own `project export-bibtex` works per project only, so selections
are formatted here. arXiv papers become `@misc`
with `eprint`/`archivePrefix`/`primaryClass` (or `@article` when they carry a
journal reference); everything else is `@article`.

A paper's stored BibTeX fields (app/bib_store.py) fill in the rest: an
`entry_type` replaces the guess above (the journal is then `booktitle` for
`inproceedings` / `incollection`), and every other non-null field is written.
"""

from __future__ import annotations

import re
import unicodedata

from .bib_store import BIB_FIELDS, MONTHS
from .doi import doi_or_none

_MATH = re.compile(r"(\$[^$]*\$)")
_SPECIAL = re.compile(r"(?<!\\)([&%#_])")
_STOP = {"a", "an", "the", "on", "of", "in", "for", "and", "to", "from", "with", "towards"}
# Stored key -> BibTeX field name, where they differ.
_NAMES = {"archive_prefix": "archivePrefix", "primary_class": "primaryClass"}
# Entry types whose container is a `booktitle`, not a `journal`.
_IN_BOOK = {"inproceedings", "incollection", "conference"}


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


def entry(paper: dict, key: str, bib: dict | None = None) -> str:
    bib = bib or {}
    arxiv = _arxiv_id(paper)
    journal = paper.get("journal_ref") or (None if arxiv else paper.get("category"))
    kind = bib.get("entry_type") or ("misc" if arxiv and not journal else "article")
    fields: list[tuple[str, str]] = []
    if paper.get("title"):
        fields.append(("title", escape(str(paper["title"]))))
    authors = [escape(str(a)) for a in paper.get("authors") or [] if str(a).strip()]
    if authors:
        fields.append(("author", " and ".join(authors)))
    if journal and not (kind in _IN_BOOK and bib.get("booktitle")):
        fields.append(("booktitle" if kind in _IN_BOOK else "journal", escape(str(journal))))
    year = str(paper.get("published") or "")[:4]
    if year.isdigit():
        fields.append(("year", year))
    raw = []  # month macros go unbraced
    for name in BIB_FIELDS:
        value = bib.get(name)
        if name == "entry_type" or not value:
            continue
        if arxiv and name in ("eprint", "archive_prefix", "primary_class"):
            continue  # written from the paper's own id below
        if name == "month" and value in MONTHS:
            raw.append(len(fields))
            fields.append(("month", value))
            continue
        fields.append((_NAMES.get(name, name), escape(str(value))))
    doi = doi_or_none(paper.get("doi"))
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
    body = ",\n".join(
        f"  {name} = {value}" if i in raw else f"  {name} = {{{value}}}"
        for i, (name, value) in enumerate(fields)
    )
    return f"@{kind}{{{key},\n{body}\n}}\n"


def render(papers: list[dict], bibs: dict[str, dict] | None = None) -> str:
    """All entries, keys made unique with a/b/c… suffixes; `bibs`: stored
    BibTeX fields by source_id."""
    seen: dict[str, int] = {}
    out = []
    for paper in papers:
        key = base_key(paper)
        n = seen.get(key, 0)
        seen[key] = n + 1
        if n:
            key = f"{key}{_suffix(n)}"
        out.append(entry(paper, key, (bibs or {}).get(str(paper.get("source_id")))))
    return "\n".join(out)


def _suffix(n: int) -> str:
    """1 → a, 26 → z, 27 → aa."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(97 + r) + s
    return s
