# Server scripts

Command-line helpers for jobs that are too big for the web UI. Copy one to the machine that hosts the linXiv-web container (or holds your PDFs), make it executable, and start with `--help`. The shell scripts need `sh`, `curl` and `jq`; the Python one needs `python3`.

| Script | What it does | Page |
|---|---|---|
| `scripts/sanitize-pdf-names.py` | Renames the PDFs under a folder to plain ASCII file names, with a dry run first and an undo manifest. Run it before importing the folder. | [Sanitize PDF file names](sanitize-pdf-names.md) |
| `scripts/bulk-import.sh` | Imports a folder of PDFs that is already on the server: through the running server, or offline with the container stopped, copying, moving or linking the files where they are. | [Bulk PDF import](bulk-import.md) |
| `scripts/bulk-ai-tags.sh` | Asks the AI set up in Settings → AI for tags for every paper that has none (or every paper with `--all`) and adds them. | [Bulk AI tags](bulk-ai-tags.md) |
| `scripts/export-tags.sh` | Writes every paper's tags to a CSV, one row per paper per tag, that can be used to put the tags back. | [Export tags](export-tags.md) |

For a large collection, the usual order is:

1. `sanitize-pdf-names.py` on the folder (dry run, then `--apply`).
2. `bulk-import.sh` on the same folder.
3. `bulk-ai-tags.sh` for the papers that came in without tags.
4. `export-tags.sh` to keep a copy of the tags.

Every script has a dry run or changes nothing until told to, and each writes a log next to where it runs.
