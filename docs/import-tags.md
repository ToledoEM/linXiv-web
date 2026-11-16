# Importing tags from a CSV

!!! note "Experimental"
    This script is experimental. It writes to `papers.db` directly. Run `--dry-run` first.

`scripts/import-tags.sh` replaces the tags of the papers listed in a CSV with the tags the CSV gives them. Use it to load a tag set you cleaned up outside linXiv-web, for example after editing an [export](export-tags.md).

Run it on the machine that hosts the linXiv-web container, from the folder with your `docker-compose.yml`. It needs `docker compose`; everything else runs in a throwaway container from the linXiv-web image.

## Getting the script onto the server

Copy it next to your `docker-compose.yml`, with the CSV:

```sh
scp scripts/import-tags.sh tags.csv server:linxiv-web/
ssh server 'chmod +x linxiv-web/import-tags.sh'
```

## CSV

One row per paper per tag. The header is `source_id,new_tag`, or `source_id,tag` as `export-tags.sh` writes it, so an export can be imported back.

```csv
source_id,new_tag
2401.01234,RNA-seq
2401.01234,transcriptomics
```

- A paper's rows are its whole new tag set. Tags the paper has now that the CSV does not list are removed.
- Papers that are not in the CSV keep their tags.
- A `reading-list` tag already on a paper is kept.
- Tags are trimmed and empty ones dropped. Two tags on one paper that differ only in case count as one; the first spelling is kept.
- The script logs a `source_id` that is not in the library as `SKIP` and moves on.

## Usage

```sh
./import-tags.sh --dry-run tags.csv          # show what would change; the server can stay up
docker compose stop linxiv-web
./import-tags.sh tags.csv                    # replace the tags
docker compose start linxiv-web
```

Options:

| Option | Default | |
|---|---|---|
| `--dry-run` | off | Read only. Lists each paper that would change and the totals, then stops. Works while the server runs. |
| `--compose-dir DIR` | `.` | Folder with the `docker-compose.yml`. |
| `--service NAME` | `linxiv-web` | Compose service name. |
| `--log FILE` | `./import-tags-<date>-<time>.log` | Log file. |

A real run refuses to start while the service is running, so the server is never writing at the same time.

## What it changes

linXiv keeps each paper's tags in two places, and the script updates both for every version of the paper, trashed papers included:

- the tag list on the paper's metadata, which the web UI and the API read;
- the paper-to-tag links, which tag counts and tag search use.

A tag the library does not have yet is created. All of it runs in one transaction, so a failed check leaves the database as it was. A paper that already has exactly the tags the CSV gives it is left alone, so running the same CSV again changes nothing.

Each line of the log is one of:

- `CHANGE <source_id> <old count> -> <new count> tags: …`
- `SKIP <source_id> not in papers.db`
- `UNTOUCHED <source_id> has tags, not in CSV`
- a totals line, then `DONE …` on success or `ABORT …` with the reason.

## Backup and undo

Before it writes, a real run copies the database to `papers-before-import-tags-<date>-<time>.db` in the data folder. To undo, stop the container and put that file back as `papers.db`.

## After the import

1. Start the container.
2. Remove tags that no paper uses any more: **Settings → Maintenance → Clean tags without papers**, or `POST /api/maintenance/clean-tags/run`.
3. Run [`export-tags.sh`](export-tags.md) and compare its output with your CSV.

## Exit codes

- `0`: done, or dry run finished.
- `1`: the import stopped (`ABORT` in the log). Nothing was changed.
- `2`: bad argument, missing CSV or `docker`, or the service is still running.
