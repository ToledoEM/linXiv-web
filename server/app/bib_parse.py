"""Read the entries of a `.bib` file (BibTeX import).

linXiv's `bibtex import` keeps title, authors, year, DOI and so on, and drops
the rest of each entry (volume, pages, publisher...). This reads those back so
the import stores them (app/bib_store.py). It is a small tolerant parser:
`@type{key, name = {value} | "value" | bare, ...}`, nested braces, `#` joins
ignored; @comment, @string and @preamble are skipped.
"""

from __future__ import annotations

import re

from .bib_store import BIB_FIELDS

_SKIP = {"comment", "string", "preamble"}
_NAMES = {"archiveprefix": "archive_prefix", "primaryclass": "primary_class"}
_FIELD = re.compile(r"\s*([A-Za-z][\w\-:.]*)\s*=\s*")
_BARE = re.compile(r"[^,}\s]*")


def _value(text: str, i: int) -> tuple[str, int]:
    """One field value starting at text[i]; returns (value, index after it)."""
    if i < len(text) and text[i] == "{":
        depth, j = 0, i
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    return text[i + 1 : j], j + 1
            j += 1
        return text[i + 1 :], len(text)
    if i < len(text) and text[i] == '"':
        depth, j = 0, i + 1
        while j < len(text):
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == '"' and depth == 0:
                return text[i + 1 : j], j + 1
            j += 1
        return text[i + 1 :], len(text)
    m = _BARE.match(text, i)
    end = m.end() if m else i
    return text[i:end], end


def _body(text: str, start: int) -> tuple[str, int]:
    """The text between an entry's outer braces (or parentheses)."""
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else ")"
    depth, j = 0, start
    while j < len(text):
        if text[j] == open_ch:
            depth += 1
        elif text[j] == close_ch:
            depth -= 1
            if depth == 0:
                return text[start + 1 : j], j + 1
        j += 1
    return text[start + 1 :], len(text)


def _fields(body: str) -> dict[str, str]:
    comma = body.find(",")
    if comma < 0:
        return {}
    out: dict[str, str] = {}
    i = comma + 1
    while i < len(body):
        m = _FIELD.match(body, i)
        if not m:
            nxt = body.find(",", i)
            if nxt < 0:
                break
            i = nxt + 1
            continue
        value, i = _value(body, m.end())
        out[m.group(1).lower()] = " ".join(value.replace("{", "").replace("}", "").split())
        nxt = body.find(",", i)
        if nxt < 0:
            break
        i = nxt + 1
    return out


def entries(text: str) -> list[dict]:
    """[{entry_type, fields: {lower-case name: value}}] in file order."""
    out = []
    for m in re.finditer(r"@\s*([A-Za-z]+)\s*([{(])", text):
        kind = m.group(1).lower()
        if kind in _SKIP:
            continue
        body, _ = _body(text, m.end() - 1)
        out.append({"entry_type": kind, "fields": _fields(body)})
    return out


def bib_fields(entry: dict) -> dict[str, str]:
    """The entry's values under bib_store names (not yet cleaned)."""
    fields = entry.get("fields") or {}
    out = {"entry_type": entry.get("entry_type")}
    for name, value in fields.items():
        key = _NAMES.get(name, name)
        if key in BIB_FIELDS and key != "entry_type":
            out[key] = value
    return out


def norm_title(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()
