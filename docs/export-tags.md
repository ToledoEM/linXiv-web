# Exporting tags to a CSV

`scripts/export-tags.sh` writes every paper's tags to a CSV with one row per paper per tag. Run it on the machine that hosts the linXiv-web container; it calls the server at `http://127.0.0.1:8086`, the port `docker-compose.yml` publishes.

Needs `curl` and `jq`.

## Getting the script onto the server

Copy it next to your `docker-compose.yml`:

```sh
scp scripts/export-tags.sh server:linxiv-web/
ssh server 'chmod +x linxiv-web/export-tags.sh'
```

## Usage

```sh
./export-tags.sh                     # writes ./paper-tags-<date>-<time>.csv
./export-tags.sh --out tags.csv      # writes tags.csv
./export-tags.sh --help
```

## Output

```csv
source_id,tag
"2401.01234","RNA-seq"
"2401.01234","transcriptomics"
```

`source_id` is the key the tag endpoints take (`/api/papers/{source_id}/tags`), so you can use the file to put tags back. Papers without tags have no rows, and a tag repeated on one paper is written once. The script builds the CSV in a temp dir and moves it into place at the end, so a failed run leaves no partial file. When it finishes it prints the row count, paper count and output path to stderr.

## Password

When the server has auth off, the script does not log in. When it has a password, the script reads it from the file named in `LINXIV_WEB_PASSWORD_FILE`, or asks for it on the terminal:

```sh
LINXIV_WEB_PASSWORD_FILE=/path/to/password.txt ./export-tags.sh
```

Without a terminal and without `LINXIV_WEB_PASSWORD_FILE`, the script stops. It also stops if first-run setup is not done; set the password in the web UI first.

The script sends the session cookies as headers, so it works over plain HTTP even with `LINXIV_WEB_COOKIE_SECURE=true`. If the session is lost during a run (a container restart, for example), it logs in again once and retries.

## Exit codes

- `0`: CSV written.
- `2`: bad argument, missing `curl` or `jq`, server unreachable, login failed, or a paper list request failed. The message on stderr gives the reason.
