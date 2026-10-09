# Importing a folder of PDFs on the server

Use this when the PDFs are already on the machine that runs the linXiv-web container and you don't want to upload them one by one in the browser. `scripts/bulk-import.sh` runs on that machine and imports every PDF under a directory, subfolders included.

It has two modes:

| Mode | Container | How it imports | Use it when |
|---|---|---|---|
| `api` (default) | running | uploads each file to `POST /api/pdfs/import` over `127.0.0.1` | you want the library to stay online, or run imports from cron |
| `offline` | stopped | runs `linxiv pdf import` in a one-off container, with the folder mounted read-only | very large batches, files over the upload cap, or linking every paper to a project |

Each PDF is imported the same way as Upload in the web UI: linXiv reads the metadata from the PDF and copies the file into the PDF folder. The source folder is never modified, unless you pass `--move-done`.

Don't run `docker exec linxiv-web linxiv pdf import ...` while the container is up. linXiv allows one writing process per library, and the server can only keep its own calls in order. A second `linxiv` process writing next to it can fail or leave the library inconsistent. The script avoids this: `api` mode goes through the server, and `offline` mode only runs while the server is stopped.

## Requirements

- On the server: `sh`, `curl`, `find`, `awk` and `sed` (any Linux has them), and Docker Compose v2 for `offline` mode.
- `api` mode: compose publishes the port on the server (the default `127.0.0.1:8086` works), and the admin password is set (first-run setup done, or `LINXIV_WEB_PASSWORD_HASH` in `.env`).
- `offline` mode: the PDFs must be readable by uid 1000, the user the container runs as.

## Getting the script onto the server

Copy it next to your `docker-compose.yml`:

```sh
scp scripts/bulk-import.sh server:linxiv-web/
ssh server 'chmod +x linxiv-web/bulk-import.sh'
```

Then, on the server:

```sh
cd linxiv-web
./bulk-import.sh --help
```

Check what it will pick up first:

```sh
./bulk-import.sh --dry-run /srv/inbox
```

## api mode: container running

```sh
./bulk-import.sh /srv/inbox
```

The script asks for the linXiv-web password, logs in, and uploads the files one at a time. You can keep using the web UI while it runs, though other requests wait their turn behind each import. Every file gets one line in the output and in the log file:

```
OK    2021/smith-rna.pdf -> doi:10.1038/s41586-021-03819-2
FAIL  scans/notes.pdf (400): not a PDF file
done: 1 imported, 1 failed, 2 total. Log: ./bulk-import-20261008-221500.log
```

The exit status is 0 only when every file was imported.

Options for this mode:

| Option | Effect |
|---|---|
| `--url URL` | Server address, if you changed `LINXIV_WEB_PUBLISH_PORT` (default `http://127.0.0.1:8086`) |
| `--move-done DIR` | Move each imported file to `DIR`, keeping its subfolder. A rerun then only retries the failures |
| `--index-text` | After the imports, start the job that indexes PDF text for full-text search (the same as **Index PDFs now** in Settings → Library → PDF full text) |
| `--log FILE` | Log location (default `./bulk-import-<date>-<time>.log`) |

Run it on the server itself and point it at `127.0.0.1`, not at a public HTTPS name. Over loopback, uploads skip the reverse proxy and its body size limit. The script also works when `LINXIV_WEB_COOKIE_SECURE=true`.

### Running it without a terminal (cron)

The script reads the password from the first line of the file named in `LINXIV_WEB_PASSWORD_FILE`. Keep that file readable only by you:

```sh
install -m 600 /dev/null ~/.linxiv-web-password
printf '%s\n' 'your-password' > ~/.linxiv-web-password
```

A crontab entry that imports whatever lands in an inbox every night, and moves the imported files out of it:

```
15 3 * * * cd $HOME/linxiv-web && LINXIV_WEB_PASSWORD_FILE=$HOME/.linxiv-web-password ./bulk-import.sh --move-done /srv/inbox-done --index-text /srv/inbox >> bulk-import-cron.log 2>&1
```

Five wrong passwords within five minutes lock out logins from that address for the rest of the five minutes (`429 too many login attempts`), so check the password file before you schedule it.

## offline mode: container stopped

Stop the server, import, start it again:

```sh
docker compose stop linxiv-web
./bulk-import.sh --mode offline /srv/inbox
docker compose start linxiv-web
```

The script refuses to run while the container is up. It starts one container for the whole batch, with the same image, volumes and `.env` as the server, and mounts the folder read-only at `/import`. There is no login and no upload size cap, and it is faster than `api` mode because nothing goes over HTTP.

Options for this mode:

| Option | Effect |
|---|---|
| `--project-id ID` | Link every imported paper to project `ID` (the number in the project's URL) |
| `--compose-dir DIR` | Folder that holds `docker-compose.yml`, if you run the script from elsewhere (default `.`) |
| `--service NAME` | Compose service name (default `linxiv-web`) |
| `--move-done DIR`, `--log FILE`, `--dry-run` | As in `api` mode |

Full-text indexing needs the server, so after you start the container again, click **Index PDFs now** in Settings → Library → PDF full text.

On Linux, if every file fails with a permission error, give uid 1000 read access to the folder:

```sh
sudo chmod -R a+rX /srv/inbox
```

## What to expect

Running the script twice on the same files doesn't create duplicate papers. linXiv derives each paper's id from the arXiv id or DOI it finds in the PDF, or from a hash of the file (`local:<hash>`) when it finds neither, so a second import lands on the same paper and keeps any titles, authors or tags you edited since. Every file is still uploaded again, which is why `--move-done` speeds up repeated runs.

Metadata comes from the PDF alone. Scans and PDFs without embedded metadata get thin records; the batch metadata edit in the Library can look them up in Crossref, arXiv, OpenAlex or PubMed afterwards.

In `api` mode, files over `LINXIV_WEB_MAX_UPLOAD_MB` (default 200) fail with `413 file too large`. Raise the variable in `.env` and run `docker compose up -d`, or import those files in `offline` mode. A single import that runs longer than `LINXIV_WEB_TIMEOUT_LONG` seconds (default 120) fails with a 504.

Before importing a large batch into an existing library, take a backup in Settings → Server & data → Backup.

## Troubleshooting

| Message | Fix |
|---|---|
| `cannot reach http://127.0.0.1:8086` | The container is down, or published on another port: pass `--url` |
| `first-run setup is not done` | Open the web UI once and create the password |
| `login failed (401): invalid password` | Wrong password, or a stale `LINXIV_WEB_PASSWORD_FILE` |
| `login failed (429)` | Wait five minutes after repeated wrong passwords |
| `FAIL ... (400): not a PDF file` | The file doesn't start with `%PDF-`: it is damaged, or not a PDF despite the extension |
| `FAIL ...: Could not extract PDF metadata` (offline mode) | Same as above: linXiv could not parse the file |
| `FAIL ... (413): file too large` | Raise `LINXIV_WEB_MAX_UPLOAD_MB`, or use `offline` mode |
| `linxiv-web is running; stop it first` | `offline` mode needs `docker compose stop linxiv-web` |
| `--project-id is offline mode only` | The upload route has no project option. Use `offline` mode, or add the papers to the project in the web UI afterwards |
