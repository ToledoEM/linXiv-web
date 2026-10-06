"""Authors (`linxiv author ...`)."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..cli import CLIError
from .common import run

router = APIRouter(prefix="/api", tags=["authors"])

ORCID_RE = re.compile(r"^(\d{4})-?(\d{4})-?(\d{4})-?(\d{3}[\dX])$")
MAX_MERGE = 500


def _orcid(value: str) -> str:
    """Normalize to `0000-0000-0000-000X` and check the ISO 7064 11-2 digit.
    The CLI stores any string, so a typo would never match a real ORCID."""
    v = value.strip().upper()
    for prefix in ("HTTPS://ORCID.ORG/", "HTTP://ORCID.ORG/", "ORCID.ORG/"):
        v = v.removeprefix(prefix)
    m = ORCID_RE.match(v)
    if not m:
        raise ValueError("ORCID must look like 0000-0002-1825-0097")
    digits = "".join(m.groups())
    total = 0
    for d in digits[:-1]:
        total = (total + int(d)) * 2
    check = (12 - total % 11) % 11
    if digits[-1] != ("X" if check == 10 else str(check)):
        raise ValueError("ORCID check digit is wrong")
    return "-".join(m.groups())


class AuthorUpdate(BaseModel):
    """Blank fields are dropped: the CLI ignores empty values and cannot clear one."""

    model_config = ConfigDict(extra="forbid", strict=True)

    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    orcid: str | None = None

    @field_validator("full_name", "first_name", "last_name", "orcid")
    @classmethod
    def _blank(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if len(value) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("invalid name")
        return value

    @field_validator("orcid")
    @classmethod
    def _check_orcid(cls, value: str | None) -> str | None:
        return None if value is None else _orcid(value)

    @model_validator(mode="after")
    def _some(self) -> AuthorUpdate:
        if not any((self.full_name, self.first_name, self.last_name, self.orcid)):
            raise ValueError("at least one field is required")
        return self


class AuthorMerge(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    duplicate_ids: list[int] = Field(min_length=1, max_length=MAX_MERGE)


@router.get("/authors")
async def list_authors(request: Request, hide_single: bool = False):
    """`author list`; `hide_single` drops authors with fewer than two papers
    (the CLI has no such flag, so it's filtered here)."""
    authors = await run(request, ["author", "list"])
    if not hide_single or not isinstance(authors, list):
        return authors
    return [a for a in authors if (a.get("paper_count") or 0) > 1]


@router.get("/authors/{author_id}/merge-candidates")
async def merge_candidates(request: Request, author_id: int):
    """ORCID matches from the CLI, plus `name_candidates`: other records with the
    same full name (case-insensitive). The v0.6.0 CLI only returns the first."""
    found = await run(request, ["author", "merge-candidates", "--", str(author_id)])
    candidates = (found.get("candidates") if isinstance(found, dict) else None) or []
    me = await run(request, ["author", "get", "--", str(author_id)])
    name = (me.get("full_name") or "").strip().casefold()
    taken = {author_id, *(c.get("author_id") for c in candidates)}
    authors = await run(request, ["author", "list"]) if name else []
    same_name = [
        {k: a.get(k) for k in ("author_id", "orcid", "full_name", "first_name", "last_name")}
        for a in authors
        if a.get("author_id") not in taken and (a.get("full_name") or "").strip().casefold() == name
    ]
    return {"candidates": candidates, "name_candidates": same_name}


@router.post("/authors/{author_id}/merge")
async def merge_authors(request: Request, author_id: int, body: AuthorMerge):
    """Re-point the duplicates' papers to `author_id` and delete the duplicates.
    Unknown duplicate ids are skipped by the CLI (absent from `merged_ids`)."""
    ids = sorted({i for i in body.duplicate_ids if i != author_id})
    if not ids:
        raise HTTPException(status_code=400, detail="pick at least one other author")
    return await run(request, ["author", "merge", "--", str(author_id), *map(str, ids)])


@router.get("/authors/{author_id}")
async def get_author(request: Request, author_id: int):
    return await run(request, ["author", "get", "--", str(author_id)])


@router.patch("/authors/{author_id}")
async def update_author(request: Request, author_id: int, body: AuthorUpdate):
    args = ["author", "update"]
    for flag, value in (
        ("full-name", body.full_name),
        ("first-name", body.first_name),
        ("last-name", body.last_name),
        ("orcid", body.orcid),
    ):
        if value is not None:
            args.append(f"--{flag}={value}")
    return await run(request, [*args, "--", str(author_id)])


@router.delete("/authors/{author_id}")
async def delete_author(request: Request, author_id: int):
    """Refused (409) while the author is still linked to any paper."""
    try:
        return await run(request, ["author", "delete", "--", str(author_id)])
    except CLIError as e:
        if "linked to" in e.message:
            raise HTTPException(status_code=409, detail=e.message) from e
        raise
