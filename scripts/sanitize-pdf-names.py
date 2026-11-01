#!/usr/bin/env python3
"""Rename the PDFs under a folder to plain ASCII file names before importing them.

Run it on the machine that holds the folder, on a folder linXiv does not know
yet (before scripts/bulk-import.sh or an upload). linXiv stores the path of
each PDF it links; renaming a linked file loses that paper's PDF, so the script
refuses a folder inside a linXiv data dir unless --force is given.

  Names keep [A-Za-z0-9._-] only, spaces become "_". Greek letters are spelled
  out, dashes become "-", quotes are dropped, other non-ASCII letters are
  transliterated or dropped. ".PDF" becomes ".pdf"; a file with no extension
  that starts with %PDF- gets ".pdf". Two files that clean to the same name in
  one folder get _2, _3, ...; nothing is overwritten. Folders keep their names.
  --apply also deletes macOS junk (.DS_Store, "._*" files) and writes a
  manifest that --undo replays backwards.

Standard library only (Python 3.8+). See docs/sanitize-pdf-names.md.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

USAGE = """\
Usage: sanitize-pdf-names.py [options] <dir>
       sanitize-pdf-names.py --undo MANIFEST <dir>

Options:
  --apply              Rename the files (default: dry run, nothing changes)
  --undo MANIFEST      Reverse the renames listed in a manifest from --apply
  --force              Run inside a linXiv data dir anyway (breaks PDF links)
  --log FILE           Log file (default ./sanitize-pdf-names-<date>-<time>.log)
  -h, --help           Show this help

Run it on a folder before importing it. --apply writes
<dir>/rename-manifest-<date>-<time>.tsv for --undo.
"""

GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ζ": "zeta",
    "η": "eta", "θ": "theta", "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu",
    "ν": "nu", "ξ": "xi", "ο": "omicron", "π": "pi", "ρ": "rho", "σ": "sigma", "ς": "sigma",
    "τ": "tau", "υ": "upsilon", "φ": "phi", "χ": "chi", "ψ": "psi", "ω": "omega",
}  # fmt: skip
GREEK.update({k.upper(): v.capitalize() for k, v in GREEK.items() if k != "ς"})
GREEK["µ"] = "mu"  # micro sign

DASHES = "‐‑‒–—―−⁃"
DROP = "'\"‘’‚‛“”„‟′″ʹʺ`´™®©­​‌‍﻿"
SPECIAL = {
    "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o", "Ø": "O",
    "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "þ": "th", "ð": "d", "&": "and",
}  # fmt: skip

# linXiv's database: a folder holding it, or any folder under it, is a library.
LIBRARY_MARK = "papers.db"
MAX_STEM_BYTES = 200
MANIFEST_GLOB = "rename-manifest-*.tsv"


class Log:
    """Print to stdout and append to the log file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.file = path.open("a", encoding="utf-8")

    def __call__(self, line: str = "") -> None:
        print(line)
        self.file.write(line + "\n")
        self.file.flush()


def clean_stem(stem: str) -> str:
    out = []
    for ch in stem:
        if ch in GREEK:
            out.append(GREEK[ch])
        elif ch in DASHES:
            out.append("-")
        elif ch in DROP:
            continue
        elif ch in SPECIAL:
            out.append(SPECIAL[ch])
        else:
            out.append(ch)
    s = unicodedata.normalize("NFKD", "".join(out))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    s = re.sub(r"[_.]*-[_.-]*", "-", s)  # "a_-_b", "a--b" -> "a-b"
    s = re.sub(r"_+", "_", s)
    s = re.sub(r"\.{2,}", ".", s)
    s = s.strip("_.-")
    return s[:MAX_STEM_BYTES].rstrip("_.-") or "unnamed"


def is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def move(src: Path, dst: Path) -> None:
    """Rename; a case-only change goes through a temporary name (case-insensitive disks)."""
    if src.name.lower() == dst.name.lower():
        tmp = src.with_name(src.name + ".renaming")
        src.rename(tmp)
        tmp.rename(dst)
    else:
        src.rename(dst)


def library_of(root: Path) -> Path | None:
    """The linXiv data dir `root` is in (itself or a parent holding papers.db), if any."""
    for folder in (root, *root.parents):
        if (folder / LIBRARY_MARK).is_file():
            return folder
    return None


def plan(root: Path, skip: set[Path]) -> tuple[list[tuple[Path, Path]], list[Path], list[Path]]:
    renames: list[tuple[Path, Path]] = []
    junk: list[Path] = []
    skipped: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        d = Path(dirpath)
        # Names present now, lowercased (exFAT and APFS ignore case); freed as files move away.
        taken = {n.lower() for n in filenames}
        for name in sorted(filenames):
            p = d / name
            if name == ".DS_Store" or (name.startswith("._") and not is_pdf(p)):
                junk.append(p)
                continue
            if name.startswith(".") or p.resolve() in skip or p.match(MANIFEST_GLOB):
                continue
            if name.lower().endswith(".pdf"):
                stem = name[:-4]
            elif is_pdf(p):
                stem = name
            else:
                skipped.append(p)
                continue
            new = clean_stem(stem) + ".pdf"
            if new == name:
                continue
            base, n = new[:-4], 2
            while new.lower() in taken and new.lower() != name.lower():
                new = f"{base}_{n}.pdf"
                n += 1
            taken.discard(name.lower())
            taken.add(new.lower())
            renames.append((p, d / new))
    return renames, junk, skipped


def rel(p: Path, root: Path) -> str:
    return str(p.relative_to(root))


def do_undo(root: Path, manifest: Path, log: Log) -> int:
    rows = [
        ln.split("\t")
        for ln in manifest.read_text(encoding="utf-8").splitlines()
        if ln.count("\t") == 1
    ]
    failed = 0
    for old, new in reversed(rows):
        src, dst = root / new, root / old
        if not src.exists():
            log(f"SKIP   {new} (missing)")
            failed += 1
        elif dst.exists() and not same_file(src, dst):
            log(f"SKIP   {new} -> {old} (target exists)")
            failed += 1
        else:
            move(src, dst)
            log(f"UNDO   {new} -> {old}")
    log(f"undone: {len(rows) - failed}, skipped: {failed}")
    return 1 if failed else 0


def die(msg: str) -> int:
    print(f"sanitize-pdf-names: {msg}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(add_help=False, usage=argparse.SUPPRESS)
    ap.add_argument("root", nargs="?")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", metavar="MANIFEST")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--log", metavar="FILE")
    ap.add_argument("-h", "--help", action="store_true")
    try:
        args, extra = ap.parse_known_args(argv)
    except SystemExit:
        return die("bad arguments (see --help)")
    if args.help:
        print(USAGE, end="")
        return 0
    if extra:
        return die(f"unknown argument: {extra[0]} (see --help)")
    if not args.root:
        return die("a folder is required (see --help)")
    root = Path(args.root).resolve()
    if not root.is_dir():
        return die(f"not a directory: {root}")
    library = library_of(root)
    if library and not args.force:
        return die(
            f"{root} is inside the linXiv library at {library}. Renaming its files would"
            " unlink their papers' PDFs. Run it on a folder before importing it, or add"
            " --force."
        )

    log_path = Path(args.log or time.strftime("sanitize-pdf-names-%Y%m%d-%H%M%S.log")).resolve()
    log = Log(log_path)
    mode = "undo" if args.undo else "apply" if args.apply else "dry run"
    log(f"sanitize-pdf-names {mode}: {root}")
    if library:
        log(f"WARN   inside the linXiv library at {library} (--force)")

    if args.undo:
        manifest = Path(args.undo)
        if not manifest.exists() and (root / manifest).exists():
            manifest = root / manifest
        if not manifest.is_file():
            return die(f"manifest not found: {args.undo}")
        return do_undo(root, manifest, log)

    renames, junk, skipped = plan(root, {Path(__file__).resolve(), log_path})
    for old, new in renames:
        log(f"RENAME {rel(old, root)} -> {rel(new, root)}")
    for p in junk:
        log(f"DELETE {rel(p, root)}")
    for p in skipped:
        log(f"SKIP   {rel(p, root)} (not a PDF)")
    log(
        f"{len(renames)} rename(s), {len(junk)} macOS junk file(s) to delete,"
        f" {len(skipped)} non-PDF skipped"
    )

    if not args.apply:
        log("dry run: nothing changed. Re-run with --apply.")
        log(f"log: {log_path}")
        return 0

    manifest = root / time.strftime("rename-manifest-%Y%m%d-%H%M%S.tsv")
    failed = 0
    with manifest.open("w", encoding="utf-8") as m:
        for old, new in renames:
            if new.exists() and not same_file(old, new):
                log(f"FAIL   {rel(old, root)}: {new.name} appeared meanwhile")
                failed += 1
                continue
            try:
                move(old, new)
            except OSError as e:
                log(f"FAIL   {rel(old, root)}: {e}")
                failed += 1
                continue
            m.write(f"{rel(old, root)}\t{rel(new, root)}\n")
            m.flush()
            log(f"OK     {rel(old, root)} -> {rel(new, root)}")
    for p in junk:
        p.unlink(missing_ok=True)
    log(f"renamed {len(renames) - failed}, failed {failed}, deleted {len(junk)} macOS junk file(s)")
    log(f"manifest: {manifest} (undo: --undo {manifest.name} {root})")
    log(f"log: {log_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
