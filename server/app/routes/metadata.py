"""Edit a paper's metadata and look up candidate metadata to compare against.

Saving goes through `linxiv paper repair`, which overwrites title, authors,
published, summary, category, DOI, URL and tags together (an omitted option is
cleared), so the server always sends the full record and carries the paper's
current tags over. Journal ref, comment and categories are left untouched.

Lookups use the CLI for Crossref, arXiv and OpenAlex. PubMed isn't in the CLI,
so it is queried directly through NCBI E-utilities (a fixed public host).

Every candidate also carries `bib`: the BibTeX fields linXiv does not store
(volume, pages, publisher, entry type...; app/bib_store.py), or null. The CLI
drops them, so Crossref and OpenAlex records are read directly from their
public APIs for these; PubMed, bioRxiv and arXiv carry them in what is already
fetched. Saving a candidate records its source (`metadata_source`) with them.
`by=filename` searches with the title in the PDF's file name instead of the
paper's own DOI or title, for imports whose PDF metadata is junk or points at
another paper.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal
from urllib.parse import quote

import httpx
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as safe_fromstring
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import bib_store
from ..cli import CLIError
from ..doi import clean_doi, doi_or_none, is_valid_doi
from ..pdf_name import pdf_file, title_from_file, year_from_file
from .common import ident, library, run
from .user_settings import disabled_sources, ncbi_api_key

router = APIRouter(prefix="/api", tags=["metadata"])
# A library CLI call with the timeout already chosen: argv -> parsed JSON.
Call = Callable[[list[str]], Awaitable[Any]]

# One argv string is capped at 128 KiB on Linux.
MAX_TEXT_BYTES = 100_000
MAX_RESULTS = 5
# `paper repair` declares --authors as required, so a paper saved without authors
# is stored under this placeholder rather than rejected.
UNKNOWN_AUTHOR = "Unknown"
NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_MAX_BYTES = 5 * 1024 * 1024
BIORXIV = "https://api.biorxiv.org"
BIORXIV_MAX_BYTES = 2 * 1024 * 1024
# bioRxiv and medRxiv share the 10.1101 DOI prefix; bioRxiv also uses 10.64898.
BIORXIV_SERVERS = ("biorxiv", "medrxiv")
# The preprint server IS the journal; the API's subject ("molecular biology") is not.
BIORXIV_JOURNAL = {"biorxiv": "bioRxiv", "medrxiv": "medRxiv"}
BIORXIV_PUBLISHER = "Cold Spring Harbor Laboratory"
CROSSREF = "https://api.crossref.org"
OPENALEX = "https://api.openalex.org"
WORK_MAX_BYTES = 2 * 1024 * 1024
OPENALEX_ID = re.compile(r"^(?:openalex:|https://openalex\.org/)?(W\d{1,12})$")
# Crossref / OpenAlex work type -> BibTeX entry type.
CROSSREF_TYPES = {
    "journal-article": "article",
    "article": "article",
    "review": "article",
    "letter": "article",
    "editorial": "article",
    "proceedings-article": "inproceedings",
    "proceedings": "proceedings",
    "book": "book",
    "monograph": "book",
    "edited-book": "book",
    "reference-book": "book",
    "book-chapter": "incollection",
    "book-section": "incollection",
    "book-part": "incollection",
    "posted-content": "misc",
    "preprint": "misc",
    "dataset": "misc",
    "report": "techreport",
    "dissertation": "phdthesis",
    "standard": "manual",
}
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
Author = Annotated[str, Field(min_length=1, max_length=500)]
Tag = Annotated[str, Field(min_length=1, max_length=512)]
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


class MetadataSourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source: Literal[bib_store.SOURCES]  # type: ignore[valid-type]
    ref: str | None = Field(None, max_length=2000)


class MetadataIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=2000)
    authors: list[Author] = Field(default_factory=list, max_length=2000)
    published: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    summary: str = ""
    category: str | None = Field(None, max_length=500)
    doi: str | None = Field(None, max_length=500)
    url: str | None = Field(None, max_length=2000)
    # The paper's current tags, when the client already holds them (batch edit):
    # saves the `paper get` round trip. Omitted = read them from the CLI.
    tags: list[Tag] | None = Field(None, max_length=2000)
    # BibTeX fields linXiv does not store (app/bib_store.py); only the keys sent
    # change. Omitted = left as stored.
    bib: dict[str, str | None] | None = None
    # Only fill BibTeX fields that are still null (batch edit, when the
    # candidate's fields are read here and could not be shown for review).
    bib_fill_only: bool = False
    # The candidate these values came from; omitted (a hand edit) keeps the
    # recorded source.
    metadata_source: MetadataSourceIn | None = None

    @field_validator("title", "category", "doi", "url")
    @classmethod
    def _single_line(cls, v: str | None) -> str | None:
        return None if v is None else _no_ctrl(v.strip())

    @field_validator("doi")
    @classmethod
    def _doi(cls, v: str | None) -> str | None:
        doi = clean_doi(v)
        if doi and not is_valid_doi(doi):
            raise ValueError(f"not a valid DOI: {doi}")
        return doi or None

    @field_validator("authors")
    @classmethod
    def _authors(cls, v: list[str]) -> list[str]:
        names = [_no_ctrl(a.strip()) for a in v]
        if not all(names):
            raise ValueError("author names must not be blank")
        return names

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        tags = [_no_ctrl(t.strip()) for t in v]
        if not all(tags):
            raise ValueError("tags must not be blank")
        return tags

    @field_validator("bib")
    @classmethod
    def _bib(cls, v: dict[str, str | None] | None) -> dict[str, str | None] | None:
        if v is None:
            return None
        bad = [k for k in v if k not in bib_store.BIB_FIELDS]
        if bad:
            raise ValueError(f"unknown BibTeX field: {', '.join(bad)}")
        for value in v.values():
            if value is not None:
                if len(value) > bib_store.MAX_VALUE:
                    raise ValueError(
                        f"BibTeX values are limited to {bib_store.MAX_VALUE} characters"
                    )
                _no_ctrl(value)
        return v

    @field_validator("summary")
    @classmethod
    def _summary(cls, v: str) -> str:
        v = v.replace("\x00", "").strip()
        if len(v.encode()) > MAX_TEXT_BYTES:
            raise ValueError(f"summary is limited to {MAX_TEXT_BYTES} bytes")
        return v


@router.put("/papers/{source_id:path}/metadata")
async def save_metadata(request: Request, source_id: str, body: MetadataIn):
    """Papers may be saved without authors; `paper repair` requires the flag, so an
    empty list is sent as a single `UNKNOWN_AUTHOR` placeholder."""
    sid = ident(source_id, "paper id")
    if not body.title:
        raise HTTPException(status_code=400, detail="title must not be blank")
    tags = body.tags
    if tags is None:
        paper = await run(request, ["paper", "get", "--", sid])
        tags = (paper.get("tags") or []) if isinstance(paper, dict) else []
    args = ["paper", "repair", f"--title={body.title}"]
    args += [f"--authors={a}" for a in (body.authors or [UNKNOWN_AUTHOR])]
    args += [f"--published={body.published}", f"--summary={body.summary}"]
    # Blank optional fields are left out, which clears them (a blank DOI is an error).
    for flag, value in (("category", body.category), ("doi", body.doi), ("url", body.url)):
        if value:
            args.append(f"--{flag}={value}")
    args += [f"--tags={t}" for t in tags]
    out = await run(request, [*args, "--", sid])
    await _store_bib(request, sid, body)
    return out


async def _store_bib(request: Request, sid: str, body: MetadataIn) -> None:
    """Keep the candidate's BibTeX fields and source next to the saved record.
    A Crossref or OpenAlex candidate from a title search carries no fields:
    they are read here, by its DOI / work id, once it is picked."""
    src = body.metadata_source
    bib = body.bib
    if src and bib is None:
        if src.source == "crossref" and body.doi:
            bib = await crossref_bib(body.doi, await contact(request, "CROSSREF_MAILTO"))
        elif src.source == "openalex" and src.ref:
            work = await openalex_work(src.ref, await contact(request, "OPENALEX_MAILTO"))
            bib = work.get("bib") if work else None
        elif src.source == "arxiv" and sid.startswith("arxiv:"):
            bib = arxiv_bib(sid, body.category, body.published)
    if bib is None and src is None:
        return
    # Explicit nulls in `bib` clear those fields; absent keys stay as stored.
    cleared = [k for k, v in (bib or {}).items() if v is None or not str(v).strip()]
    lib = library(request)
    source, ref = (src.source, src.ref) if src else (None, None)
    if body.bib_fill_only:
        # Stored values stay; the saved record's source is still recorded.
        await bib_store.upsert(lib, sid, bib, overwrite=False)
        await bib_store.upsert(lib, sid, None, source, ref, overwrite=True)
        return
    if cleared:
        await bib_store.clear(lib, sid, cleared)
    await bib_store.upsert(lib, sid, bib, source, ref, overwrite=True)


# ---------------------------------------------------------------------------
# Lookup


def _candidate(**kw) -> dict:
    keys = ("source", "ref", "title", "authors", "published", "summary", "category", "doi", "url")
    out = {k: kw.get(k) for k in keys}
    out["doi"] = doi_or_none(out["doi"])
    out["bib"] = bib_store.clean(kw.get("bib")) or None
    return out


async def contact(request: Request, key: str) -> str:
    """The contact address sent to Crossref / OpenAlex (env var first, as linXiv)."""
    if env := os.environ.get(key, "").strip():
        return env
    try:
        stored = await run(request, ["settings", "get"])
    except CLIError:
        return ""
    value = stored.get(key) if isinstance(stored, dict) else None
    return value.strip() if isinstance(value, str) else ""


def mailto_from(stored: dict, key: str) -> str:
    if env := os.environ.get(key, "").strip():
        return env
    value = stored.get(key) if isinstance(stored, dict) else None
    return value.strip() if isinstance(value, str) else ""


def _month_of(date: object) -> str | None:
    """Month of an ISO date, only when the date has one (YYYY-MM...)."""
    text = str(date or "")
    return bib_store.month(text[5:7]) if re.match(r"^\d{4}-\d{2}", text) else None


def arxiv_bib(ref: str | None, category: str | None, published: str | None) -> dict:
    """arXiv's BibTeX keys, from what the record already holds."""
    arxiv_id = re.sub(r"^(?:arxiv:|https?://arxiv\.org/(?:abs|pdf)/)", "", str(ref or ""))
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id.removesuffix(".pdf"))
    out = {"entry_type": "misc", "archive_prefix": "arXiv", "month": _month_of(published)}
    if arxiv_id:
        out["eprint"] = arxiv_id
    if category:
        out["primary_class"] = category
    return bib_store.clean(out)


async def _get_json(url: str, params: dict | None = None) -> dict | None:
    """GET a public metadata API; None on any failure (the extra fields are
    optional, a lookup never fails for them)."""
    try:
        async with _http() as client:
            r = await client.get(url, params=params or None)
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or len(r.content) > WORK_MAX_BYTES:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _first(value: object) -> str | None:
    if isinstance(value, list):
        value = next((v for v in value if v), None)
    return str(value).strip() if value not in (None, "") else None


def _person(p: object) -> str:
    if not isinstance(p, dict):
        return ""
    return " ".join(x for x in (p.get("given"), p.get("family")) if x) or str(p.get("name") or "")


def crossref_fields(msg: dict | None) -> dict:
    """BibTeX fields from a Crossref `/works/{doi}` message."""
    if not isinstance(msg, dict):
        return {}
    kind = CROSSREF_TYPES.get(str(msg.get("type") or ""), "misc" if msg.get("type") else None)
    container = _first(msg.get("container-title"))
    date = next(
        (
            msg[k]["date-parts"][0]
            for k in ("published-print", "published-online", "issued", "published")
            if isinstance(msg.get(k), dict)
            and isinstance(msg[k].get("date-parts"), list)
            and msg[k]["date-parts"]
            and isinstance(msg[k]["date-parts"][0], list)
        ),
        [],
    )
    institution = _first(
        [i.get("name") for i in msg.get("institution") or [] if isinstance(i, dict)]
    )
    editors = [n for n in (_person(e) for e in msg.get("editor") or []) if n]
    out = {
        "entry_type": kind,
        "volume": msg.get("volume"),
        "number": msg.get("issue"),
        "pages": str(msg.get("page") or "").replace("-", "--") or None,
        "publisher": msg.get("publisher"),
        "address": msg.get("publisher-location"),
        "issn": _first(msg.get("ISSN")),
        "isbn": _first(msg.get("ISBN")),
        "edition": msg.get("edition-number"),
        "editor": " and ".join(editors) or None,
        "month": date[1] if len(date) > 1 else None,
    }
    if kind in ("inproceedings", "incollection"):
        out["booktitle"] = container
    elif kind == "book":
        out["series"] = container
    if kind == "phdthesis":
        out["school"] = institution
    elif kind == "techreport":
        out["institution"] = institution or msg.get("publisher")
    return bib_store.clean(out)


async def crossref_bib(doi: str | None, mailto: str = "") -> dict | None:
    doi = doi_or_none(doi)
    if not doi:
        return None
    params = {"mailto": mailto} if mailto else None
    data = await _get_json(f"{CROSSREF}/works/{quote(doi, safe='/')}", params)
    return crossref_fields(data.get("message")) if data else None


def openalex_fields(work: dict | None) -> dict:
    """BibTeX fields from an OpenAlex work."""
    if not isinstance(work, dict):
        return {}
    loc = work.get("primary_location") if isinstance(work.get("primary_location"), dict) else {}
    src = loc.get("source") if isinstance(loc.get("source"), dict) else {}
    biblio = work.get("biblio") if isinstance(work.get("biblio"), dict) else {}
    kind = CROSSREF_TYPES.get(str(work.get("type_crossref") or work.get("type") or ""))
    if src.get("type") == "conference" and kind in (None, "article"):
        kind = "inproceedings"
    first, last = biblio.get("first_page"), biblio.get("last_page")
    pages = f"{first}--{last}" if first and last and first != last else first
    out = {
        "entry_type": kind,
        "volume": biblio.get("volume"),
        "number": biblio.get("issue"),
        "pages": pages,
        "publisher": src.get("host_organization_name"),
        "issn": src.get("issn_l") or _first(src.get("issn")),
        "month": _month_of(work.get("publication_date")),
    }
    if kind in ("inproceedings", "incollection"):
        out["booktitle"] = src.get("display_name")
    return bib_store.clean(out)


def _openalex_abstract(index: object) -> str | None:
    if not isinstance(index, dict):
        return None
    words: dict[int, str] = {}
    for word, places in index.items():
        for i in places if isinstance(places, list) else []:
            if isinstance(i, int):
                words[i] = word
    return " ".join(words[i] for i in sorted(words)) or None


async def openalex_work(ref: str, mailto: str = "") -> dict | None:
    """The OpenAlex work `ref` (openalex:W..., W... or its URL) as a candidate."""
    m = OPENALEX_ID.match(str(ref or "").strip())
    if not m:
        return None
    params = {"mailto": mailto} if mailto else None
    work = await _get_json(f"{OPENALEX}/works/{m.group(1)}", params)
    if not work:
        return None
    loc = work.get("primary_location") if isinstance(work.get("primary_location"), dict) else {}
    src = loc.get("source") if isinstance(loc.get("source"), dict) else {}
    authors = [
        str(a["author"].get("display_name")).strip()
        for a in work.get("authorships") or []
        if isinstance(a, dict)
        and isinstance(a.get("author"), dict)
        and a["author"].get("display_name")
    ]
    return _candidate(
        source="openalex",
        ref=f"openalex:{m.group(1)}",
        title=work.get("title") or work.get("display_name"),
        authors=authors,
        published=work.get("publication_date"),
        summary=_openalex_abstract(work.get("abstract_inverted_index")),
        category=src.get("display_name"),
        doi=str(work.get("doi") or "").removeprefix("https://doi.org/") or None,
        url=loc.get("landing_page_url") or work.get("doi"),
        bib=openalex_fields(work),
    )


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
    ref = r.get("entry_id") or r.get("source_id")
    bib = (
        arxiv_bib(ref, r.get("primary_category"), r.get("published")) if source == "arxiv" else None
    )
    return _candidate(
        source=source,
        ref=ref,
        title=r.get("title"),
        authors=r.get("authors") or [],
        published=r.get("published"),
        summary=_clean_abstract(r.get("summary")),
        category=r.get("primary_category"),
        doi=doi,
        url=url,
        bib=bib,
    )


def cli_call(request: Request) -> Call:
    """The library's CLI with the long timeout (lookups reach outside services)."""
    return lambda args: run(request, args, long=True)


async def _search(call: Call, source: str, query: str) -> list[dict]:
    args = ["search", "--source", source, "--max", str(MAX_RESULTS), "--", ident(query, "query")]
    results = await call(args)
    return [_from_search(source, r) for r in results or [] if isinstance(r, dict)]


async def _crossref_doi(call: Call, doi: str, mailto: str = "") -> list[dict]:
    try:
        d = await call(["doi", "resolve", "--", ident(doi, "DOI")])
    except CLIError as e:
        if e.status == 404:
            return []
        raise
    bib = await crossref_bib(d.get("doi") or doi, mailto)
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
            bib=bib,
        )
    ]


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20, headers={"User-Agent": "linxiv-web"})


async def _ncbi(path: str, params: dict, api_key: str = "") -> bytes:
    query = {**params, "tool": "linxiv-web"}
    if api_key:
        query["api_key"] = api_key
    try:
        async with _http() as client:
            r = await client.get(f"{NCBI}/{path}", params=query)
    except httpx.HTTPError as e:
        # Exception type only: the request URL (with the api_key) must not leak.
        raise HTTPException(
            status_code=502, detail=f"PubMed lookup failed ({type(e).__name__})"
        ) from e
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
    for art in safe_fromstring(xml).iter("PubmedArticle"):
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
        issue = a.find("Journal/JournalIssue")
        pub_month = issue.findtext("PubDate/Month") if issue is not None else None
        if not pub_month and issue is not None and (md := issue.findtext("PubDate/MedlineDate")):
            pub_month = next(iter(re.findall(r"[A-Za-z]{3,}", md)), None)
        bib = {
            "entry_type": "article",
            "volume": issue.findtext("Volume") if issue is not None else None,
            "number": issue.findtext("Issue") if issue is not None else None,
            "pages": (a.findtext("Pagination/MedlinePgn") or "").replace("-", "--") or None,
            "issn": a.findtext("Journal/ISSN"),
            "month": pub_month,
        }
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
                bib=bib,
            )
        )
    return out


async def _pubmed(term: str, api_key: str = "") -> list[dict]:
    found = await _ncbi(
        "esearch.fcgi",
        {"db": "pubmed", "retmode": "json", "retmax": MAX_RESULTS, "term": term},
        api_key,
    )
    try:
        ids = json.loads(found)["esearchresult"]["idlist"]
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(status_code=502, detail="PubMed lookup failed (bad reply)") from e
    if not ids:
        return []
    xml = await _ncbi(
        "efetch.fcgi", {"db": "pubmed", "retmode": "xml", "id": ",".join(ids)}, api_key
    )
    try:
        return _pubmed_parse(xml)
    except (ET.ParseError, DefusedXmlException) as e:
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
                    category=BIORXIV_JOURNAL[server],
                    doi=latest.get("doi") or doi,
                    url=f"https://www.{server}.org/content/{doi}v{version}",
                    bib={
                        "entry_type": "article",
                        "publisher": BIORXIV_PUBLISHER,
                        "month": _month_of(first.get("date")),
                        "note": "Preprint",
                    },
                )
            ]
    return []


async def require_source(request: Request, source: str, stored: dict | None = None) -> None:
    """400 when the lookup source is switched off in Settings."""
    if stored is None:
        try:
            stored = await run(request, ["settings", "get"])
        except CLIError:
            stored = {}  # unreadable settings: nothing is switched off
    if source in disabled_sources(stored):
        raise HTTPException(status_code=400, detail=f"Lookup source {source} is switched off")


async def _ncbi_key(request: Request) -> str:
    try:
        stored = await run(request, ["settings", "get"])
    except CLIError:
        stored = {}  # no key is not a reason to fail the lookup
    key, _ = ncbi_api_key(stored)
    return key or ""


async def _by_filename(request: Request, source: str, paper: dict) -> dict:
    """Search by the title in the PDF's file name, ignoring the stored DOI (it may
    belong to another paper). The last candidate is the file name itself: its
    title, and its year folder as the date, for papers no source can find."""
    lib = library(request)
    rel = pdf_file(paper.get("pdf_path"), [str(lib.data_dir / "pdfs"), str(lib.pdf_dir)])
    title = title_from_file(rel)
    if not title:
        raise HTTPException(status_code=400, detail="the PDF file name has no title to search by")
    if source == "biorxiv":
        raise HTTPException(
            status_code=400,
            detail="bioRxiv/medRxiv lookup needs a DOI (the API has no title search)",
        )
    if source == "pubmed":
        found = await _pubmed(f"{title}[title]", await _ncbi_key(request))
    else:
        found = await _search(cli_call(request), source, title)
    year = year_from_file(rel)
    published = paper.get("published")
    if year and not str(published or "").startswith(str(year)):
        published = f"{year}-01-01"
    found.append(
        _candidate(
            source="filename",
            ref=rel,
            title=title,
            authors=paper.get("authors") or [],
            published=published,
            summary=paper.get("summary"),
            category=paper.get("category"),
            doi=paper.get("doi"),
            url=paper.get("url"),
        )
    )
    return {"match": "filename", "candidates": found}


@router.get("/papers/{source_id:path}/lookup")
async def lookup(
    request: Request,
    source_id: str,
    source: Literal["crossref", "arxiv", "openalex", "pubmed", "biorxiv"] = "crossref",
    by: Literal["auto", "filename"] = "auto",
):
    """Candidate metadata for a library paper. Matches by identifier when the
    paper has one the source understands (DOI, arXiv id), otherwise by title.
    `by=filename` searches by the title in the PDF's file name instead."""
    sid = ident(source_id, "paper id")
    await require_source(request, source)
    paper = await run(request, ["paper", "get", "--", sid])
    if by == "filename":
        return await _by_filename(request, source, paper)
    doi = doi_or_none(paper.get("doi")) or ""
    title = (paper.get("title") or "").strip()
    arxiv_id = sid.removeprefix("arxiv:") if sid.startswith("arxiv:") else None

    if source == "crossref" and doi:
        mailto = await contact(request, "CROSSREF_MAILTO")
        return {"match": "doi", "candidates": await _crossref_doi(cli_call(request), doi, mailto)}
    if source == "arxiv" and arxiv_id:
        found = await _search(cli_call(request), "arxiv", f"id:{arxiv_id}")
        return {"match": "arxiv", "candidates": found}
    if source == "biorxiv":
        if not doi:
            raise HTTPException(
                status_code=400,
                detail="bioRxiv/medRxiv lookup needs a DOI (the API has no title search)",
            )
        return {"match": "doi", "candidates": await _biorxiv(doi)}
    if source == "pubmed":
        key = await _ncbi_key(request)
        # Not every DOI is indexed in PubMed; fall back to the title.
        if doi and (found := await _pubmed(f"{doi}[doi]", key)):
            return {"match": "doi", "candidates": found}
        return {"match": "title", "candidates": await _pubmed(f"{title}[title]", key)}
    if not title:
        raise HTTPException(status_code=400, detail="paper has no title to search by")
    return {"match": "title", "candidates": await _search(cli_call(request), source, title)}


# ---------------------------------------------------------------------------
# Identifier match (maintenance: complete metadata of new papers)

# bioRxiv/medRxiv DOI prefixes: their API only knows these.
BIORXIV_PREFIXES = ("10.1101/", "10.64898/")
# Sources that can look a paper up by its exact identifier. OpenAlex is not one:
# the CLI only searches it by text or fetches it by OpenAlex work id.
ID_SOURCES = ("arxiv", "biorxiv", "crossref", "pubmed")


async def match_by_id(
    call: Call, paper: dict, sources: list[str], ncbi_key: str = "", stored: dict | None = None
) -> dict | None:
    """The record a source holds under this paper's own arXiv id or DOI, or None.
    Never searches by title, so a hit is the same paper. `sources` are tried in
    order; each is asked only when it applies: arXiv for arXiv papers, bioRxiv
    for bioRxiv/medRxiv DOIs, Crossref and PubMed for any DOI."""
    sid = str(paper.get("source_id") or "")
    arxiv_id = sid.removeprefix("arxiv:") if sid.startswith("arxiv:") else None
    doi = doi_or_none(paper.get("doi")) or ""
    for source in sources:
        if source == "arxiv" and arxiv_id:
            found = await _search(call, "arxiv", f"id:{arxiv_id}")
            hit = next((c for c in found if (c.get("ref") or "").endswith(arxiv_id)), None)
        elif source == "biorxiv" and doi and doi.startswith(BIORXIV_PREFIXES):
            found = await _biorxiv(doi)
            hit = next((c for c in found if (c.get("doi") or "").lower() == doi.lower()), None)
        elif source in ("crossref", "pubmed") and doi:
            if source == "crossref":
                found = await _crossref_doi(call, doi, mailto_from(stored or {}, "CROSSREF_MAILTO"))
            else:
                found = await _pubmed(f"{doi}[doi]", ncbi_key)
            hit = next((c for c in found if (c.get("doi") or "").lower() == doi.lower()), None)
        else:
            continue
        if hit:
            return hit
    return None


def repair_args(sid: str, body: MetadataIn, tags: list[str]) -> list[str]:
    """`paper repair` argv for a full record (see save_metadata: omitted options
    are cleared, so every field and the current tags go along)."""
    args = ["paper", "repair", f"--title={body.title}"]
    args += [f"--authors={a}" for a in (body.authors or [UNKNOWN_AUTHOR])]
    args += [f"--published={body.published}", f"--summary={body.summary}"]
    for flag, value in (("category", body.category), ("doi", body.doi), ("url", body.url)):
        if value:
            args.append(f"--{flag}={value}")
    return [*args, *(f"--tags={t}" for t in tags), "--", sid]
