"""DOI clean-up. DOIs read from PDFs can carry punctuation from the surrounding
text (`10.1234/x;`, ` 10.1234/x `), which breaks lookups by DOI. Only the ends
are trimmed: `;`, `(` and `)` are legal inside a DOI (`10.1002/(SICI)…;2-x`).
Same rule as the web's `cleanDoi` (`web/src/format.ts`)."""

from __future__ import annotations

import re

_PREFIX = re.compile(r"^(?:doi:\s*|https?://(?:dx\.|www\.)?doi\.org/)", re.IGNORECASE)
_LEAD = re.compile(r"^[\s\"';,.:<>(\[{]+")
_TRAIL = "\"';,.:>"
_CLOSE = {")": "(", "]": "[", "}": "{"}


def clean_doi(value: object) -> str:
    """`value` without the whitespace, quotes and punctuation around it and
    without a `doi:` / doi.org prefix; "" when nothing is left. A closing
    bracket at the end goes only when it has no opening one inside the DOI."""
    doi = _LEAD.sub("", _PREFIX.sub("", _LEAD.sub("", str(value or ""))))
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
