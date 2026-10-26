"""Remove authors without papers (maintenance operation; deletes, so the panel
asks before Run and it is not nightly unless ticked).

Authors whose `paper_count` in `linxiv author list` is 0, e.g. left behind when
their papers were deleted, are removed with `linxiv author delete`. linXiv
refuses to delete an author still linked to a paper; those are counted as
skipped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .cli import CLIError
from .maintenance import Op

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .jobs import Job
    from .libraries import Library


async def clean_authors(app: FastAPI, lib: Library, job: Job) -> dict:
    out = {"authors_removed": 0, "skipped": 0}
    timeout = app.state.settings.timeout_short
    authors = await lib.cli(["author", "list"], timeout)
    for a in authors if isinstance(authors, list) else []:
        if job.cancel_requested:
            break
        aid = a.get("author_id") if isinstance(a, dict) else None
        if not isinstance(aid, int) or a.get("paper_count") != 0:
            continue
        job.current = f"{lib.key}: {a.get('full_name') or aid}"
        try:
            await lib.cli(["author", "delete", "--", str(aid)], timeout)
            out["authors_removed"] += 1
        except CLIError:
            out["skipped"] += 1  # still linked to a paper
    return out


OP = Op(
    "clean-authors",
    "Clean authors without papers",
    "Deletes author records that no paper uses any more. Authors still linked to a paper are kept.",
    clean_authors,
    destructive=True,
)
