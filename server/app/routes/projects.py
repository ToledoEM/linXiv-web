"""Projects (`linxiv project ...`).

Option values go as `--opt=value` so a description or tag starting with `-`
can't be read as a flag; the project name/id still follow `--`.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.background import BackgroundTask

from ..cli import CLIError
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


class PaperIds(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_ids: list[str] = Field(min_length=1, max_length=1000)


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


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: int):
    return await run(request, ["project", "get", "--", str(project_id)])


@router.get("/projects/{project_id}/papers")
async def project_papers(request: Request, project_id: int):
    """Library rows for the project's papers, in project order. The CLI has no
    membership filter on `list`, so the full listing is filtered here; trashed
    papers drop out because `list` omits them."""
    project = await run(request, ["project", "get", "--", str(project_id)])
    papers = await run(request, ["list"])
    by_id = {p.get("source_id"): p for p in papers} if isinstance(papers, list) else {}
    return [by_id[s] for s in project.get("source_ids", []) if s in by_id]


@router.post("/projects/{project_id}/papers")
async def add_papers(request: Request, project_id: int, body: PaperIds):
    """`project add-papers`: answers 200 with `added` and `failed` lists, even
    when some (or all) ids are unknown."""
    ids = [ident(s, "paper id") for s in body.source_ids]
    return await run(request, ["project", "add-papers", "--", str(project_id), *ids])


@router.delete("/projects/{project_id}/papers/{source_id:path}")
async def remove_paper(request: Request, project_id: int, source_id: str):
    return await run(
        request, ["project", "remove-paper", "--", str(project_id), ident(source_id, "paper id")]
    )


# format -> (CLI subcommand, file extension, media type)
EXPORTS = {
    "lxproj": ("export", ".lxproj", "application/zip"),
    "bibtex": ("export-bibtex", ".bib", "application/x-bibtex"),
    "obsidian": ("export-obsidian", ".md", "text/markdown"),
    "zotero": ("export-zotero", ".json", "application/json"),
}


def _slug(name: str, project_id: int) -> str:
    """Download file name, as linXiv desktop's slugify (src/api/exportImport.ts)."""
    stripped = re.sub(r"\s+", "_", re.sub(r'[:/\\*?"<>|]', "", name)).lower()
    return stripped or f"project-{project_id}"


@router.get("/projects/{project_id}/export")
async def export_project(
    request: Request,
    project_id: int,
    format: Literal["lxproj", "bibtex", "obsidian", "zotero"] = "lxproj",
    pdfs: bool = False,
):
    """The CLI writes the export into a private temp dir; the file is sent as a
    download and the dir removed once the response is done. `pdfs` bundles
    saved PDFs into the .lxproj archive."""
    sub, ext, media = EXPORTS[format]
    project = await run(request, ["project", "get", "--", str(project_id)])
    tmp = Path(tempfile.mkdtemp(prefix="lxw-export-"))
    try:
        args = ["project", sub]
        if format == "lxproj" and pdfs:
            args.append("--pdfs")
        out = await run(
            request, [*args, "--", str(project_id), str(tmp / f"export{ext}")], long=True
        )
        path = Path(str(out.get("path", ""))).resolve() if isinstance(out, dict) else None
        if not path or not path.is_file() or not path.is_relative_to(tmp.resolve()):
            raise CLIError(502, "linxiv export wrote no file")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return FileResponse(
        path,
        media_type=media,
        filename=_slug(str(project.get("name", "")), project_id) + ext,
        background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True),
    )


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
