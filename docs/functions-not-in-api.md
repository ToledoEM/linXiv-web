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
- **`POST /api/add`:** `routes/add.py` classifies the input (arXiv ID, DOI, publisher article link, PDF URL) on the server and then picks the CLI command. Publisher links (Nature, Springer, Wiley, ACS, APS, IOP, Science, PNAS and others) map to their DOI with the table from linXiv v0.7.0's `recognize.rs`, which only the linXiv app and `linxiv-headless` use. The publisher PDF is fetched on a best-effort basis: the server checks that the link returns a real PDF before `linxiv pdf download` stores it, because that command keeps whatever the link returns.
- **PDF full text:** `routes/sources.py` extracts a saved PDF's text with pypdf and stores it with `linxiv paper set-text` (linXiv v0.7.0). This works for one paper or as a job over every non-arXiv paper with a PDF. The CLI only fetches arXiv TeX source by itself.

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

These exist in linXiv, but only in the `linxiv-headless` HTTP API ([linXiv `docs/api.md`](https://github.com/linxiv-dev/linXiv/blob/main/docs/api.md)), not in the CLI or `linxiv-mcp` (checked against v0.7.0). linXiv-web would need either new upstream CLI commands or `linxiv-headless` as its backend. The headless server cannot share the library with the CLI, because linXiv allows one process per library.

| Feature | linxiv-headless route | linXiv-web today |
|---|---|---|
| Per-paper reading status | `GET /api/reading-status`, `PUT /api/reading-status/{sid}` | Not available |
| Link or unlink one paper and one author | `POST` / `DELETE /api/authors/{id}/papers/{pid}` | Merge whole authors only |
| Change a highlight's anchor or color in place | `PATCH /api/annotations/{id}` | A color change deletes the highlight and creates a new one |
| Clear a project's color | `PATCH /api/projects/{id}` with `color_hex: null` | Color can be set but not cleared |
| Saved search state and history shared with the app | `GET` / `POST /api/search/state`, `GET /api/search/history` | History is kept per browser |
| TeX diff between two versions of a paper | `GET /api/papers/{id}/full-text-diff` | Not available |
| Backups taken before schema upgrades | `GET /api/storage/pre-migration-backups` | Not listed |
