"""PDF highlight annotations (`linxiv annotation ...`).

The anchor is opaque to the CLI (it stores any string), but linXiv desktop
renders it, so it is validated here against the desktop shape
(`src/lib/pdfAnchor.ts`) and re-serialized the way desktop's JSON.stringify
writes it. The CLI can only change a comment; a color change re-creates the
annotation with the new anchor, then deletes the old one.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..cli import CLIError
from .common import ident, run

router = APIRouter(prefix="/api", tags=["annotations"])

MAX_RECTS = 500
MAX_QUOTE_LEN = 10_000
MAX_COMMENT_BYTES = 100_000
COLOR = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
EPS = 1e-9


class Rect(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _inside(self) -> Rect:
        if self.x + self.w > 1 + EPS or self.y + self.h > 1 + EPS:
            raise ValueError("rect extends past the page")
        return self


class Anchor(BaseModel):
    """Desktop `Anchor` (v1). Field order is the serialization order."""

    model_config = ConfigDict(extra="forbid", strict=True)

    v: int
    version: int = Field(ge=0)
    page: int = Field(ge=1)
    color: str = Field(pattern=COLOR)
    quote: str = Field(max_length=MAX_QUOTE_LEN)
    rects: list[Rect] = Field(min_length=1, max_length=MAX_RECTS)

    @field_validator("v")
    @classmethod
    def _v1(cls, v: int) -> int:
        if v != 1:
            raise ValueError("only anchor v1 is supported")
        return v

    def dumps(self) -> str:
        return json.dumps(self.model_dump(), separators=(",", ":"), ensure_ascii=False)


def _comment(value: str | None) -> str | None:
    if value is not None and len(value.replace("\x00", "").encode()) > MAX_COMMENT_BYTES:
        raise ValueError(f"comment is limited to {MAX_COMMENT_BYTES} bytes")
    return None if value is None else value.replace("\x00", "")


class AnnotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_id: str = Field(min_length=1)
    anchor: Anchor
    comment: str = ""
    project_id: int | None = None

    _c = field_validator("comment")(_comment)


class AnnotationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    comment: str | None = None
    color: str | None = Field(None, pattern=COLOR)
    # Required with `color`: the paper the annotation must belong to.
    source_id: str | None = Field(None, min_length=1)

    _c = field_validator("comment")(_comment)

    @model_validator(mode="after")
    def _some(self) -> AnnotationUpdate:
        if self.comment is None and self.color is None:
            raise ValueError("comment or color is required")
        if self.color is not None and self.source_id is None:
            raise ValueError("source_id is required to change the color")
        return self


async def _create(request: Request, source_id: str, anchor: str, comment: str, project_id):
    args = ["annotation", "create", f"--comment={comment}"]
    if project_id is not None:
        args.append(f"--project-id={project_id}")
    return await run(request, [*args, "--", ident(source_id, "paper id"), anchor])


@router.get("/annotations")
async def list_annotations(request: Request, paper: str | None = None, project: int | None = None):
    args = ["annotation", "list"]
    if paper is not None:
        args.append(f"--paper-id={ident(paper, 'paper id')}")
    if project is not None:
        args.append(f"--project-id={project}")
    return await run(request, args)


@router.post("/annotations")
async def create_annotation(request: Request, body: AnnotationCreate):
    return await _create(
        request, body.source_id, body.anchor.dumps(), body.comment, body.project_id
    )


@router.patch("/annotations/{annotation_id}")
async def update_annotation(request: Request, annotation_id: int, body: AnnotationUpdate):
    """Comment-only edits update in place. A color change creates the replacement
    first, so a failed delete leaves a duplicate rather than losing the highlight;
    the response then carries the new `id`."""
    if body.color is None:
        return await run(
            request,
            ["annotation", "update", f"--comment={body.comment}", "--", str(annotation_id)],
        )
    sid = ident(body.source_id or "", "paper id")
    listed = await run(request, ["annotation", "list", f"--paper-id={sid}"])
    current = next(
        (a for a in listed or [] if isinstance(a, dict) and a.get("id") == annotation_id), None
    )
    if current is None:
        raise HTTPException(status_code=404, detail=f"Annotation {annotation_id} not found")
    try:
        anchor = Anchor.model_validate_json(str(current.get("anchor") or ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail="annotation has no valid highlight") from e
    anchor.color = body.color
    comment = body.comment if body.comment is not None else str(current.get("comment") or "")
    created = await _create(request, sid, anchor.dumps(), comment, current.get("project_id"))
    try:
        await run(request, ["annotation", "delete", "--", str(annotation_id)])
    except CLIError as e:
        if e.status != 404:
            raise
    return {"id": created.get("id"), "replaced": annotation_id}


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(request: Request, annotation_id: int):
    return await run(request, ["annotation", "delete", "--", str(annotation_id)])
