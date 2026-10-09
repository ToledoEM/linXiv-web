"""What a PDF's file name says about the paper.

Imported collections (a Mendeley export, a folder sorted by year) often name each
file after the paper's title and keep it in a year folder, while the metadata
linXiv reads from inside old PDFs can be junk ("Abstract", "dev4172.q") or belong
to another paper. These helpers read the stored `pdf_path` as a second opinion:
a title and year to search by, and a flag for titles that look wrong. Pure
string work, no file access.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import PurePosixPath

# linXiv's own copy of a paper's PDF: `doi_10.1000_xyzv1.pdf`, `arxiv_1706.03762v7.pdf`.
_MANAGED = re.compile(r"^[a-z]+_.+v\d+$")
# Publisher and preprint download names that carry no title.
_CODE = re.compile(
    r"^(\d+_\d{4}_article_\d+|\d{4}\.\d{2}\.\d{2}\.\d+v\d+(\.full)?|[a-z]?\d[\d._-]*)$",
    re.IGNORECASE,
)
_CLASH = re.compile(r"_\d+$")  # `_2` added when two files cleaned to the same name
_JUNK = re.compile(
    r"^(abstract|untitled|title|article|contents?|editorial|index)\W*$"
    r"|^©|^\(c\)|^\W"
    r"|^figure s?\d|^supplement|^supporting information"
    r"|\.(tif|tiff|dvi|doc|docx|q|tex|pdf|ps|indd)\b"
    r"|ghostscript|microsoft word|acrobat distiller|untitled document",
    re.IGNORECASE,
)
MIN_TITLE = 12
MIN_WORDS = 3
SIMILAR = 0.5


def pdf_file(pdf_path: str | None, bases: list[str]) -> str | None:
    """`pdf_path` relative to the first PDF folder in `bases` that contains it."""
    if not pdf_path:
        return None
    for base in bases:
        prefix = base.rstrip("/") + "/"
        if pdf_path.startswith(prefix) and len(pdf_path) > len(prefix):
            return pdf_path[len(prefix) :]
    return None


def title_from_file(rel: str | None) -> str | None:
    """A searchable title from a descriptive file name, or None when the name
    is one of linXiv's copies, a download code, or too short to mean anything."""
    if not rel:
        return None
    stem = PurePosixPath(rel).stem
    if _MANAGED.match(stem) or _CODE.match(stem):
        return None
    stem = _CLASH.sub("", stem)
    words = [w for w in re.split(r"[_\s]+", stem) if w]
    if len(words) < MIN_WORDS:
        return None
    letters = sum(c.isalpha() for c in stem)
    if letters < len(stem) / 2:
        return None
    return " ".join(words)


def year_from_file(rel: str | None) -> int | None:
    """The year of the innermost folder named like one (`Mendeley/1995/x.pdf`)."""
    if not rel:
        return None
    for part in reversed(PurePosixPath(rel).parts[:-1]):
        if re.fullmatch(r"\d{4}", part) and 1900 <= int(part) <= datetime.now(UTC).year:
            return int(part)
    return None


def _words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def title_suspect(title: str | None, file_title: str | None) -> bool:
    """True when the stored title is empty, looks like junk read from the PDF,
    or has little in common with the title in the file name."""
    t = (title or "").strip()
    if len(t) < MIN_TITLE or t.replace(" ", "").isdigit() or _JUNK.search(t):
        return True
    if not file_title:
        return False
    a, b = _words(t), _words(file_title)
    # File names are often cut short: compare against the same length of title.
    a = a[: max(len(b), 1) + 10]
    return SequenceMatcher(None, a, b).ratio() < SIMILAR
