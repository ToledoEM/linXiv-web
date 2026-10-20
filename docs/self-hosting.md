# Self-hosting linXiv-web with Docker

This guide runs linXiv-web on your own machine or home server from the prebuilt container image. For development and building from source, see [Development](development.md).

The current release is the `release` branch, published as the image tag used below. `main` may contain changes that are not released yet.

## Requirements

- Docker with Docker Compose v2 (`docker compose`), on Linux, macOS or Windows.
- An `amd64` or `arm64` machine. The image is published for both.
- Two directories on the host: one for the library database, one for PDFs.

The image bundles the `linxiv` CLI and `linxiv-mcp`, built from linXiv v0.7.0. Do not point linXiv-web at a data directory that the linXiv desktop app or `linxiv-headless` also uses: linXiv expects one process per library.

## Quick start

```sh
mkdir -p linxiv-web/data linxiv-web/pdfs
cd linxiv-web
```

On Linux, the container runs as uid 1000 and must be able to write both directories:

```sh
sudo chown 1000:1000 data pdfs
```

Create `docker-compose.yml`:

```yaml
services:
  linxiv-web:
    image: ghcr.io/toledoem/linxiv-web:0.1.2
    container_name: linxiv-web
    restart: unless-stopped
    env_file:
      - path: .env
        required: false
    ports:
      # 127.0.0.1 = this machine only. Use 0.0.0.0 to reach it from the LAN.
      - "${LINXIV_WEB_BIND:-127.0.0.1}:${LINXIV_WEB_PUBLISH_PORT:-8086}:8000"
    volumes:
      # Long syntax: a missing host directory is an error, not a silently created empty one.
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

Start it:

```sh
docker compose up -d
docker compose logs -f linxiv-web
```

Open http://127.0.0.1:8086.

The image is tagged with the linXiv-web version (`0.1.2`) and `latest`; pin the version to choose when you update. The image is public: no `docker login` needed.

## First-run setup

With no password configured, the server starts in setup mode and logs:

```
linxiv-web: no password set; first-run setup is open on 0.0.0.0:8000. The first visitor creates the admin password.
```

The first person to open the web UI creates the admin password (at least 8 characters) and is logged in. Until then every API call is refused. Do the setup before you publish the port to a network you don't trust.

After the password, the wizard offers optional steps, each with Skip:

1. Contact emails for arXiv, Crossref and OpenAlex, and an NCBI (PubMed) API key.
2. Theme and light/dark mode (stored in the browser).
3. AI provider, model and key (off by default).
4. Home feed URL and PDF folder layout.

Everything in the wizard can be changed later in Settings.

The password hash is stored in `data/linxiv-web-auth.json` (mode 0600). linXiv-web never stores the password itself.

### Setting the password in `.env` instead

A password from the environment always wins over the stored one, and setup never opens. Generate an argon2 hash:

```sh
docker run --rm -e PASSWORD='your-password' --entrypoint python \
  ghcr.io/toledoem/linxiv-web:0.1.2 -m app hash-password
```

Put it in `.env` next to `docker-compose.yml`, in single quotes (the hash contains `$`):

```sh
LINXIV_WEB_PASSWORD_HASH='$argon2id$v=19$m=65536,t=3,p=4$...'
```

### Changing or resetting the password

Logged in: **Settings → Server & data → Login** changes the password and logs out every other browser. "Log out other sessions" there ends all sessions except yours.

Forgotten password: set a new one from the server, no restart needed (every browser is logged out):

```sh
docker compose exec linxiv-web python -m app reset-password
```

Or remove the stored password so the next visitor runs first-run setup again (the library is untouched):

```sh
docker compose down
rm data/linxiv-web-auth.json
docker compose up -d
```

A password set with `LINXIV_WEB_PASSWORD_HASH` / `LINXIV_WEB_PASSWORD` always wins; change it in `.env` instead.

## Logging in

Tick **Remember me on this browser** to stay logged in for 90 days (`LINXIV_WEB_REMEMBER_DAYS` changes this). Without it, the login ends when the browser closes, and after 14 days at most.

Sessions are kept in `data/linxiv-web-state.db`, so restarting or updating the container keeps you logged in.

## Where your data lives

| Host directory | Container | Contents |
|---|---|---|
| `data/` (`LINXIV_WEB_DATA_HOST`) | `/data` | `papers.db` (library), `user_settings.json` (linXiv settings, including API keys entered in Settings), `linxiv-web-auth.json` (admin password hash), `linxiv-web-state.db` (sessions, login throttle) |
| `pdfs/` (`LINXIV_WEB_PDF_HOST`) | `/pdfs` | PDFs, flat or in year/journal subfolders (Settings → Library → PDF folders) |

Keep `data/` on a local disk: SQLite over network shares or exFAT is unreliable. `pdfs/` may live on a NAS or external drive.

To use other locations, set them in `.env` (both directories must exist):

```sh
LINXIV_WEB_DATA_HOST=/srv/linxiv/data
LINXIV_WEB_PDF_HOST=/mnt/nas/papers
```

## Reaching it from other machines

Set in `.env`:

```sh
LINXIV_WEB_BIND=0.0.0.0
LINXIV_WEB_PUBLISH_PORT=8086
```

then `docker compose up -d`, and open `http://<server-ip>:8086`. This is plain HTTP: use it on a trusted LAN, or put HTTPS in front.

### HTTPS with a reverse proxy

Keep `LINXIV_WEB_BIND=127.0.0.1` and let the proxy on the same host forward to it. Set in `.env`:

```sh
LINXIV_WEB_COOKIE_SECURE=true
LINXIV_WEB_HSTS=true   # optional: browsers stop using plain HTTP for this host
```

The proxy must pass the original `Host` header: linXiv-web rejects writes whose `Origin` doesn't match the host it sees.

linXiv-web serves only loopback, private LAN and link-local addresses unless `LINXIV_WEB_ALLOW_EXTERNAL=true`. Behind a proxy it sees the proxy's address, so everyone passes as the proxy. To see real client addresses, list the proxy in `LINXIV_WEB_TRUSTED_PROXIES` (from inside the container it usually shows up as the Docker gateway, e.g. `172.17.0.1`, or the whole `172.16.0.0/12`) and make it send `X-Forwarded-For`; then internet clients need `LINXIV_WEB_ALLOW_EXTERNAL=true`.

Caddy (passes `Host` by default, gets certificates itself):

```
papers.example.org {
    reverse_proxy 127.0.0.1:8086
}
```

nginx:

```nginx
server {
    listen 443 ssl;
    server_name papers.example.org;
    # ssl_certificate / ssl_certificate_key ...
    client_max_body_size 200m;   # match LINXIV_WEB_MAX_UPLOAD_MB

    location / {
        proxy_pass http://127.0.0.1:8086;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;  # long searches, imports, AI calls
    }
}
```

## Configuration

Settings changed in the web UI are stored in `data/`. Environment variables go in `.env` and need `docker compose up -d` to apply. The most useful ones:

| Variable | Default | Purpose |
|---|---|---|
| `LINXIV_WEB_BIND` / `LINXIV_WEB_PUBLISH_PORT` | `127.0.0.1` / `8086` | Where compose publishes the port |
| `LINXIV_WEB_DATA_HOST` / `LINXIV_WEB_PDF_HOST` | `./data` / `./pdfs` | Host directories |
| `LINXIV_WEB_PASSWORD_HASH` | none | Admin password hash; skips first-run setup |
| `LINXIV_WEB_REMEMBER_DAYS` | `90` | Login lifetime with Remember me |
| `LINXIV_WEB_COOKIE_SECURE` | `false` | `true` behind HTTPS |
| `LINXIV_WEB_ALLOW_EXTERNAL` | `false` | Serve public IP addresses (else 403) |
| `LINXIV_WEB_TRUSTED_PROXIES` | none | Proxy IPs/CIDRs whose `X-Forwarded-For` is believed |
| `LINXIV_WEB_MAX_UPLOAD_MB` | `200` | Upload size cap |
| `CROSSREF_MAILTO`, `NCBI_API_KEY`, `GEMINI_API_KEY`, … | none | Override the values entered in Settings |

The full list is in [Admin Server Configuration](reference/configuration.md).

## Importing many PDFs

To import a folder of PDFs that is already on the server, without the web UI, use `scripts/bulk-import.sh`. See [bulk-import.md](bulk-import.md).

## Backups

- Database only: Settings → Server & data → Backup downloads a copy of `papers.db` and can import or restore one. It does not include PDFs.
- Everything: stop the container and copy both directories:

  ```sh
  docker compose down
  tar czf linxiv-backup-$(date +%F).tar.gz data pdfs
  docker compose up -d
  ```

## Updating

Change the image tag in `docker-compose.yml` to the new version, then:

```sh
docker compose pull
docker compose up -d
```

Reload open browser tabs with Cmd/Ctrl+Shift+R so they pick up the new interface.

## Building the image yourself

Instead of pulling from GHCR, compose can build from the git repository. Replace the `image:` line with:

```yaml
    build:
      context: https://github.com/ToledoEM/linXiv-web.git#release
      args:
        LINXIV_REF: v0.7.0
    image: linxiv-web:local
```

and run `docker compose build && docker compose up -d`. The first build compiles linXiv from source and takes several minutes. To build local changes, clone the repository and use `context: ./linXiv-web` instead of the URL.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Container exits with `LINXIV_WEB_PDF_DIR=/pdfs is not writable` (or the data dir) | On Linux: `sudo chown 1000:1000 data pdfs` |
| `... does not exist (mount the PDF directory)` | Create the host directories before starting; compose won't create them |
| Container exits with `linxiv-web-auth.json is unreadable` | The stored password file is damaged: delete it and run setup again |
| `invalid password` after setting `LINXIV_WEB_PASSWORD_HASH` | Keep the hash in single quotes in `.env`; compose expands `$` otherwise |
| Writes fail with `cross-origin request rejected` behind a proxy | The proxy must forward the original `Host` header |
| `403 External requests are disabled` | The client has a public IP address: set `LINXIV_WEB_ALLOW_EXTERNAL=true`, or reach it over LAN/VPN |
| Container exits with `LINXIV_WEB_TRUSTED_PROXIES: '…' is not an IP or CIDR` | Use addresses or CIDRs, not host names |
| Old interface after an update | Hard reload with Cmd/Ctrl+Shift+R |
| Logged out after a restart | `LINXIV_WEB_SECRET_KEY` changed, or `data/linxiv-web-state.db` was deleted |
| `docker compose pull` says `denied` | Log in to ghcr.io (see Quick start) |
