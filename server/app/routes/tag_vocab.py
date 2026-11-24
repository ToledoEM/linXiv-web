"""Tag vocabulary for AI tagging: CSV import/export, aliases and the alias
review queue (app/tag_store.py), plus the vocabulary AI tag suggestions match
against (library tags with paper counts, joined with the CSV tags)."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .. import tag_store
from ..tag_norm import display, norm_key, sibling
from ..tag_pipeline import MAX_TAG_LEN, RESERVED, Vocabulary
from .common import ident, library, run
from .imports import read_upload
from .library import _full_list

router = APIRouter(prefix="/api/tags/vocabulary", tags=["tags"])

MAX_ROWS = 50_000
MAX_ERRORS = 50
# Columns of the two CSV layouts the import reads.
PLAIN = ("tag", "aliases", "weight")
TAG_MAP = ("old_tag", "new_tag", "papers")


async def tag_counts(request: Request) -> tuple[list[str], dict[str, int]]:
    """Every library tag and the papers carrying it (the cached full list)."""
    tags = await run(request, ["tag", "list-all"])
    tags = [t for t in tags if isinstance(t, str)] if isinstance(tags, list) else []
    papers = await _full_list(request, ["list", "--sort", "published"])
    counts: dict[str, int] = {}
    for p in papers if isinstance(papers, list) else []:
        if isinstance(p, dict):
            for t in set(p.get("tags") or []):
                if isinstance(t, str):
                    counts[t] = counts.get(t, 0) + 1
    return tags, counts


async def load_vocabulary(request: Request) -> Vocabulary:
    lib = library(request)
    tags, counts = await tag_counts(request)
    return Vocabulary.build(
        tags, counts, await tag_store.vocab(lib), await tag_store.alias_map(lib)
    )


def _tag(value: object) -> str:
    text = display(str(value or ""))
    if len(text) > MAX_TAG_LEN or any(ord(c) < 32 or ord(c) == 127 for c in text):
        return ""
    return text


def _weight(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    w = float(text)
    if not 0 <= w < 1e12:
        raise ValueError
    return w


def parse_csv(text: str) -> tuple[dict, dict, list[str], str, int]:
    """CSV -> ({key: (tag, weight)}, {alias key: (alias, canonical)}, errors,
    layout, aliases skipped as identifier siblings).

    Layouts: `tag[,aliases][,weight]` (aliases split on `|`), or a consolidation
    tag map `old_tag,new_tag[,cluster][,papers]` where `new_tag` is the tag,
    each `old_tag` spelled differently is an alias and `papers` add up to the weight.
    An alias that is an identifier sibling of its tag (STAT5 for stat3) is skipped:
    clusters built from name embeddings put family members together.
    """
    rows = csv.DictReader(io.StringIO(text))
    head = [h.strip().lower() for h in rows.fieldnames or []]
    rows.fieldnames = head
    if "tag" in head:
        layout = "tags"
    elif "old_tag" in head and "new_tag" in head:
        layout = "tag_map"
    else:
        raise HTTPException(
            status_code=400,
            detail="CSV needs a `tag` column, or `old_tag` and `new_tag` (a tag map)",
        )
    tags: dict[str, tuple[str, float | None]] = {}
    aliases: dict[str, tuple[str, str]] = {}
    errors: list[str] = []
    siblings = 0

    def bad(line: int, why: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(f"line {line}: {why}")

    for n, row in enumerate(rows, start=2):
        if n - 1 > MAX_ROWS:
            raise HTTPException(status_code=413, detail=f"at most {MAX_ROWS} rows")
        canonical = _tag(row.get("tag" if layout == "tags" else "new_tag"))
        key = norm_key(canonical)
        if not key:
            bad(n, "empty or invalid tag")
            continue
        if key in RESERVED:
            bad(n, "reserved tag")
            continue
        try:
            weight = _weight(row.get("weight" if layout == "tags" else "papers"))
        except ValueError:
            bad(n, "weight is not a number from 0")
            continue
        seen = tags.get(key)
        if layout == "tag_map" and seen:
            canonical = seen[0]
            if weight is not None or seen[1] is not None:
                weight = (seen[1] or 0) + (weight or 0)
        elif seen and weight is None:
            weight = seen[1]
        tags[key] = (canonical, weight)
        names = (
            str(row.get("aliases") or "").split("|")
            if layout == "tags"
            else [str(row.get("old_tag") or "")]
        )
        for name in names:
            alias = _tag(name)
            akey = norm_key(alias)
            if not akey or akey == key or akey in RESERVED:
                continue
            if sibling(akey, key):
                siblings += 1
                continue
            aliases.setdefault(akey, (alias, canonical))
    # A tag of the file wins over an alias of the same spelling.
    for key in tags:
        aliases.pop(key, None)
    return tags, aliases, errors, layout, siblings


def _any_csv(data: bytes) -> None:
    """Any UTF-8 text: parse_csv checks the header and every row."""


@router.get("")
async def overview(request: Request):
    lib = library(request)
    return {
        "vocab": await tag_store.vocab(lib),
        "aliases": await tag_store.aliases(lib),
        "pending": len(await tag_store.pending(lib)),
    }


@router.post("/import")
async def import_csv(request: Request, file: UploadFile, replace: bool = False):
    data = await read_upload(request, file, _any_csv)
    tags, aliases, errors, layout, siblings = parse_csv(data.decode("utf-8-sig"))
    if not tags:
        raise HTTPException(status_code=400, detail="no valid tags in the CSV")
    stored = await tag_store.import_vocab(library(request), tags, aliases, replace)
    return {
        **stored,
        "layout": layout,
        "replaced": replace,
        "skipped_siblings": siblings,
        "errors": errors,
    }


@router.get("/export.csv")
async def export_csv(request: Request):
    lib = library(request)
    by_tag: dict[str, list[str]] = {}
    for a in await tag_store.aliases(lib):
        by_tag.setdefault(norm_key(a["canonical"]), []).append(a["alias"])
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(PLAIN)
    rows = await tag_store.vocab(lib)
    listed = set()
    for r in rows:
        listed.add(r["tag_key"])
        weight = "" if r["weight"] is None else f"{r['weight']:g}"
        w.writerow([r["tag"], "|".join(by_tag.get(r["tag_key"], [])), weight])
    # Aliases of tags that are only in the library (not in the CSV vocabulary).
    for a in await tag_store.aliases(lib):
        key = norm_key(a["canonical"])
        if key not in listed:
            listed.add(key)
            w.writerow([a["canonical"], "|".join(by_tag[key]), ""])
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tag-vocabulary.csv"'},
    )


class AliasIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    alias: str = Field(min_length=1, max_length=MAX_TAG_LEN)
    canonical: str = Field(min_length=1, max_length=MAX_TAG_LEN)


@router.post("/aliases")
async def add_alias(request: Request, body: AliasIn):
    alias, canonical = _tag(body.alias), _tag(body.canonical)
    akey, ckey = norm_key(alias), norm_key(canonical)
    if not akey or not ckey:
        raise HTTPException(status_code=400, detail="invalid tag")
    if akey == ckey:
        raise HTTPException(status_code=400, detail="alias and tag are the same once normalized")
    if RESERVED & {akey, ckey}:
        raise HTTPException(status_code=400, detail="reserved tag")
    key = await tag_store.add_alias(library(request), alias, canonical, "user")
    return {"alias_key": key, "alias": alias, "canonical": canonical}


@router.delete("/aliases/{key}")
async def delete_alias(request: Request, key: str):
    if not await tag_store.delete_alias(library(request), ident(key, "alias")):
        raise HTTPException(status_code=404, detail="no such alias")
    return {"deleted": key}


@router.get("/pending")
async def list_pending(request: Request):
    return await tag_store.pending(library(request))


async def _resolve(request: Request, key: str, approve: bool):
    row = await tag_store.resolve_pending(library(request), ident(key, "alias"), approve)
    if row is None:
        raise HTTPException(status_code=404, detail="no such pending alias")
    return {"alias_key": key, "approved": approve}


@router.post("/pending/{key}/approve")
async def approve_pending(request: Request, key: str):
    return await _resolve(request, key, True)


@router.post("/pending/{key}/reject")
async def reject_pending(request: Request, key: str):
    return await _resolve(request, key, False)
