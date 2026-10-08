# Functions not in the linxiv CLI

What the web server provides that the linxiv CLI does not.

Compares the `linxiv` CLI that the web server wraps with the web server code in `server/app/`. Not an exhaustive diff.

## Server-only code with no CLI command behind it

- **Auth:** `routes/auth.py` has login, setup, logout and "me", plus the remember-me option (`app/auth.py`).
- **Knowledge graph:** `routes/graph.py` builds the payload in Python, because the CLI has no graph command.
- **AI features:** `app/ai.py` and `routes/ai.py` call Gemini, OpenAI, Anthropic or a generic provider over `httpx`. They cover tag suggestions, summaries (saved as a note) and metadata cleanup, with write-only keys stored in settings.
- **MCP over HTTP at `/mcp`:** `app/mcp_bridge.py` and `routes/mcp.py` run `linxiv-mcp` as a subprocess per session. It has a bearer token that is shown once, stored as a sha256 hash under web-only `web_mcp_token_*` keys, and can be rotated or revoked. The tool profile is read-only or read+write.
- **Background full-text worker:** `app/fulltext_worker.py` runs as an asyncio task in the FastAPI lifespan. `routes/sources.py` exposes the job queue (`/jobs`, `/jobs/{id}/cancel`, `/sources/worker`, `/sources/pending`). The "Index now" button also goes through this.
- **PDF layout and folder moves:** `app/pdf_layout.py` and `app/pdf_text.py`. Files are moved and `PAPER_META.PDF_PATH` is written straight into SQLite, because the CLI has no command to set a PDF location.
- **Direct external calls:** PubMed via NCBI E-utilities (`routes/metadata.py`), and bioRxiv/medRxiv as a source (DOI-only, 2 MB cap).
- **`POST /api/add`:** `routes/add.py` classifies the input (arXiv ID, DOI, URL) on the server and then picks the CLI command.

## Server-side logic layered on CLI results

- **Author merge candidates:** `name_candidates` is computed on the server (exact full name, case-folded, minus ORCID matches and self). The CLI lacks this.
- **Author list filter:** the "hide single-paper authors" filter runs server-side, because the CLI has no flag for it.
- **ORCID checks:** format, `orcid.org` URL prefix stripped and check digit. The CLI stores any string.
- **Annotation anchors:** validated with strict pydantic and re-serialized to `{v,version,page,color,quote,rects}`. The CLI stores any string.
- **Library search:** local match plus `paper search` for queries of 3+ characters, merged. If the deep search fails, you get the plain hits plus an `X-Deep-Search-Error` header.
- **Project export:** one `GET /projects/{id}/export?format=…` that streams the file back and uses the linXiv desktop app's slugified filename.
- **Project import:** a stateless preview step, then a commit that re-uploads the file.
- **Upload endpoints:** bibtex, zotero and PDF import take uploads instead of host paths.

## Web UI features with no CLI or server counterpart

- Search history in localStorage, honoring the shared `search_history_enabled` and `_max` settings, plus a "Clear search history" button the linXiv desktop app lacks.
- Batch metadata edit, which reuses `GET …/lookup` and `PUT …/metadata` per paper, one at a time.
- Crossref search tab (the CLI supports it, the linXiv desktop app doesn't) and a Query Builder for arXiv.
- Zoom and density settings per browser.
- Upload and Trash sidebar toggles that exist only in the web app.
- Settings groups with `#id` deep links.

## Blocked on the CLI

- Per-paper reading status, needs an upstream `reading status` command.
- There is no per-paper author unlink or reassign, because the CLI has no link or unlink command.
