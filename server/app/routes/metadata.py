"""Edit a paper's metadata and look up candidate metadata to compare against.

Saving goes through `linxiv paper repair`, which overwrites title, authors,
published, summary, category, DOI, URL and tags together (an omitted option is
cleared), so the server always sends the full record and carries the paper's
current tags over. Journal ref, comment and categories are left untouched.

Lookups use the CLI for Crossref, arXiv and OpenAlex. PubMed isn't in the CLI,
so it is queried directly through NCBI E-utilities (a fixed public host).
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Annotated, Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..cli import CLIError
from .common import ident, run

router = APIRouter(prefix="/api", tags=["metadata"])

# One argv string is capped at 128 KiB on Linux.
MAX_TEXT_BYTES = 100_000
MAX_RESULTS = 5
NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_MAX_BYTES = 5 * 1024 * 1024
BIORXIV = "https://api.biorxiv.org"
BIORXIV_MAX_BYTES = 2 * 1024 * 1024
# bioRxiv and medRxiv share the 10.1101 DOI prefix; bioRxiv also uses 10.64898.
BIORXIV_SERVERS = ("biorxiv", "medrxiv")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
Author = Annotated[str, Field(min_length=1, max_length=500)]
_MONTHS = {
    m: i
    for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
    )
}


def _no_ctrl(value: str) -> str:
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("control characters are not allowed")
    return value


class MetadataIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=2000)
    authors: list[Author] = Field(min_length=1, max_length=2000)
    published: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    summary: str = ""
    category: str | None = Field(None, max_length=500)
    doi: str | None = Field(None, max_length=500)
    url: str | None = Field(None, max_length=2000)

    @field_validator("title", "category", "doi", "url")
    @classmethod
    def _single_line(cls, v: str | None) -> str | None:
        return None if v is None else _no_ctrl(v.strip())

    @field_validator("authors")
    @classmethod
    def _authors(cls, v: list[str]) -> list[str]:
        names = [_no_ctrl(a.strip()) for a in v]
        if not all(names):
            raise ValueError("author names must not be blank")
        return names

    @field_validator("summary")
    @classmethod
    def _summary(cls, v: str) -> str:
        v = v.replace("\x00", "").strip()
        if len(v.encode()) > MAX_TEXT_BYTES:
            raise ValueError(f"summary is limited to {MAX_TEXT_BYTES} bytes")
        return v


@router.put("/papers/{source_id:path}/metadata")
async def save_metadata(request: Request, source_id: str, body: MetadataIn):
    sid = ident(source_id, "paper id")
    if not body.title:
        raise HTTPException(status_code=400, detail="title must not be blank")
    paper = await run(request, ["paper", "get", "--", sid])
    tags = (paper.get("tags") or []) if isinstance(paper, dict) else []
    args = ["paper", "repair", f"--title={body.title}"]
    args += [f"--authors={a}" for a in body.authors]
    args += [f"--published={body.published}", f"--summary={body.summary}"]
    # Blank optional fields are left out, which clears them (a blank DOI is an error).
    for flag, value in (("category", body.category), ("doi", body.doi), ("url", body.url)):
        if value:
            args.append(f"--{flag}={value}")
    args += [f"--tags={t}" for t in tags]
    return await run(request, [*args, "--", sid])


# ---------------------------------------------------------------------------
# Lookup


def _candidate(**kw) -> dict:
    keys = ("source", "ref", "title", "authors", "published", "summary", "category", "doi", "url")
    return {k: kw.get(k) for k in keys}


def _clean_abstract(text: str | None) -> str:
    # Crossref abstracts arrive as JATS XML.
    return re.sub(r"\s*</?jats:[^>]*>\s*", " ", text or "").strip()


def _from_search(source: str, r: dict) -> dict:
    url = r.get("paper_url")
    doi = None
    if source == "crossref":
        doi = r.get("source_id")
    elif url and url.startswith("https://doi.org/"):
        doi = url.removeprefix("https://doi.org/")
    return _candidate(
        source=source,
        ref=r.get("entry_id") or r.get("source_id"),
        title=r.get("title"),
        authors=r.get("authors") or [],
        published=r.get("published"),
        summary=_clean_abstract(r.get("summary")),
        category=r.get("primary_category"),
        doi=doi,
        url=url,
    )


async def _search(request: Request, source: str, query: str) -> list[dict]:
    args = ["search", "--source", source, "--max", str(MAX_RESULTS), "--", ident(query, "query")]
    results = await run(request, args, long=True)
    return [_from_search(source, r) for r in results or [] if isinstance(r, dict)]


async def _crossref_doi(request: Request, doi: str) -> list[dict]:
    try:
        d = await run(request, ["doi", "resolve", "--", ident(doi, "DOI")], long=True)
    except CLIError as e:
        if e.status == 404:
            return []
        raise
    return [
        _candidate(
            source="crossref",
            ref=d.get("source_id"),
            title=d.get("title"),
            authors=d.get("authors") or [],
            published=d.get("published"),
            summary=_clean_abstract(d.get("summary")),
            category=d.get("category"),
            doi=d.get("doi"),
            url=d.get("url"),
        )
    ]


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20, headers={"User-Agent": "linxiv-web"})


async def _ncbi(path: str, params: dict) -> bytes:
    try:
        async with _http() as client:
            r = await client.get(f"{NCBI}/{path}", params={**params, "tool": "linxiv-web"})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"PubMed lookup failed: {e}") from e
    if r.status_code != 200 or len(r.content) > NCBI_MAX_BYTES:
        raise HTTPException(status_code=502, detail=f"PubMed lookup failed ({r.status_code})")
    return r.content


def _itertext(el: ET.Element | None) -> str:
    # Titles and abstracts may carry inline markup (<i>, <sup>...).
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def _pubmed_date(article: ET.Element) -> str | None:
    pub = article.find("Journal/JournalIssue/PubDate")
    if pub is None:
        return None
    year = pub.findtext("Year")
    month: str | int | None = pub.findtext("Month")
    day = pub.findtext("Day")
    if not year and (medline := pub.findtext("MedlineDate")):
        # e.g. "2015 May-Jun" or "2014-2015"
        parts = re.findall(r"[A-Za-z]+|\d{4}", medline)
        year = next((p for p in parts if p.isdigit()), None)
        month = next((p for p in parts if not p.isdigit()), None)
    if not year:
        return None
    if isinstance(month, str):
        month = int(month) if month.isdigit() else _MONTHS.get(month[:3].lower())
    m = month if isinstance(month, int) and 1 <= month <= 12 else 1
    d = int(day) if day and day.isdigit() and 1 <= int(day) <= 31 else 1
    return f"{year}-{m:02d}-{d:02d}"


def _pubmed_parse(xml: bytes) -> list[dict]:
    out = []
    for art in ET.fromstring(xml).iter("PubmedArticle"):
        cit = art.find("MedlineCitation")
        a = cit.find("Article") if cit is not None else None
        if cit is None or a is None:
            continue
        pmid = cit.findtext("PMID")
        title = _itertext(a.find("ArticleTitle"))
        # MEDLINE titles end with a period; drop it as Zotero does.
        if title.endswith(".") and not title.endswith(".."):
            title = title[:-1]
        authors = []
        for au in a.findall("AuthorList/Author"):
            name = au.findtext("CollectiveName") or " ".join(
                p for p in (au.findtext("ForeName"), au.findtext("LastName")) if p
            )
            if name.strip():
                authors.append(name.strip())
        parts = []
        for t in a.findall("Abstract/AbstractText"):
            text = _itertext(t)
            parts.append(f"{t.get('Label')}: {text}" if t.get("Label") else text)
        doi = next(
            (e.text for e in a.findall("ELocationID") if e.get("EIdType") == "doi" and e.text),
            None,
        ) or next(
            (
                e.text
                for e in art.findall("PubmedData/ArticleIdList/ArticleId")
                if e.get("IdType") == "doi" and e.text
            ),
            None,
        )
        out.append(
            _candidate(
                source="pubmed",
                ref=f"pubmed:{pmid}",
                title=title,
                authors=authors,
                published=_pubmed_date(a),
                summary="\n\n".join(parts),
                category=a.findtext("Journal/Title"),
                doi=doi,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            )
        )
    return out


async def _pubmed(term: str) -> list[dict]:
    found = await _ncbi(
        "esearch.fcgi", {"db": "pubmed", "retmode": "json", "retmax": MAX_RESULTS, "term": term}
    )
    try:
        ids = json.loads(found)["esearchresult"]["idlist"]
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(status_code=502, detail="PubMed lookup failed (bad reply)") from e
    if not ids:
        return []
    xml = await _ncbi("efetch.fcgi", {"db": "pubmed", "retmode": "xml", "id": ",".join(ids)})
    try:
        return _pubmed_parse(xml)
    except ET.ParseError as e:
        raise HTTPException(status_code=502, detail="PubMed lookup failed (bad XML)") from e


def _biorxiv_author(name: str) -> str:
    """bioRxiv lists authors as "Last, I. N."; the library stores "I. N. Last"."""
    last, _, first = name.partition(",")
    return f"{first.strip()} {last.strip()}".strip()


async def _biorxiv(doi: str) -> list[dict]:
    """Latest version of a bioRxiv/medRxiv preprint by DOI (the API has no title search)."""
    # "." / ".." segments would be normalized away by the URL layer, changing the API path.
    if not DOI_RE.match(doi) or any(seg in (".", "..") for seg in doi.split("/")):
        return []
    path = quote(doi, safe="/")
    async with _http() as client:
        for server in BIORXIV_SERVERS:
            try:
                r = await client.get(f"{BIORXIV}/details/{server}/{path}")
            except httpx.HTTPError as e:
                raise HTTPException(status_code=502, detail=f"bioRxiv lookup failed: {e}") from e
            if r.status_code != 200 or len(r.content) > BIORXIV_MAX_BYTES:
                raise HTTPException(
                    status_code=502, detail=f"bioRxiv lookup failed ({r.status_code})"
                )
            try:
                rows = [x for x in r.json().get("collection") or [] if isinstance(x, dict)]
            except ValueError as e:
                raise HTTPException(
                    status_code=502, detail="bioRxiv lookup failed (bad reply)"
                ) from e
            if not rows:
                continue
            rows.sort(
                key=lambda x: (
                    int(str(x.get("version") or 0)) if str(x.get("version") or "0").isdigit() else 0
                )
            )
            first, latest = rows[0], rows[-1]
            version = latest.get("version") or "1"
            authors = [a.strip() for a in str(latest.get("authors") or "").split(";") if a.strip()]
            return [
                _candidate(
                    source="biorxiv",
                    ref=f"{server}:{doi}v{version}",
                    title=(latest.get("title") or "").strip() or None,
                    authors=[_biorxiv_author(a) for a in authors],
                    # The first version's posting date, as arXiv's "published" is v1's.
                    published=first.get("date"),
                    summary=(latest.get("abstract") or "").strip() or None,
                    category=latest.get("category"),
                    doi=latest.get("doi") or doi,
                    url=f"https://www.{server}.org/content/{doi}v{version}",
                )
            ]
    return []


@router.get("/papers/{source_id:path}/lookup")
async def lookup(
    request: Request,
    source_id: str,
    source: Literal["crossref", "arxiv", "openalex", "pubmed", "biorxiv"] = "crossref",
):
    """Candidate metadata for a library paper. Matches by identifier when the
    paper has one the source understands (DOI, arXiv id), otherwise by title."""
    sid = ident(source_id, "paper id")
    paper = await run(request, ["paper", "get", "--", sid])
    doi = (paper.get("doi") or "").strip()
    title = (paper.get("title") or "").strip()
    arxiv_id = sid.removeprefix("arxiv:") if sid.startswith("arxiv:") else None

    if source == "crossref" and doi:
        return {"match": "doi", "candidates": await _crossref_doi(request, doi)}
    if source == "arxiv" and arxiv_id:
        return {"match": "arxiv", "candidates": await _search(request, "arxiv", f"id:{arxiv_id}")}
    if source == "biorxiv":
        if not doi:
            raise HTTPException(
                status_code=400,
                detail="bioRxiv/medRxiv lookup needs a DOI (the API has no title search)",
            )
        return {"match": "doi", "candidates": await _biorxiv(doi)}
    if source == "pubmed":
        # Not every DOI is indexed in PubMed; fall back to the title.
        if doi and (found := await _pubmed(f"{doi}[doi]")):
            return {"match": "doi", "candidates": found}
        return {"match": "title", "candidates": await _pubmed(f"{title}[title]")}
    if not title:
        raise HTTPException(status_code=400, detail="paper has no title to search by")
    return {"match": "title", "candidates": await _search(request, source, title)}
