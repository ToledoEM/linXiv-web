"""DOI clean-up and validation. DOIs read from PDFs or pasted by people carry
the text around them (`10.1234/x;`, `DOI: 10.1234/x.`, `https://doi.org/10.1234%2Fx`),
which breaks lookups by DOI. `clean_doi` pulls the DOI out: it drops a doi.org
URL (percent-decoded) or `doi:` prefix, starts at the first `10.<registrant>/`,
stops at whitespace and trims punctuation off the end only, since `;`, `(` and
`)` are legal inside a DOI (`10.1002/(SICI)…;2-x`).

`is_valid_doi` uses Crossref's patterns
(https://www.crossref.org/blog/dois-and-matching-regular-expressions/): the
modern one matches 74.4M of 74.9M DOIs, the rest are older Wiley, SICI, ACS and
10.1207 forms. Same rules as the web's `cleanDoi` / `isValidDoi`
(`web/src/format.ts`); both run `server/tests/fixtures/doi-vectors.json`.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

_URL = re.compile(r"^(?:https?://)?(?:dx\.|www\.)?doi\.org/", re.IGNORECASE)
_PREFIX = re.compile(r"^doi:\s*", re.IGNORECASE)
_LEAD = re.compile(r"^[\s\"';,.:<>(\[{]+")
_START = re.compile(r"10\.\d{4,9}/\S+")
_TRAIL = "\"';,.:>"
_CLOSE = {")": "(", "]": "[", "}": "{"}

_VALID = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$",
        r"^10\.1002/\S+$",
        # SICI: the parentheses are literal (Crossref's regex leaves them unescaped).
        r"^10\.\d{4}/\d+-\d+X?\(\d+\)\d+<\w+:\w*>\d+\.\d+\.\w+;\d$",
        r"^10\.1021/\w\w\d+$",
        r"^10\.1207/\w+&\d+_\d+$",
    )
]


def clean_doi(value: object) -> str:
    """The DOI in `value`, without the text, quotes and punctuation around it
    and without a `doi:` / doi.org prefix; "" when nothing is left. Text with no
    `10.<registrant>/` in it is only trimmed. A closing bracket at the end goes
    only when it has no opening one inside the DOI."""
    doi = _LEAD.sub("", str(value or ""))
    if m := _URL.match(doi):
        doi = unquote(doi[m.end() :])
    doi = _LEAD.sub("", _PREFIX.sub("", doi))
    if m := _START.search(doi):
        doi = m.group(0)
    while doi:
        last = doi[-1]
        if (
            last.isspace()
            or last in _TRAIL
            or (last in _CLOSE and doi.count(last) > doi.count(_CLOSE[last]))
        ):
            doi = doi[:-1]
        else:
            break
    return doi


def is_valid_doi(doi: str) -> bool:
    """`doi` (already cleaned) has a shape Crossref's patterns accept."""
    return any(p.match(doi) for p in _VALID)


def doi_or_none(value: object) -> str | None:
    """The cleaned DOI when it is valid, else None (shown, exported and looked
    up as no DOI)."""
    doi = clean_doi(value)
    return doi if doi and is_valid_doi(doi) else None
