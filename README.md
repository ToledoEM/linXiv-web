# linXiv-web

linXiv-web is a browser UI for [linXiv](https://github.com/linxiv-dev/linXiv). You can search arXiv, OpenAlex and Crossref, add papers to a library, tag them, and manage their PDFs.

It is a separate project written to fit the [linxiv-dev](https://github.com/linxiv-dev) organization. The linXiv maintainers have not adopted it, so it is not an official linXiv component.

## How it works

linXiv-web reaches linXiv only through the `linxiv` CLI, which prints JSON for every command. A FastAPI server runs `linxiv <command>` as a subprocess, passing arguments as a list without a shell, and serves a React single-page app.

```
browser ──HTTP──▶ FastAPI (/api/*, static SPA) ──subprocess──▶ linxiv CLI ──▶ papers.db + pdfs/
```

A linXiv library allows one writing process per data dir, so the server runs CLI calls one at a time behind a lock. Don't point linXiv-web at a data dir that the desktop app or `linxiv-headless` also uses.

`linxiv` always writes PDFs to `<data dir>/pdfs`. The container turns that path into a symlink to `/pdfs`, which lets the database stay on local disk while the PDFs sit on other storage.

Like `linxiv-headless`, the server refuses to start if it binds to a non-loopback address without a password.

## Compatibility

| linXiv-web | linXiv CLI |
|---|---|
| 0.1.x | v0.6.0 |

The image builds `linxiv` from upstream source at the `LINXIV_REF` build arg (default `v0.6.0`).

## Run (Docker)

```sh
cp .env.example .env
mkdir -p .dev/data .dev/pdfs

# Generate a password hash and paste it into .env (keep the single quotes)
docker compose build
docker compose run --rm --no-deps -e PASSWORD='your-password' linxiv-web python -m app hash-password

docker compose up -d
```

Open http://127.0.0.1:8086 and log in.

To keep the library elsewhere, set `LINXIV_WEB_DATA_HOST` and `LINXIV_WEB_PDF_HOST` in `.env`. Both directories must already exist. Keep the database directory on local disk, because SQLite over network or exFAT storage is unreliable.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LINXIV_WEB_PASSWORD_HASH` | none | argon2 hash of the login password (`python -m app hash-password`) |
| `LINXIV_WEB_PASSWORD` | none | Plain password, hashed in memory at startup (dev only) |
| `LINXIV_WEB_SECRET_KEY` | random per start | Session signing key. If unset, a restart logs everyone out |
| `LINXIV_WEB_COOKIE_SECURE` | `false` | Set to `true` behind HTTPS |
| `LINXIV_WEB_DATA_DIR` | `/data` | linXiv data dir (`papers.db`). Passed to the CLI as `LINXIV_DATA_DIR` |
| `LINXIV_WEB_PDF_DIR` | `/pdfs` | PDF directory, symlinked from `<data dir>/pdfs` |
| `LINXIV_WEB_HOST` / `LINXIV_WEB_PORT` | `0.0.0.0` / `8000` in the image | Listen address |
| `LINXIV_WEB_MAX_UPLOAD_MB` | `200` | Upload size cap |
| `LINXIV_WEB_TIMEOUT_LONG` / `_SHORT` | `120` / `30` | CLI timeout in seconds (search, fetch, download and import use the long one) |

## API

All routes except `/api/health`, `/api/login` and `/api/me` need a session when a password is set. Write requests also need the `X-CSRF-Token` header, which echoes the `lxw_csrf` cookie.

| Route | linxiv command |
|---|---|
| `GET /api/search?q&source=arxiv\|openalex\|crossref&max` | `search` |
| `POST /api/papers/{id}/fetch?source=` | `fetch`, then `paper get` |
| `GET /api/papers?q&tag&pdf=has\|none&fulltext&limit&offset&category&sort&dir` | `list` (`q`/`tag`/`pdf` filtered server-side), or `paper search` when `fulltext=true` |
| `GET /api/papers/{id}` | `paper get` |
| `GET /api/papers/{id}/versions` | `paper versions` |
| `DELETE /api/papers/{id}` | `paper delete` (soft delete, goes to trash) |
| `GET /api/papers/{id}/pdf` | `pdf path`, then serves the file (only from inside the data or PDF dir) |
| `POST /api/papers/{id}/pdf` `{url?, version?}` | `pdf download` (for arXiv papers the URL is derived) |
| `DELETE /api/papers/{id}/pdf` | `pdf delete` |
| `GET/POST/DELETE /api/papers/{id}/tags` | `tag list` / `tag add` / `tag remove` |
| `GET /api/pdfs`, `GET /api/pdfs/storage` | `pdf list`, `pdf storage` |
| `POST /api/pdfs/import` (multipart `file`) | `pdf import` |
| `POST /api/import/bibtex`, `POST /api/import/zotero` (multipart `file`) | `bibtex import`, `zotero import` (upsert: existing entries are updated) |
| `POST /api/add` `{input}` | arXiv id/link: `fetch`; DOI or doi.org link: `doi save`; other http(s) link: server downloads the PDF (public hosts only, size-capped), then `pdf import` |
| `GET /api/stats`, `/api/categories`, `/api/tags` | `stats`, `categories`, `tag list-all` |
| `GET /api/authors?hide_single` | `author list` (`hide_single` drops one-paper authors server-side) |
| `GET /api/projects?status=active\|archived`, `POST /api/projects`, `PATCH /api/projects/{id}` | `project list`, `project create`, `project update` |
| `GET /api/projects/{id}`, `GET /api/projects/{id}/papers` | `project get`; papers = `project get` + `list`, filtered to members in project order |
| `POST /api/projects/{id}/papers` (`{"source_ids": [...]}`), `DELETE /api/projects/{id}/papers/{source_id}` | `project add-papers` (200 with `added`/`failed`), `project remove-paper` |
| `GET /api/projects/{id}/export?format=lxproj\|bibtex\|obsidian\|zotero&pdfs` | `project export [--pdfs]`, `export-bibtex`, `export-obsidian`, `export-zotero`; written to a temp dir, sent as a download, then deleted |
| `POST /api/projects/{id}/archive`, `POST /api/projects/{id}/restore`, `DELETE /api/projects/{id}` | `project archive`, `project restore`, `project delete` (soft delete, goes to trash) |
| `GET /api/trash` | `trash list` |
| `POST /api/trash/papers/{id}/restore`, `DELETE /api/trash/papers/{id}` | `trash restore`, `trash hard-delete` (paper must be in the trash) |
| `POST /api/trash/projects/{id}/restore`, `DELETE /api/trash/projects/{id}` | `trash restore-project`, `trash hard-delete-project` |
| `GET /api/settings`, `PATCH /api/settings` | `settings get`, `settings update` (allowlist: `pdf_save_limit_mb`, `tex_rendering_enabled`, `ARXIV_MAILTO`, `CROSSREF_MAILTO`, `OPENALEX_MAILTO`) |

Paper ids are linXiv source ids such as `arxiv:1706.03762`. Old-style arXiv ids keep their slash: `/api/papers/arxiv:hep-th/9901001`.

## Development

Everything runs in containers.

```sh
# Server: ruff + pytest, including one test against the real linxiv binary
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

The FastAPI server lives in `server/`, with the subprocess wrapper in `app/cli.py`. The Vite, React and TypeScript frontend lives in `web/`. The `Dockerfile` builds the CLI first, then the SPA, then the Python runtime image.

Branch and commit conventions match linXiv's; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE). See [NOTICE](NOTICE).
