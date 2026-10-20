# Development

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

The FastAPI server lives in `server/`. The CLI subprocess wrapper is `app/cli.py`, the AI provider client `app/ai.py`, and the MCP bridge `app/mcp_bridge.py`. The Vite, React and TypeScript frontend lives in `web/`. The `Dockerfile` builds the CLI and MCP server first, then the SPA, then the Python runtime image.

Branch and commit conventions match linXiv's; see `CONTRIBUTING.md` in the repository.

## Running from a checkout

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

For the prebuilt image, use [Self-hosting](self-hosting.md) instead.

## This documentation site

The site is built with [Zensical](https://zensical.org), managed by uv from the repository root. Pages live in `docs/`, and `zensical.toml` holds the navigation.

```sh
uv sync                  # install Zensical into .venv
uv run zensical serve    # preview at http://localhost:8000, rebuilds on save
uv run zensical build    # write the static site to site/
```

`site/` is ignored by git.
