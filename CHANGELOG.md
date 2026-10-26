# Changelog

All notable changes to linXiv-web are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The version is `server/pyproject.toml` `version`; images are published to `ghcr.io/toledoem/linxiv-web:<version>`.

## [Unreleased]

### Added
- Live demo link in the README and the documentation home page.
- Multi-user mode, off by default. Settings → **Server Admin** turns it on: you pick a username and keep the server password, and your library stays as it is. The login page then asks for a username. Turning it off again lets only the owner log in (password only) and keeps every account and library for later.
- Settings → Server Admin → **Users** (admins only): add accounts (user or admin), rename them, set a role or a new password, delete them. Each account gets its own library with its own PDFs and settings (AI keys, contacts, feeds, lookup). Deleting an account keeps its library folder on disk and shows where it is. No two accounts may share a password, the last admin can't be demoted or deleted, and the owner always stays admin.
- Shared library: a separate library everyone can read and only admins change. The sidebar switches between **My library** and **Shared library**; admins fill it with the usual Add, Upload, Search and Feed pages. Users see it read only and use **Copy to my library** (Library selection bar or paper page) to copy papers with their PDFs into their own library; papers they already have keep their stored metadata.
- `python -m app reset-password --user <name>` resets one account's password and logs that account out.
- `LINXIV_WEB_LIBRARIES_PDF_DIR`: keep the PDFs of the shared and per-user libraries on another disk (`<dir>/<library>`); it must not be inside `LINXIV_WEB_PDF_DIR`.
- API: `GET/POST /api/users`, `PUT/DELETE /api/users/{id}`, `GET/POST /api/admin/multi-user`, `POST /api/shared/copy`. Requests choose the shared library with the `X-Linxiv-Library: shared` header or `?library=shared` on plain links. `/api/me` reports `multi_user`, `username`, `role` and `owner`.

### Changed
- Built against linXiv v0.7.1 (was v0.7.0). CLI commands and MCP tools are unchanged. Project BibTeX export now includes authors and, for arXiv papers, `eprint`/`archivePrefix`; BibTeX import keeps arXiv ids and versions, so an exported project re-imports as the same papers. A broken full-text index now shows as a Library search error instead of returning fewer results.
- Background jobs belong to the library they run on and the account that started them: the same job can run in two libraries at once, and users see only their own jobs. The full-text indexer runs once per library, one arXiv fetch at a time across all of them.
- Activity log entries name the account that made the change.
- Batch edit metadata: Approve all reloads the list once at the end instead of after every paper, and each save no longer reads the paper again first, so a save costs one CLI call instead of three or four. `PUT /api/papers/{id}/metadata` accepts the paper's current `tags`; when they are sent the server skips its own `paper get`.

### Security
- In multi-user mode, app logs, the activity log, the update check, system status and diagnostics, and MCP settings are admin only, as are the server-wide settings (log level, update check, `GHCR_TOKEN`, MCP). The MCP endpoint keeps serving the owner's library.
- Every request reads the account's role from the server, so a role change, password reset or deletion applies at once and ends that account's sessions. Failed logins are counted per address and username, so one account under attack doesn't lock out others.

## [0.1.2] - 2026-10-20

### Added
- Knowledge Graph: **Export GraphML** and **Export CSV** (zip of `nodes.csv` and `edges.csv`) download the whole graph with node metadata, for Gephi, Cytoscape, igraph, NetworkX or pandas. Also available as `GET /api/graph/export`.
- `scripts/bulk-ai-tags.sh --all`: ask the AI about every paper, not only untagged ones; tagged papers keep their tags and gain new ones.
- Home feed: several RSS or Atom feeds instead of one. Settings → Library lists them (name, URL, on/off, up to 10); Home gains a feed picker (all feeds, a single feed, or a random 10 from all) and a keyword box that filters the entries on screen. Entries from the same paper in two feeds are shown once, and each row says which feed it came from. A feed that fails to load is reported on its own without hiding the others. Existing single-feed setups keep working and become the first feed in the list. Filter rules still apply to every feed.
- Project and reading list pages: **batch edit**, as in the Library. Tick papers, then look up metadata for all of them from one source or ask the AI for tags (when AI is on), and approve or skip each paper.
- Paper page: an "Add to project" picker, so a paper can be put in a project or reading list without going through the Library.
- Leaving the Library while a batch metadata or AI tag run is going now asks first, in the app and when closing or reloading the tab; the run stops only if you confirm.
- Documentation website built with [Zensical](https://zensical.org) and managed by uv (`pyproject.toml`, `zensical.toml` at the repository root). Pages live in `docs/`: the existing guides, a tour of every page with screenshots, AI features, configuration, HTTP API, compatibility and development. `uv run zensical serve` previews it; `uv run zensical build` renders it into `site/` (ignored by git).

### Changed
- Paper page redesigned: the PDF fills the left pane and opens with the page, and the paper's details sit in a rail on the right. Drag the divider or use the arrow keys to resize; the width is remembered per browser. The rail shows the title, authors, dates, categories, version and tags, then Details, Notes and Annotations tabs; Projects, AI summary, PDF, Full text and Danger zone are collapsible sections in Details. Papers without a PDF, or whose PDF file is missing, show a card with Download PDF in the left pane. The PDF toolbar gains ‹ › page buttons. The panes stack on narrow screens.
- Sidebar: "Reading" is now "Reading lists", matching the page it opens.
- Home: the "Categories" tile is now "Categories / Journals"; it already counted journal names for papers that are not on arXiv.
- Papers can be saved without an author; they are stored under "Unknown" rather than refused.
- Docs file names are lowercase: `docs/self-hosting.md`, `docs/bulk-import.md`, `docs/bulk-ai-tags.md`, `docs/mcp.md`.

### Fixed
- Library → Batch AI tags: Approve all reloads the library once at the end instead of after every paper, which re-listed the whole library per save and kept the CPU busy (no comments).
- Scrolling inside the PDF reader no longer carries on into the page behind it when the PDF reaches its first or last page.
- Projects and Reading lists: cards in the same row are the same height whether or not a project has a description, and their buttons line up along the bottom.

## [0.1.1] - 2026-10-16

### Changed
- Library: page, search, tag, PDF filter, sort and page size are kept in the URL (`/library?page=2&tag=…`), so a page can be bookmarked, reloaded or shared, and Back from a paper returns to the same page. Search runs when the Search button next to the box is pressed, not while typing. Sort and page size still default to the browser's last choice.
- Paper page links show `:` as typed (`/paper/doi:10.1111/…`) instead of `%3A`; old encoded links still open.
- Add paper and Upload are one page (`/add`) with three sections: add by link or identifier (arXiv, DOI, publisher link, or direct PDF link), upload PDF files, and import a metadata file (BibTeX or Zotero CSL JSON, no PDFs). The Upload sidebar entry is gone; `/upload` opens `/add`.
- README: CI, CodeQL, Security, release, license and image badges.
- Self-hosting guide: the image and repository are public, so pulling needs no `docker login` and compose can build straight from the GitHub URL.

### Fixed
- DOIs with stray characters at either end (`;`, spaces, quotes, brackets, trailing punctuation, a `doi:` or doi.org prefix), as often read from PDFs, are cleaned before metadata lookup (Crossref, PubMed, bioRxiv/medRxiv), in Add paper, when saving metadata, in lookup candidates, BibTeX and notes exports, and in DOI links. Characters inside a DOI are kept.
- Settings → About update check: a private image package now says to make it public or set `GHCR_TOKEN`.

### Security
- Add paper by PDF link: each download hop connects to the address that passed the public-host check, so a second DNS answer can't redirect it to a private address (DNS rebinding). Host header and TLS certificate checks still use the link's host name.
- Settings → Logs: the Download link only takes a known time window and URL-encodes it.

## [0.1.0] - 2026-10-14

### Added
- Browser UI over the `linxiv` CLI (linXiv v0.7.0): Home dashboard and arXiv feed, Library with search (title, abstract, full text, notes), sortable configurable tables, batch metadata edit and AI tags, paper page with PDF reader, highlights and notes.
- Search (arXiv, OpenAlex, Crossref, local) with history and advanced arXiv query builder; Add paper by arXiv id, DOI, publisher link or PDF link; PDF, BibTeX and Zotero import.
- Projects and reading lists with export (`.lxproj`, BibTeX, notes as Markdown) and `.lxproj` import; Authors with merge and ORCID backfill; knowledge graph.
- Metadata lookup and review against Crossref, arXiv, OpenAlex, PubMed and bioRxiv/medRxiv, including lookup by PDF file name.
- Optional AI features (Gemini, OpenAI, Anthropic, OpenAI-compatible): tag suggestions, summaries, metadata cleanup. Optional MCP server over HTTP with bearer token and tool profiles.
- MCP `tools/list` carries tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`, `title`) derived from each tool's profile tier, since `linxiv-mcp` sets none; clients can auto-allow read-only tools and confirm destructive ones.
- Settings → Integrations → MCP server: OpenCode connect snippet (`opencode.json`, token from `LINXIV_MCP_TOKEN`).
- `docs/MCP.md`: setup, Claude Code / Codex / OpenCode clients, profiles, permission hints, full tool reference, security and troubleshooting.
- Settings: themes, zoom and density, sidebar pages, shortcuts, PDF folder layouts, full-text indexing (TeX and PDF text), backup and restore, app logs, update check, disk space and health.
- Single-admin login (argon2), first-run setup, "Remember me", CSRF protection, login throttling, SSRF guards on outbound downloads.
- `scripts/bulk-import.sh` for server-side PDF ingest (copy, move, in situ).
- `scripts/bulk-ai-tags.sh` and `docs/BULK-AI-TAGS.md`: tag every untagged paper with the AI saved in Settings → AI, over loopback with the server running; `--max-tags`, `--jobs` (parallel AI requests; LM Studio Max Concurrent Predictions documented), `--dry-run`, one log line per paper (id, PDF file, tags, status).
- `HEALTHCHECK` in the runtime image (probes `/api/health` on `LINXIV_WEB_PORT`), so it applies without the compose file.
- Security workflow: `npm audit` (high severity and above) and `pip-audit` on the hash-locked server dependencies, on push, pull request and weekly.
- CodeQL (Python, TypeScript, Actions) and OpenSSF Scorecard workflows. Both skip while the repository is private, because code scanning on private repositories needs GitHub Advanced Security.
- Dependabot: weekly grouped updates for uv, npm, GitHub Actions and Docker base images.
- Server branch-coverage gate: pytest fails below 90%.
- Web unit tests with Vitest (`npm test`, `npm run coverage`), run in CI; notes Markdown export checked against the server's golden file.
- `SECURITY.md` and this changelog.
- Docker image publishing from the `release` branch only; the run fails unless `server/pyproject.toml`, `server/app/main.py` and `web/package.json` agree and the version has no `v<version>` tag yet. Manual workflow runs rebuild the current version without tagging.
- GitHub Actions pinned to commit SHAs; `docker.yml` grants no permissions by default.
- Docker base images (`rust`, `debian`, `python`, `node`, `uv`) pinned by multi-arch digest.
- Ruff runs bandit (`S`), bugbear (`B`), pyupgrade (`UP`), import order (`I`) and simplify (`SIM`) rules.
- ESLint is type-aware and rejects un-handled promises (`no-floating-promises`, `no-misused-promises`).
- Settings → Server & data → Login: change the admin password (logs out every other browser) and "Log out other sessions". `python -m app reset-password` sets a new password from the server without a restart. Passwords set by `LINXIV_WEB_PASSWORD(_HASH)` stay read-only here.
- Logins survive restarts: sessions (stored as SHA-256 of their id) and the session signing key live in `<data dir>/linxiv-web-state.db` (mode 0600). `LINXIV_WEB_SECRET_KEY`, when set, replaces the stored key.
- Activity log (Settings → Server & data → Activity): every POST/PUT/PATCH/DELETE under `/api/` with time, client address, route, path parameters and status; Settings saves record key names only, never values. The page shows the latest 50 events; CSV export has the full log. Clearing needs a typed phrase and is itself recorded. `<data dir>/logs/activity.jsonl`, 5 MiB plus one rotated file.
- Diagnostics report (Settings → About): versions, configuration, library counts, disk, health, running jobs and reachability of outside services, as Markdown to copy or download. Secrets and addresses that could locate the server appear only as set / not set.
- Activity tray: running background jobs (TeX source index, PDF text index, PDF folders) with progress and Cancel on every page; finished jobs stay until dismissed.
- Upload page: drag and drop PDFs; drops add to the selection, other file types are skipped with a note.
- Notes render as Markdown (headings, lists, emphasis, links, quotes, code) with TeX math, ported from the desktop app; raw HTML is not rendered.
- Typed confirmation dialog for restoring a backup ("replace library"), clearing the server log ("clear logs") and deleting the activity log.
- `LINXIV_WEB_HSTS=true` sends `Strict-Transport-Security` (for HTTPS deployments). Every response carries a `Permissions-Policy` turning off camera, microphone, geolocation, payment and USB.
- `LINXIV_WEB_AI_ALLOWED_HOSTS` restricts which hosts the OpenAI-compatible AI base URL may use.
- Tags page (`/tags`, hideable in Settings → Sidebar): every tag with its paper count, untagged and total papers, filter box, sort by name or count; a row opens the Library filtered to that tag. `GET /api/tags/counts`.
- Library tag filter "Untagged" (`GET /api/papers?untagged=true`, `/library?untagged=1`).
- Paper page Delete paper / Delete PDF: no countdown. The first press puts Undo in the button's place and the delete button beside it; nothing is deleted until that second press.
- Metadata lookup compare: "Apply and Save" writes the picked fields in one step (was Apply, then Save).
- Settings → Library → Metadata lookup: switch each source (Crossref, arXiv, OpenAlex, PubMed, bioRxiv/medRxiv, AI cleanup) on or off (`web_lookup_disabled`); switched-off sources leave Retrieve metadata and `GET /api/papers/{id}/lookup` refuses them. "Contacts & API keys" moved to the Library group below it; the "AI & sources" group is now "AI".
- AI example replies in prompts and Settings are placeholders (`<tag 1>`, `<title>`), so models don't copy example content.
- Library pages: 50 papers per page by default, pager with 25/50/100/200/500 per page (kept per browser); Authors, Category, Tags and PDF column sorts order the whole library on the server; `X-Total-Count` header on `GET /api/papers`.
- Paper page shows the journal (stored journal, else journal reference; "arXiv preprint" for arXiv papers without one).
- Release flow: a merge from `main` into the `release` branch publishes `ghcr.io/toledoem/linxiv-web:<version>` and `:latest`, tags `v<version>` and creates a GitHub Release from this changelog. Image carries OCI version/revision/source labels.
- `branch-cleanup.yml`: deletes branches daily once their pull request has been merged for 3 days (never `main`/`release` or branches of open PRs; manual run defaults to a dry run).

### Fixed
- PDF reader showed blank pages for scanned PDFs (CCITT fax, JBIG2, JPEG 2000 images) since react-pdf 11 / pdf.js 6: the pdf.js wasm image decoders now ship under `/assets/pdfjs-wasm/` and the CSP allows `'wasm-unsafe-eval'` (WebAssembly only, no JS eval).

### Security
- PubMed lookup parses NCBI XML with `defusedxml`; replies with entity declarations are refused (502) instead of expanded.
- Requests from public IP addresses are refused (403) unless `LINXIV_WEB_ALLOW_EXTERNAL=true`; loopback, private LAN and link-local clients are served. `X-Forwarded-For` is read only from proxies listed in `LINXIV_WEB_TRUSTED_PROXIES` (IPs or CIDRs), right to left, so a client can't forge its address. Refused requests are logged once per address per minute.
- Login throttle (5 failures per 5 minutes) keyed on the real client address behind trusted proxies and kept across restarts; old entries pruned.
- The OpenAI-compatible AI base URL may not resolve to cloud metadata addresses (`169.254.0.0/16`, `fd00:ec2::254`, `100.100.100.200`); checked before every request, so the API key is never sent there.
- Unexpected server errors return `{"detail": "internal server error"}` without internals.
- At most two PDF text extractions (AI summary, PDF full-text index) run at once.
