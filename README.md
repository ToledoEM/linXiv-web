# linXiv-web

linXiv-web is a browser UI for [linXiv](https://github.com/linxiv-dev/linXiv). You can search arXiv, OpenAlex and Crossref, add papers to a library, tag them, organize them into projects and reading lists, read and highlight their PDFs, and take notes.

It is a separate project written to fit the [linxiv-dev](https://github.com/linxiv-dev) organization. The linXiv maintainers have not adopted it, so it is not an official linXiv component.

## Features

- **Library:** sortable table (click any column header), one search box over title, abstract, authors, ids, tags, indexed full text and notes, PDF filters, batch metadata editing.
- **Papers:** metadata editing with lookup and side-by-side compare against Crossref, arXiv, OpenAlex, PubMed and bioRxiv/medRxiv; versions; tags; notes; PDF reader with find and highlights; arXiv TeX source indexing for full-text search.
- **Projects and reading lists:** projects with export (BibTeX, Obsidian, Zotero, `.lxproj`) and `.lxproj` import; reading lists on their own page.
- **Discovery:** search tabs (arXiv, OpenAlex, Crossref, local) with an advanced arXiv query builder, add papers by arXiv id, DOI or PDF link, RSS/Atom home feed with filter rules, arXiv new-version monitor.
- **Authors and graph:** author pages, edit and merge, ORCID backfill, knowledge graph of papers, authors and tags.
- **Maintenance:** trash, backup / import / restore of the database, PDF folder layouts (by year and/or journal), background full-text indexer.
- **AI (opt-in):** tag suggestions, paper summaries saved as notes, metadata cleanup, with Gemini, OpenAI, Anthropic or any OpenAI-compatible server (LM Studio, Ollama, vLLM, OpenRouter).
- **MCP (opt-in):** linXiv's own MCP tools over HTTP at `/mcp`, for Claude Code and Codex.
- Themes (light/dark), zoom and density, keyboard shortcuts, sidebar page toggles.

## How it works

linXiv-web reaches linXiv through the `linxiv` CLI, which prints JSON for every command. A FastAPI server runs `linxiv <command>` as a subprocess, passing arguments as a list without a shell, and serves a React single-page app.

```
browser ──HTTP──▶ FastAPI (/api/*, static SPA) ──subprocess──▶ linxiv CLI ──▶ papers.db + pdfs/
MCP client ──HTTP /mcp──▶ FastAPI ──stdio──▶ linxiv-mcp ──▶ papers.db + pdfs/
```

Library reads and writes go through the CLI. Two exceptions, both where the CLI has no command: PDF folder layouts move files and update their stored path in `papers.db` directly (under the CLI lock), and the AI summary reads text from a saved PDF.

The server contacts outside services itself only in these cases:

- it downloads a PDF link pasted into Add Paper before importing it (public hosts only, size-capped);
- metadata lookup queries PubMed through NCBI E-utilities (`eutils.ncbi.nlm.nih.gov`) and bioRxiv/medRxiv through `api.biorxiv.org`;
- when AI features are switched on, AI actions send the paper's title, abstract (and, if you choose, PDF text) to the provider you configured. Nothing is sent until you click an AI button.

A linXiv library allows one writing process per data dir, so the server runs CLI calls one at a time behind a lock. Work that needs many calls, such as indexing the TeX source of every saved arXiv paper, runs as a background job that makes one call per paper, so other requests get the lock between them. Jobs live in memory: restarting the server stops a running job and forgets finished ones. Don't point linXiv-web at a data dir that the desktop app or `linxiv-headless` also uses.

`linxiv` always writes PDFs to `<data dir>/pdfs`. The container turns that path into a symlink to `/pdfs`, which lets the database stay on local disk while the PDFs sit on other storage.

Like `linxiv-headless`, the server refuses to start if it binds to a non-loopback address without a password.

## Compatibility

| linXiv-web | linXiv CLI / MCP |
|---|---|
| 0.1.x | v0.6.0 |

The image builds `linxiv` and `linxiv-mcp` from upstream source at the `LINXIV_REF` build arg (default `v0.6.0`).

## Run (Docker)

```sh
cp .env.example .env
mkdir -p .dev/data .dev/pdfs

# Generate a password hash and paste it into .env (keep the single quotes)
docker compose build
docker compose run --rm --no-deps -e PASSWORD='your-password' linxiv-web python -m app hash-password

docker compose up -d
```

Open http://127.0.0.1:8086 and log in. After an update, rebuild and recreate the container (`docker compose build && docker compose up -d --force-recreate`), then reload the page with Cmd/Ctrl+Shift+R.

To keep the library elsewhere, set `LINXIV_WEB_DATA_HOST` and `LINXIV_WEB_PDF_HOST` in `.env`. Both directories must already exist. Keep the database directory on local disk, because SQLite over network or exFAT storage is unreliable.

### Run with your own docker-compose.yml and .env

To run linXiv-web on another machine without cloning the repo, make a folder with two files. Compose builds the image straight from the git repository: replace `$PLACEHOLDERFUTUREURL` with the repository's git URL. The first build compiles linXiv from source and takes several minutes.

```sh
mkdir -p linxiv-web/data linxiv-web/pdfs
cd linxiv-web
```

`docker-compose.yml`:

```yaml
services:
  linxiv-web:
    build:
      # Replace with the repository's git URL
      context: $PLACEHOLDERFUTUREURL#main
      args:
        LINXIV_REF: ${LINXIV_REF:-v0.6.0}
    image: linxiv-web:local
    container_name: linxiv-web
    restart: unless-stopped
    env_file: .env
    ports:
      # 127.0.0.1 = this machine only. Use 0.0.0.0 to reach it from the LAN.
      - "${LINXIV_WEB_BIND:-127.0.0.1}:${LINXIV_WEB_PUBLISH_PORT:-8086}:8000"
    volumes:
      - type: bind
        source: ${LINXIV_WEB_DATA_HOST:-./data}
        target: /data
        bind:
          create_host_path: false
      - type: bind
        source: ${LINXIV_WEB_PDF_HOST:-./pdfs}
        target: /pdfs
        bind:
          create_host_path: false
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
```

`.env` (keep the single quotes around the hash; it contains `$`):

```sh
# Login password: argon2 hash (see the command below)
LINXIV_WEB_PASSWORD_HASH='$argon2id$v=19$m=65536,t=3,p=4$REPLACE$ME'

# Session signing key, so a restart doesn't log you out (any long random string)
LINXIV_WEB_SECRET_KEY=change-me-to-a-long-random-string

# Where the port is published (docker-compose.yml above)
LINXIV_WEB_BIND=127.0.0.1
LINXIV_WEB_PUBLISH_PORT=8086

# Library location on this machine (must exist; keep data on local disk)
LINXIV_WEB_DATA_HOST=./data
LINXIV_WEB_PDF_HOST=./pdfs

# Behind an HTTPS reverse proxy
# LINXIV_WEB_COOKIE_SECURE=true

# Optional: contact addresses and API keys. They can also be set in Settings;
# values here take precedence.
# CROSSREF_MAILTO=you@example.org
# NCBI_API_KEY=
# GEMINI_API_KEY=
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# GENAI_API_KEY_TAG_GEN=
```

Build, set the password, start:

```sh
docker compose build
docker compose run --rm --no-deps -e PASSWORD='your-password' linxiv-web python -m app hash-password
# paste the printed hash into .env as LINXIV_WEB_PASSWORD_HASH, then:
docker compose up -d
```

Open http://127.0.0.1:8086 (or `http://<machine-ip>:8086` with `LINXIV_WEB_BIND=0.0.0.0`). To update later: `docker compose build --no-cache && docker compose up -d`.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LINXIV_WEB_PASSWORD_HASH` | none | argon2 hash of the login password (`python -m app hash-password`). Without it (or `LINXIV_WEB_PASSWORD`), first-run setup in the browser creates the password, stored in `<data dir>/linxiv-web-auth.json` |
| `LINXIV_WEB_PASSWORD` | none | Plain password, hashed in memory at startup (dev only) |
| `LINXIV_WEB_SECRET_KEY` | random per start | Session signing key. If unset, a restart logs everyone out |
| `LINXIV_WEB_COOKIE_SECURE` | `false` | Set to `true` behind HTTPS |
| `LINXIV_WEB_REMEMBER_DAYS` | `90` | Login lifetime when "Remember me" is ticked (otherwise the login lasts until the browser closes, at most 14 days) |
| `LINXIV_WEB_DATA_DIR` | `/data` | linXiv data dir (`papers.db`). Passed to the CLI and MCP server as `LINXIV_DATA_DIR` |
| `LINXIV_WEB_PDF_DIR` | `/pdfs` | PDF directory, symlinked from `<data dir>/pdfs` |
| `LINXIV_WEB_HOST` / `LINXIV_WEB_PORT` | `0.0.0.0` / `8000` in the image | Listen address |
| `LINXIV_WEB_MAX_UPLOAD_MB` | `200` | Upload size cap |
| `LINXIV_WEB_TIMEOUT_LONG` / `_SHORT` | `120` / `30` | CLI timeout in seconds (search, fetch, download and import use the long one) |
| `LINXIV_BIN` / `LINXIV_MCP_BIN` | `linxiv` / `linxiv-mcp` | CLI and MCP server binaries |
| `ARXIV_MAILTO`, `CROSSREF_MAILTO`, `OPENALEX_MAILTO` | none | Contact addresses sent to those services; override the values set in Settings |
| `NCBI_API_KEY` | none | PubMed key; overrides the one set in Settings |
| `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GENAI_API_KEY_TAG_GEN` | none | AI provider keys (the last one is for the OpenAI-compatible endpoint); override the ones set in Settings |

Keys entered in Settings are stored in the linXiv settings store and are never sent back to the browser (only their last 4 characters).

## AI features

Off by default. In **Settings → AI**: tick the switch, pick a provider (Gemini, OpenAI, Anthropic, or an OpenAI-compatible base URL such as `http://localhost:1234/v1` for LM Studio), paste a key (optional for local servers), Save, then **Load models**, pick one, Save, and **Test connection**.

| Action | Where | What the model gets | Result |
|---|---|---|---|
| AI Tags | paper page, Library batch panel ("AI tags") | title, categories, abstract, current tags, your existing tag vocabulary | up to 8 tags to tick and add |
| AI summary | paper page | "Abstract only", or "Abstract + PDF text" (first 40 pages, 60k characters) | summary + key points, saved as a note on request |
| AI cleanup | Edit metadata and Library batch metadata, source "AI cleanup" | title, authors, journal | a candidate shown as a field diff; nothing is saved until you approve |

Every request carries a JSON Schema and a valid example reply (shown in Settings → AI). OpenAI and OpenAI-compatible servers get structured output (`response_format: json_schema`), which also keeps "thinking" models such as Qwen from spending the whole token budget on reasoning; a server that rejects it is retried with the schema in the prompt only. Anthropic uses a forced tool call. Requests time out after 90 s (300 s for OpenAI-compatible servers, since local models read long prompts slowly).

## MCP server (Claude Code / Codex)

Off by default. linXiv-web builds upstream's `linxiv-mcp` and serves its tools over MCP Streamable HTTP at `/mcp`. Each MCP session gets its own `linxiv-mcp` process (at most 4 sessions, closed after 30 minutes idle).

In **Settings → MCP server**: tick the switch, choose which tools the agent gets, Save, then **Create token**. The token is shown once (only its SHA-256 is stored); replacing or revoking it disconnects open sessions. The card shows the commands with the token filled in:

```sh
# Claude Code
claude mcp add --transport http linxiv http://127.0.0.1:8086/mcp --header "Authorization: Bearer <token>"

# Codex
export LINXIV_MCP_TOKEN=<token>
codex mcp add linxiv --url http://127.0.0.1:8086/mcp --bearer-token-env-var LINXIV_MCP_TOKEN
```

| Profile | Tools | Adds |
|---|---|---|
| Read only (default) | 32 | search, get, list, refs, stats |
| Read + edit library | 68 | papers, notes, tags, projects, highlights; soft deletes (to the trash) |
| Full | 75 | hard deletes, merging papers or authors, metadata overwrite |

Never exposed: `get_settings` / `update_setting` (the settings store holds API keys), backup and restore, and the import/export tools that read or write server file paths. `download_pdf` with a caller-chosen `url` is refused; the paper's stored link is used. Tools added upstream stay hidden until they are classified.

`/mcp` does not use the browser login: it needs the bearer token, answers 404 while switched off, and refuses requests that carry another site's `Origin`.

## API

All routes except `/api/health`, `/api/login`, `/api/me` and `/mcp` need a session when a password is set. Write requests also need the `X-CSRF-Token` header, which echoes the `lxw_csrf` cookie.

| Route | linxiv command / behaviour |
|---|---|
| `GET /api/search?q&source=arxiv\|openalex\|crossref&max` | `search` |
| `POST /api/papers/{id}/fetch?source=` | `fetch`, then `paper get` |
| `GET /api/papers?q&tag&pdf=has\|none&fulltext&limit&offset&category&sort&dir` | `list` filtered server-side; a `q` of 3+ characters also runs `paper search` (TeX full text and notes), hits flagged `deep_match`; `fulltext=true` returns only the `paper search` hits |
| `GET /api/papers/{id}`, `GET /api/papers/{id}/versions` | `paper get`, `paper versions` |
| `DELETE /api/papers/{id}` | `paper delete` (soft delete, goes to trash) |
| `GET /api/papers/{id}/pdf` | `pdf path`, then serves the file (only from inside the data or PDF dir) |
| `POST /api/papers/{id}/pdf` `{url?, version?}` | `pdf download` (for arXiv papers the URL is derived) |
| `DELETE /api/papers/{id}/pdf` | `pdf delete` |
| `PUT /api/papers/{id}/metadata` `{title, authors[], published, summary, category?, doi?, url?}` | `paper get`, then `paper repair` with the full record and the paper's current tags (repair clears any field it isn't given) |
| `GET /api/papers/{id}/lookup?source=crossref\|arxiv\|openalex\|pubmed\|biorxiv` | Candidate metadata: `doi resolve` (by DOI), `search` (by arXiv id or title), NCBI E-utilities for PubMed (by DOI, then title), api.biorxiv.org (by DOI) |
| `GET/POST/DELETE /api/papers/{id}/tags` | `tag list` / `tag add` / `tag remove` |
| `GET /api/pdfs`, `GET /api/pdfs/storage` | `pdf list`, `pdf storage` (recounted including subfolders) |
| `POST /api/pdfs/import` (multipart `file`) | `pdf import` |
| `GET /api/pdfs/layout/preview?layout=`, `POST /api/jobs/pdf-layout` | PDF folder layout (`none`, `year`, `journal`, `year/journal`, `journal/year`): preview, then a job that moves files and updates their stored path |
| `POST /api/import/bibtex`, `POST /api/import/zotero` (multipart `file`) | `bibtex import`, `zotero import` (upsert: existing entries are updated) |
| `POST /api/add` `{input}` | arXiv id/link: `fetch`; DOI or doi.org link: `doi save`; other http(s) link: server downloads the PDF (public hosts only, size-capped), then `pdf import` |
| `GET /api/stats`, `/api/categories`, `/api/tags` | `stats`, `categories`, `tag list-all` |
| `GET /api/authors?hide_single`, `GET/PATCH/DELETE /api/authors/{id}` | `author list`, `author get`, `author update`, `author delete` (409 while linked to papers) |
| `GET /api/authors/{id}/merge-candidates`, `POST /api/authors/{id}/merge` | `author merge-candidates` (plus same-name hints), `author merge` |
| `POST /api/orcid/backfill` `{limit?}` | `orcid backfill` (1 to 100; 409 while one runs) |
| `GET /api/projects?status=active\|archived`, `POST /api/projects`, `PATCH /api/projects/{id}` | `project list`, `project create`, `project update` |
| `GET /api/projects/{id}`, `GET /api/projects/{id}/papers` | `project get`; papers = `project get` + `list`, filtered to members in project order |
| `POST /api/projects/{id}/papers` (`{"source_ids": [...]}`), `DELETE /api/projects/{id}/papers/{source_id}` | `project add-papers` (200 with `added`/`failed`), `project remove-paper` |
| `GET /api/projects/{id}/export?format=lxproj\|bibtex\|obsidian\|zotero&pdfs` | `project export [--pdfs]`, `export-bibtex`, `export-obsidian`, `export-zotero`; written to a temp dir, sent as a download, then deleted |
| `POST /api/projects/import/preview`, `POST /api/projects/import` (multipart `file`, `on_conflict=merge\|overwrite`) | `project import --preview`, `project import` (`.lxproj`, zip checked before the CLI sees it) |
| `POST /api/projects/{id}/archive`, `POST /api/projects/{id}/restore`, `DELETE /api/projects/{id}` | `project archive`, `project restore`, `project delete` (soft delete, goes to trash) |
| `GET /api/notes?paper=&project=`, `POST /api/notes`, `PATCH /api/notes/{id}`, `DELETE /api/notes/{id}` | `note list`, `note create [--project-id]`, `note update`, `note delete` (permanent); title/content capped at 100 kB |
| `GET /api/annotations?paper=&project=`, `POST /api/annotations`, `PATCH /api/annotations/{id}`, `DELETE /api/annotations/{id}` | `annotation list/create/update/delete` (PDF highlights; anchors validated server-side) |
| `GET /api/graph` | Knowledge graph of papers, authors and tags, built from `list` and `author list` |
| `GET /api/feed`, `POST /api/feed/dismiss` | `feed get` for the stored home feed URL (cached 5 minutes), `feed dismiss` |
| `GET /api/feed/rules`, `POST /api/feed/rules`, `DELETE /api/feed/rules/{id}` | `feed rules list/add/delete` |
| `GET /api/versions/new`, `POST /api/versions/check` `{limit?}`, `POST /api/versions/{id}/ack` | `versions new`, `versions check --limit` (1 to 100, default 20; stores new versions it finds), `versions ack` (a second ack still returns ok) |
| `POST /api/papers/{id}/source` `{force?}` | `paper fetch-source [--force]`: downloads the paper's arXiv LaTeX source and indexes its text for full-text search (400 for non-arXiv papers) |
| `GET /api/sources/pending`, `GET /api/sources/worker` | Saved arXiv papers whose source isn't indexed; status of the background full-text indexer |
| `POST /api/jobs/index-sources` `{limit?}`, `GET /api/jobs?kind=`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel` | Background job: one `paper fetch-source` per pending paper, 7 s apart (409 if one is already running) |
| `GET /api/trash` | `trash list` |
| `POST /api/trash/papers/{id}/restore`, `DELETE /api/trash/papers/{id}` | `trash restore`, `trash hard-delete` (paper must be in the trash) |
| `POST /api/trash/projects/{id}/restore`, `DELETE /api/trash/projects/{id}` | `trash restore-project`, `trash hard-delete-project` |
| `GET /api/backup`, `POST /api/backup/import`, `POST /api/backup/restore` (multipart `file`) | `backup` (database snapshot download), `import` (merge another database), `restore` (replace the library; refused while a job runs) |
| `GET /api/settings`, `PATCH /api/settings` | `settings get`, `settings update`, limited to an allowlist (storage cap, TeX rendering, contact addresses, home feed, search history, full-text worker, AI and MCP settings); API keys are write-only |
| `GET /api/ai/models`, `POST /api/ai/test`, `GET /api/ai/schemas` | Provider model list, connection test, the JSON Schema and example each AI action uses (409 while AI is off) |
| `POST /api/ai/tags/{id}`, `POST /api/ai/summary/{id}?pdf=`, `POST /api/ai/cleanup/{id}` | AI tag suggestions, summary, metadata cleanup; previews only, nothing is written |
| `GET /api/mcp`, `POST /api/mcp/token`, `DELETE /api/mcp/token` | MCP status, create (shown once) or revoke the access token |
| `POST/GET/DELETE /mcp` | MCP Streamable HTTP endpoint (bearer token; see above) |

Paper ids are linXiv source ids such as `arxiv:1706.03762`. Old-style arXiv ids keep their slash: `/api/papers/arxiv:hep-th/9901001`.

## Development

Everything runs in containers.

```sh
# Server: ruff + pytest, including tests against the real linxiv and linxiv-mcp binaries
docker build --target server-test .

# Frontend: lint, type check, build
docker run --rm -v "$PWD/web":/w -w /w node:22-slim sh -c 'npm ci && npm run lint && npm run build'

# Just the CLI (handy for exploring its JSON output)
docker build --target cli -t linxiv-cli .
docker run --rm -v lxw-scratch:/data linxiv-cli stats
```

To build against a local linXiv checkout instead of a tag (its submodules must be initialised):

```sh
docker build --build-arg LINXIV_SRC=local --build-context linxiv-local=../linXiv .
```

The FastAPI server lives in `server/`: the CLI subprocess wrapper is `app/cli.py`, the AI provider client `app/ai.py`, and the MCP bridge `app/mcp_bridge.py`. The Vite, React and TypeScript frontend lives in `web/`. The `Dockerfile` builds the CLI and MCP server first, then the SPA, then the Python runtime image.

Branch and commit conventions match linXiv's; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- Bring the Peer-to-peer project sharing into the web-app


## License

[Apache-2.0](LICENSE). See [NOTICE](NOTICE).
