# Admin Server Configuration

linXiv-web reads these environment variables, usually from the `.env` file next to `docker-compose.yml`.

| Variable | Default | Purpose |
|---|---|---|
| `LINXIV_WEB_PASSWORD_HASH` | none | argon2 hash of the login password (`python -m app hash-password`). Without it (or `LINXIV_WEB_PASSWORD`), first-run setup in the browser creates the password, stored in `<data dir>/linxiv-web-auth.json` |
| `LINXIV_WEB_PASSWORD` | none | Plain password, hashed in memory at startup (dev only) |
| `LINXIV_WEB_SECRET_KEY` | generated, kept in `<data dir>/linxiv-web-state.db` | Session signing key. Changing it logs everyone out |
| `LINXIV_WEB_COOKIE_SECURE` | `false` | Set to `true` behind HTTPS |
| `LINXIV_WEB_HSTS` | `false` | Send `Strict-Transport-Security` (1 year). Only behind HTTPS: browsers then refuse plain HTTP to this host |
| `LINXIV_WEB_REMEMBER_DAYS` | `90` | Login lifetime when "Remember me" is ticked (otherwise the login lasts until the browser closes, at most 14 days) |
| `LINXIV_WEB_DATA_DIR` | `/data` | linXiv data dir (`papers.db`). Passed to the CLI and MCP server as `LINXIV_DATA_DIR` |
| `LINXIV_WEB_PDF_DIR` | `/pdfs` | PDF directory, symlinked from `<data dir>/pdfs` |
| `LINXIV_WEB_HOST` / `LINXIV_WEB_PORT` | `0.0.0.0` / `8000` in the image | Listen address |
| `LINXIV_WEB_ALLOW_EXTERNAL` | `false` | Serve clients with public IP addresses. Off: only loopback, private LAN and link-local clients get through (others get 403) |
| `LINXIV_WEB_TRUSTED_PROXIES` | none | Comma-separated IPs/CIDRs of reverse proxies whose `X-Forwarded-For` is believed (read right to left). Unlisted proxies count as the client |
| `LINXIV_WEB_MAX_UPLOAD_MB` | `200` | Upload size cap |
| `LINXIV_WEB_TIMEOUT_LONG` / `_SHORT` | `120` / `30` | CLI timeout in seconds (search, fetch, download and import use the long one) |
| `LINXIV_BIN` / `LINXIV_MCP_BIN` | `linxiv` / `linxiv-mcp` | CLI and MCP server binaries |
| `ARXIV_MAILTO`, `CROSSREF_MAILTO`, `OPENALEX_MAILTO` | none | Contact addresses sent to those services; override the values set in Settings |
| `NCBI_API_KEY` | none | PubMed key; overrides the one set in Settings |
| `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GENAI_API_KEY_TAG_GEN` | none | AI provider keys (the last one is for the OpenAI-compatible endpoint); override the ones set in Settings |
| `LINXIV_WEB_AI_ALLOWED_HOSTS` | none | Comma-separated host names the OpenAI-compatible base URL may use. Unset: any host except cloud metadata addresses (`169.254.0.0/16`, `fd00:ec2::254`, `100.100.100.200`), which are always refused |

Keys entered in Settings are stored in the linXiv settings store. The server never sends them back to the browser, only their last 4 characters.

The Compose file also reads `LINXIV_WEB_BIND`, `LINXIV_WEB_PUBLISH_PORT`, `LINXIV_WEB_DATA_HOST` and `LINXIV_WEB_PDF_HOST` to decide where the port is published and which host folders are mounted. [Self-hosting](../self-hosting.md) explains them.
