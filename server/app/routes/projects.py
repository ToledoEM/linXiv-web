"""Projects (`linxiv project ...`).

Option values go as `--opt=value` so a description or tag starting with `-`
can't be read as a flag; the project name/id still follow `--`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import ident, run

router = APIRouter(prefix="/api", tags=["projects"])

# linxiv parses any hex string as a number ("#abc" becomes "#000abc"), so only
# the full #rrggbb form is accepted. The CLI can set a color but not clear it.
COLOR = r"^#[0-9a-fA-F]{6}$"
Tag = Annotated[str, Field(min_length=1, max_length=100)]


def _clean_tags(tags: list[str] | None) -> list[str] | None:
    if tags is None:
        return None
    cleaned = [t.strip() for t in tags]
    for t in cleaned:
        if not t or any(ord(c) < 32 or ord(c) == 127 for c in t):
            raise ValueError("invalid tag")
    return cleaned


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=10_000)
    color_hex: str | None = Field(None, pattern=COLOR)
    project_tags: list[Tag] = Field(default_factory=list, max_length=50)

    _tags = field_validator("project_tags")(_clean_tags)


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=10_000)
    color_hex: str | None = Field(None, pattern=COLOR)
    project_tags: list[Tag] | None = Field(None, max_length=50)

    _tags = field_validator("project_tags")(_clean_tags)


def _desc(value: str) -> str:
    # Descriptions are free text; only NUL can't travel in an argv.
    return value.replace("\x00", "")


@router.get("/projects")
async def list_projects(request: Request, status: Literal["active", "archived"] = "active"):
    return await run(request, ["project", "list", f"--status={status}"])


@router.post("/projects")
async def create_project(request: Request, body: ProjectCreate):
    args = ["project", "create", f"--description={_desc(body.description)}"]
    if body.color_hex:
        args.append(f"--color={body.color_hex}")
    args += [f"--tags={t}" for t in body.project_tags]
    return await run(request, [*args, "--", ident(body.name, "name")])


@router.patch("/projects/{project_id}")
async def update_project(request: Request, project_id: int, body: ProjectUpdate):
    args = ["project", "update"]
    if body.name is not None:
        args.append(f"--name={ident(body.name, 'name')}")
    if body.description is not None:
        args.append(f"--description={_desc(body.description)}")
    if body.color_hex is not None:
        args.append(f"--color={body.color_hex}")
    if body.project_tags is not None:
        # Bare --tags clears; repeated --tags=x replaces the set.
        args += [f"--tags={t}" for t in body.project_tags] or ["--tags"]
    return await run(request, [*args, "--", str(project_id)])


@router.post("/projects/{project_id}/archive")
async def archive_project(request: Request, project_id: int):
    return await run(request, ["project", "archive", "--", str(project_id)])


@router.post("/projects/{project_id}/restore")
async def restore_project(request: Request, project_id: int):
    return await run(request, ["project", "restore", "--", str(project_id)])


@router.delete("/projects/{project_id}")
async def delete_project(request: Request, project_id: int):
    """Soft delete: the project moves to the trash."""
    return await run(request, ["project", "delete", "--", str(project_id)])
