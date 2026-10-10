# Changelog

All notable changes to linXiv-web are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The version is `server/pyproject.toml` `version`; images are published to `ghcr.io/toledoem/linxiv-web:<version>`.

## [0.1.0] - Unreleased

### Added
- Browser UI over the `linxiv` CLI (linXiv v0.7.0): Home dashboard and arXiv feed, Library with search (title, abstract, full text, notes), sortable configurable tables, batch metadata edit and AI tags, paper page with PDF reader, highlights and notes.
- Search (arXiv, OpenAlex, Crossref, local) with history and advanced arXiv query builder; Add paper by arXiv id, DOI, publisher link or PDF link; PDF, BibTeX and Zotero import.
- Projects and reading lists with export (`.lxproj`, BibTeX, notes as Markdown) and `.lxproj` import; Authors with merge and ORCID backfill; knowledge graph.
- Metadata lookup and review against Crossref, arXiv, OpenAlex, PubMed and bioRxiv/medRxiv, including lookup by PDF file name.
- Optional AI features (Gemini, OpenAI, Anthropic, OpenAI-compatible): tag suggestions, summaries, metadata cleanup. Optional MCP server over HTTP with bearer token and tool profiles.
- Settings: themes, zoom and density, sidebar pages, shortcuts, PDF folder layouts, full-text indexing (TeX and PDF text), backup and restore, app logs, update check, disk space and health.
- Single-admin login (argon2), first-run setup, "Remember me", CSRF protection, login throttling, SSRF guards on outbound downloads.
- `scripts/bulk-import.sh` for server-side PDF ingest (copy, move, in situ).
- `HEALTHCHECK` in the runtime image (probes `/api/health` on `LINXIV_WEB_PORT`), so it applies without the compose file.
- Security workflow: `npm audit` (high severity and above) and `pip-audit` on the hash-locked server dependencies, on push, pull request and weekly.
- CodeQL (Python, TypeScript, Actions) and OpenSSF Scorecard workflows. Both skip while the repository is private, because code scanning on private repositories needs GitHub Advanced Security.
- Dependabot: weekly grouped updates for uv, npm, GitHub Actions and Docker base images.
- Server branch-coverage gate: pytest fails below 90%.
- `SECURITY.md` and this changelog.
- Docker image publishing: a push to `main` builds and pushes only when `server/pyproject.toml` holds a version not yet in GHCR; manual workflow runs always rebuild.
- GitHub Actions pinned to commit SHAs; `docker.yml` grants no permissions by default.
- Docker base images (`rust`, `debian`, `python`, `node`, `uv`) pinned by multi-arch digest.
- Ruff runs bandit (`S`), bugbear (`B`), pyupgrade (`UP`), import order (`I`) and simplify (`SIM`) rules.
- ESLint is type-aware and rejects un-handled promises (`no-floating-promises`, `no-misused-promises`).

### Security
- PubMed lookup parses NCBI XML with `defusedxml`; replies with entity declarations are refused (502) instead of expanded.
