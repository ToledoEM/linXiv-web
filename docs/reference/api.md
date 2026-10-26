# HTTP API

The web UI uses this API, and scripts can call it too. Every route except `/api/health`, `/api/login`, `/api/me` and `/mcp` needs a session when a password is set. Write requests also need the `X-CSRF-Token` header, which echoes the `lxw_csrf` cookie.

Most routes map to one `linxiv` CLI command. The right column names the command or describes what the server does.

In multi-user mode (see [Server Admin](../server-admin.md)) each request works on the caller's own library, or on the shared library when it sends the header `X-Linxiv-Library: shared` (plain links such as a PDF or a download use `?library=shared` instead). Writes to the shared library by accounts that are not admins get 403, except `POST /api/shared/copy` and `POST /api/export/bibtex`. Logs, activity, update check, system status and diagnostics, and `/api/mcp` are admin only. `GET /api/jobs` lists only the caller's own jobs for accounts that are not admins.

| Route | linxiv command / behaviour |
|---|---|
| `POST /api/login` `{username?, password, remember?}` | Start a session. `username` is required in multi-user mode and ignored otherwise; failed attempts are limited per client address and username |
| `GET /api/me` | Login state: `auth_enabled`, `setup_required`, `authenticated`, `password_source`, `multi_user`, `username`, `role` (`admin` or `user`), `owner` |
| `POST /api/password` `{current, new, remember?}` | Change the caller's own password; logs out the caller's other sessions. For the owner this is the stored server password (409 when it comes from `LINXIV_WEB_PASSWORD(_HASH)`). In multi-user mode the new password must differ from every other account's |
| `GET /api/admin/multi-user`, `POST /api/admin/multi-user` `{enabled, username?}` | Admin only. Multi-user status and owner username; turn it on (`username` names the owner the first time) or off (owner only; logs out every other account) |
| `GET /api/users`, `POST /api/users` `{username, password, role}` | Admin only. List accounts (never their password hashes); create one with its own library (409 for a taken username, 400 for a password another account uses) |
| `PUT /api/users/{id}` `{username?, password?, role?}`, `DELETE /api/users/{id}` | Admin only. Rename, set a password, change the role (each ends that account's sessions); delete (the library stays on disk, its path is returned). The owner stays admin and can't be deleted; the last admin can't be demoted or deleted; nobody deletes their own account |
| `POST /api/shared/copy` `{source_ids}` | Copy papers with their PDFs from the shared library into the caller's own: a temporary project is exported with `project export --pdfs` and imported with `project import --on-conflict=merge`, then both temporary projects are deleted. Returns `copied`, `failed`, `skipped_pdfs` |
| `POST /api/sessions/revoke-others` | Log out every session except the caller's; returns `{revoked}` |
| `GET /api/activity?limit`, `GET /api/activity/export` | Activity log, newest first / as CSV: every POST/PUT/PATCH/DELETE under `/api/` with time, client address, route, path parameters, status (Settings saves: key names only). Kept in `<data dir>/logs/activity.jsonl`, 5 MiB + one rotated file |
| `DELETE /api/activity` `{confirm: "delete activity log"}` | Clear the activity log (the clear is recorded) |
| `GET /api/system/diagnostics` | Markdown report for bug reports: versions, configuration, library counts, disk, health, running jobs, DNS + TCP 443 reachability of outside services. Secrets and addresses that could locate the server only as set / not set |
| `GET /api/search?q&source=arxiv\|openalex\|crossref&max` | `search` |
| `POST /api/papers/{id}/fetch?source=` | `fetch`, then `paper get` |
| `GET /api/papers?q&tag&pdf=has\|none&fulltext&limit&offset&category&sort&dir` | `list` filtered server-side; a `q` of 3+ characters also runs `paper search` (TeX full text and notes), hits flagged `deep_match`; `fulltext=true` returns only the `paper search` hits. Each paper also gets `pdf_file` (its PDF's path inside the PDF folder) and `title_suspect` (the title looks like junk read from the PDF, or unlike the file name) |
| `GET /api/papers/{id}`, `GET /api/papers/{id}/versions` | `paper get` (plus `pdf_file` and `title_suspect`), `paper versions` |
| `DELETE /api/papers/{id}` | `paper delete` (soft delete, goes to trash) |
| `GET /api/papers/{id}/pdf` | `pdf path`, then serves the file (only from inside the data or PDF dir) |
| `POST /api/papers/{id}/pdf` `{url?, version?}` | `pdf download` (for arXiv papers the URL is derived) |
| `DELETE /api/papers/{id}/pdf` | `pdf delete` |
| `PUT /api/papers/{id}/metadata` `{title, authors[], published, summary, category?, doi?, url?}` | `paper get`, then `paper repair` with the full record and the paper's current tags (repair clears any field it isn't given) |
| `GET /api/papers/{id}/lookup?source=crossref\|arxiv\|openalex\|pubmed\|biorxiv&by=auto\|filename` | Candidate metadata: `doi resolve` (by DOI), `search` (by arXiv id or title), NCBI E-utilities for PubMed (by DOI, then title), api.biorxiv.org (by DOI). `by=filename` searches by the title in the PDF's file name, ignoring the stored DOI, and adds a last candidate built from the file name and its year folder |
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
| `GET /api/graph/export` | The same graph as a file: `format=graphml` (default) or `format=csv` (zip of `nodes.csv` and `edges.csv`); `exclude_single_authors=true` drops single-paper authors |
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
| `GET /api/settings/export`, `POST /api/settings/import` (the exported JSON) | Settings that `PATCH /api/settings` accepts, as a download without API keys or tokens (admins also get the server-wide keys); import applies a file's `settings` through the same checks, refusing API keys and unknown keys |
| `GET /api/maintenance`, `PUT /api/maintenance/schedule` `{hour, nightly[], keep_backups?, trash_days? (0-120)}`, `POST /api/maintenance/{op}/run` | Admin only. Maintenance operations (`duplicates`, `complete-metadata`, `pdf-check`, `backup`, `clean-authors`, `empty-trash`) with their last result and running job; the nightly hour (server local time) and ticked operations; start one as job `maint-<op>` over every library (409 while it runs) |
| `GET /api/maintenance/backups`, `GET`/`DELETE /api/maintenance/backups/{library}/{name}` | Admin only. Database backups the `backup` operation keeps in each library's `maintenance/backups/`: list, download, delete |
| `GET`/`PUT /api/maintenance/complete-metadata/options` `{gaps[], sources[]}` | Admin only. Which gaps (`title`, `authors`, `date`, `abstract`, `journal`, `doi`) make a new paper incomplete, and which sources (`arxiv`, `biorxiv`, `crossref`, `pubmed`) are asked, in order; at least one of each |
| `GET /api/maintenance/pdf-check` | Admin only. Last `pdf-check` report per library: missing PDF files and files no paper points at (lists capped at 500, counts complete) |
| `GET /api/duplicates`, `POST /api/duplicates/merge` `{winner, loser}`, `POST /api/duplicates/dismiss` `{source_ids}` | Groups of papers with identical PDF files from the last `duplicates` run in this library; `paper merge` keeps the winner; dismissed groups stay hidden on later runs |
| `GET /api/metadata-review`, `POST /api/metadata-review/remove` `{source_ids}` | Papers `complete-metadata` could not complete in this library (fixed or deleted ones drop out); take papers off the list |
| `GET /api/settings`, `PATCH /api/settings` | `settings get`, `settings update`, limited to an allowlist (storage cap, TeX rendering, contact addresses, home feed, search history, full-text worker, AI and MCP settings); API keys are write-only |
| `GET /api/ai/models`, `POST /api/ai/test`, `GET /api/ai/schemas` | Provider model list, connection test, the JSON Schema and example each AI action uses (409 while AI is off) |
| `POST /api/ai/tags/{id}`, `POST /api/ai/summary/{id}?pdf=`, `POST /api/ai/cleanup/{id}` | AI tag suggestions, summary, metadata cleanup; previews only, nothing is written |
| `GET /api/mcp`, `POST /api/mcp/token`, `DELETE /api/mcp/token` | MCP status, create (shown once) or revoke the access token |
| `POST/GET/DELETE /mcp` | MCP Streamable HTTP endpoint (bearer token; see [MCP server](../mcp.md)) |


Paper ids are linXiv source ids such as `arxiv:1706.03762`. Old-style arXiv ids keep their slash: `/api/papers/arxiv:hep-th/9901001`.
