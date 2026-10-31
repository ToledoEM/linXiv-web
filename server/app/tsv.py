"""Tab-separated downloads of report lists (PDF check, duplicates)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from fastapi.responses import Response

_BREAKS = re.compile(r"[\t\r\n]+")
# A cell starting with one of these runs as a formula when opened in a spreadsheet.
_FORMULA = ("=", "+", "-", "@")


def cell(value: object) -> str:
    text = _BREAKS.sub(" ", "" if value is None else str(value))
    return "'" + text if text.startswith(_FORMULA) else text


def tsv(header: list[str], rows: Iterable[Iterable[object]]) -> str:
    lines = ["\t".join(header)]
    lines += ["\t".join(cell(v) for v in row) for row in rows]
    return "\n".join(lines) + "\n"


def tsv_response(header: list[str], rows: Iterable[Iterable[object]], filename: str) -> Response:
    return Response(
        tsv(header, rows),
        media_type="text/tab-separated-values; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
