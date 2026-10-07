"""AI routes: provider checks for Settings → AI (list models, test the
connection) and tag suggestions.

All use the saved provider settings (never values from the request) and refuse
while `ai_enabled` is off. Suggestions are only returned; the UI adds the tags
the user accepts through the normal tag routes.
"""

from __future__ import annotations

import re
import time

from fastapi import APIRouter, HTTPException, Request

from .. import ai
from .common import ident, run

router = APIRouter(prefix="/api/ai", tags=["ai"])

TEST_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
TEST_EXAMPLE = {"ok": True}


# Tag suggestions: at most this many per paper, and this much of the library's
# tag vocabulary in the prompt.
MAX_SUGGESTED = 8
MAX_VOCABULARY = 400
MAX_TAG_LEN = 64
MAX_ABSTRACT_CHARS = 6000
TAGS_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": MAX_TAG_LEN},
            "maxItems": MAX_SUGGESTED,
        }
    },
    "required": ["tags"],
    "additionalProperties": False,
}
TAGS_EXAMPLE = {"tags": ["single-cell rna-seq", "drug response", "perturbation atlas"]}
TAGS_SYSTEM = (
    "You tag research papers in a personal library. Suggest 3 to 6 short topical tags "
    "for the paper: lowercase, one to three words, no '#'. Reuse tags from the existing "
    "vocabulary when they fit; add a new tag only for an important topic it lacks. "
    "Do not repeat the paper's current tags."
)


# What each AI function asks the model to return; shown in Settings → AI.
TASKS = [
    {
        "id": "test",
        "label": "Test connection",
        "schema": TEST_SCHEMA,
        "example": TEST_EXAMPLE,
    },
    {
        "id": "tags",
        "label": "Tag suggestions",
        "schema": TAGS_SCHEMA,
        "example": TAGS_EXAMPLE,
    },
]
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


async def _config(request: Request) -> ai.AIConfig:
    stored = await run(request, ["settings", "get"])
    try:
        return ai.config_from(stored if isinstance(stored, dict) else {})
    except ai.AIError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e


@router.get("/models")
async def models(request: Request):
    cfg = await _config(request)
    try:
        ids = await ai.list_models(cfg)
    except ai.AIError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    return {"provider": cfg.provider, "models": ids}


@router.get("/schemas")
async def schemas():
    """The JSON Schema and example reply each AI function sends (static; no
    provider call, works while AI is off)."""
    return [{**t, "schema": {"$schema": JSON_SCHEMA_DIALECT, **t["schema"]}} for t in TASKS]


@router.post("/test")
async def test(request: Request):
    cfg = await _config(request)
    started = time.monotonic()
    try:
        reply = await ai.complete(
            cfg,
            'Connection test. Reply {"ok": true}.',
            schema=TEST_SCHEMA,
            example=TEST_EXAMPLE,
            max_tokens=256,
        )
    except ai.AIError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    return {
        "ok": isinstance(reply, dict) and reply.get("ok") is True,
        "provider": cfg.provider,
        "model": cfg.model,
        "ms": round((time.monotonic() - started) * 1000),
    }


def _clean_tags(raw: object, current: list[str], vocabulary: list[str]) -> list[dict]:
    """Model output -> [{tag, known}]: trimmed, deduped, minus the paper's tags,
    spelled like the vocabulary when it matches one."""
    if not isinstance(raw, dict) or not isinstance(raw.get("tags"), list):
        raise HTTPException(status_code=502, detail="The model returned no tags")
    known = {t.casefold(): t for t in vocabulary}
    taken = {t.casefold() for t in current}
    out: list[dict] = []
    for item in raw["tags"]:
        if not isinstance(item, str):
            continue
        tag = re.sub(r"\s+", " ", item.strip().lstrip("#")).strip()
        if not tag or len(tag) > MAX_TAG_LEN or any(ord(c) < 32 or ord(c) == 127 for c in tag):
            continue
        key = tag.casefold()
        if key in taken:
            continue
        taken.add(key)
        out.append({"tag": known.get(key, tag), "known": key in known})
        if len(out) == MAX_SUGGESTED:
            break
    return out


@router.post("/tags/{source_id:path}")
async def suggest_tags(request: Request, source_id: str):
    """Suggested tags for one paper from its title, abstract and categories,
    steered toward the library's existing tags."""
    cfg = await _config(request)
    sid = ident(source_id)
    paper = await run(request, ["paper", "get", "--", sid])
    vocabulary = await run(request, ["tag", "list-all"])
    vocabulary = (
        [t for t in vocabulary if isinstance(t, str)] if isinstance(vocabulary, list) else []
    )
    current = [t for t in (paper.get("tags") or []) if isinstance(t, str)]
    categories = paper.get("categories") or ([paper["category"]] if paper.get("category") else [])
    prompt = "\n".join(
        [
            f"Title: {paper.get('title') or ''}",
            f"Categories: {', '.join(str(c) for c in categories) or 'none'}",
            f"Abstract: {(paper.get('summary') or 'none')[:MAX_ABSTRACT_CHARS]}",
            f"Current tags: {', '.join(current) or 'none'}",
            f"Existing vocabulary: {', '.join(vocabulary[:MAX_VOCABULARY]) or 'none yet'}",
        ]
    )
    try:
        raw = await ai.complete(
            cfg,
            prompt,
            system=TAGS_SYSTEM,
            schema=TAGS_SCHEMA,
            example=TAGS_EXAMPLE,
            max_tokens=512,
        )
    except ai.AIError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    return {"source_id": sid, "suggested": _clean_tags(raw, current, vocabulary)}
