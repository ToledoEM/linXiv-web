# Changelog

All notable changes to linXiv-web are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The version is `server/pyproject.toml` `version`; images are published to `ghcr.io/toledoem/linxiv-web:<version>`.

## [Unreleased]

### Fixed
- Library → Batch AI tags: Approve all reloads the library once at the end instead of after every paper, which re-listed the whole library per save and kept the CPU busy (no comments).

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
