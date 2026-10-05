"""Paper notes (`linxiv note ...`), optionally scoped to a project.

Note text travels as one argv string, and Linux caps a single argument at
128 KiB, so title and content are limited by UTF-8 size below that.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import ident, run

router = APIRouter(prefix="/api", tags=["notes"])

MAX_TEXT_BYTES = 100_000


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.replace("\x00", "")
    if len(value.encode()) > MAX_TEXT_BYTES:
        raise ValueError(f"note text is limited to {MAX_TEXT_BYTES} bytes")
    return value


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_id: str = Field(min_length=1)
    title: str = ""
    content: str = ""
    project_id: int | None = None

    _text = field_validator("title", "content")(_text)


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str | None = None
    content: str | None = None

    _text = field_validator("title", "content")(_text)

    @model_validator(mode="after")
    def _some(self) -> NoteUpdate:
        if self.title is None and self.content is None:
            raise ValueError("title or content is required")
        return self


@router.get("/notes")
async def list_notes(request: Request, paper: str | None = None, project: int | None = None):
    args = ["note", "list"]
    if paper is not None:
        args.append(f"--paper-id={ident(paper, 'paper id')}")
    if project is not None:
        args.append(f"--project-id={project}")
    return await run(request, args)


@router.post("/notes")
async def create_note(request: Request, body: NoteCreate):
    if not body.title.strip() and not body.content.strip():
        raise HTTPException(status_code=400, detail="note needs a title or content")
    args = ["note", "create", f"--title={body.title}"]
    if body.project_id is not None:
        args.append(f"--project-id={body.project_id}")
    return await run(request, [*args, "--", ident(body.source_id, "paper id"), body.content])


@router.patch("/notes/{note_id}")
async def update_note(request: Request, note_id: int, body: NoteUpdate):
    args = ["note", "update"]
    if body.title is not None:
        args.append(f"--title={body.title}")
    if body.content is not None:
        args.append(f"--content={body.content}")
    return await run(request, [*args, "--", str(note_id)])


@router.delete("/notes/{note_id}")
async def delete_note(request: Request, note_id: int):
    """Permanent: notes have no trash."""
    return await run(request, ["note", "delete", "--", str(note_id)])
