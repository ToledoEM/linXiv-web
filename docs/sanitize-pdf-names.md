# Cleaning up PDF file names before an import

PDF collections often have file names with spaces, accents, Greek letters, curly quotes or dashes copied from a title. Some disks, shells and sync tools handle those badly. `scripts/sanitize-pdf-names.py` renames every PDF under a folder to a plain ASCII name, so the files are easy to handle before you import them with [bulk import](bulk-import.md) or upload them.

Run it **before** the import, on a folder linXiv does not know yet. linXiv stores the path of each PDF it links. A file renamed after it was imported loses its link: the paper shows no PDF, and Server Admin → **Check PDF files** lists it as missing. This matters most for `--place in-situ` imports, which link your own files where they are.

## Requirements

- Python 3.8 or newer on the machine that holds the folder. It uses the standard library only, so nothing needs installing. Debian, Ubuntu and macOS ship a suitable `python3`.
- Write access to the folder.

The script never talks to the linXiv-web server, so the container can be running or stopped.

## Getting the script onto the server

```sh
scp scripts/sanitize-pdf-names.py server:linxiv-web/
ssh server 'chmod +x linxiv-web/sanitize-pdf-names.py'
```

Then, on the server:

```sh
cd linxiv-web
./sanitize-pdf-names.py --help
```

## Dry run

By default the script only lists what it would do:

```sh
./sanitize-pdf-names.py /mnt/usb/Papers
```

```text
sanitize-pdf-names dry run: /mnt/usb/Papers
RENAME 2019/β-cell αβ – “study”.pdf -> 2019/beta-cell_alphabeta-study.pdf
RENAME 2021/Résumé & notes.PDF -> 2021/Resume_and_notes.pdf
RENAME misc/same name.pdf -> misc/same_name_2.pdf
DELETE .DS_Store
SKIP   readme.txt (not a PDF)
3 rename(s), 1 macOS junk file(s) to delete, 1 non-PDF skipped
dry run: nothing changed. Re-run with --apply.
```

Every run also writes its output to `./sanitize-pdf-names-<date>-<time>.log`, or to the file given with `--log FILE`.

## Renaming

```sh
./sanitize-pdf-names.py --apply /mnt/usb/Papers
```

Each rename is logged as `OK` or `FAIL`. The script also writes `rename-manifest-<date>-<time>.tsv` in the folder, one `old<TAB>new` line per rename (paths relative to the folder). Keep it until you are sure about the result.

The exit code is `0` when every rename worked, `1` when one or more failed, and `2` for a bad argument or a refused folder.

## Undoing a run

```sh
./sanitize-pdf-names.py --undo rename-manifest-20261101-120000.tsv /mnt/usb/Papers
```

The script reads the manifest backwards and gives each file its old name back. A file that is missing, or whose old name is taken again, is reported as `SKIP` and left alone. Deleted macOS junk files are not restored.

## Rename rules

- Names keep `A-Z a-z 0-9 . _ -` only. Spaces and any other character become `_`, and repeated `_` collapse into one.
- Greek letters are spelled out (`β` to `beta`, `Ω` to `Omega`, the micro sign `µ` to `mu`).
- Unicode dashes become `-`. Quotes, `™ ® ©` and invisible characters are dropped. `ß æ ø ł þ &` and similar become `ss ae o l th and`. Other accented letters lose their accent (`é` to `e`); letters with no ASCII form are dropped.
- `.PDF` becomes `.pdf`. A file with no extension that starts with `%PDF-` gets `.pdf`. Other files are reported as `SKIP` and keep their names.
- When two files in one folder clean to the same name, the later ones get `_2`, `_3` and so on. Case is ignored for this, because exFAT and macOS disks treat `A.pdf` and `a.pdf` as the same file. Nothing is ever overwritten.
- Names are cut at 200 characters before `.pdf`. A name with nothing left becomes `unnamed.pdf`.
- Folder names are never changed. Hidden files (names starting with `.`) are left alone, except `.DS_Store` and `._*` AppleDouble files, which `--apply` deletes.

linXiv-web reads a title from the file name when a PDF carries none: it splits the name on `_`, and drops a trailing `_2` style suffix. The rules above keep names in that shape.

## Inside a linXiv library

The script refuses a folder that holds a `papers.db`, or sits anywhere under a folder that does, such as the PDF folder inside the linXiv data directory:

```text
sanitize-pdf-names: /srv/linxiv/data/pdfs is inside the linXiv library at /srv/linxiv/data. Renaming its files would unlink their papers' PDFs. Run it on a folder before importing it, or add --force.
```

`--force` runs it anyway and logs a `WARN` line. Only use it when you know none of the files are linked yet. A PDF folder kept on another disk (`LINXIV_WEB_PDF_HOST`) has no `papers.db` next to it, so the script can't tell it is a library: check the path yourself.

## Troubleshooting

| Message | Meaning |
|---|---|
| `a folder is required` | Give the folder as the last argument. |
| `not a directory: …` | The path does not exist or is a file. |
| `… is inside the linXiv library at …` | See [Inside a linXiv library](#inside-a-linxiv-library). |
| `FAIL … appeared meanwhile` | Another program created a file with the new name during the run. Run the script again. |
| `FAIL …: [Errno 13] Permission denied` | The folder is not writable for your user. |
| `SKIP … (target exists)` during `--undo` | The old name is taken by another file. Rename that file, then run the undo again; finished lines are skipped as missing. |
