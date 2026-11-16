#!/bin/sh
# Replace the tags of the papers listed in a CSV with the tags the CSV gives
# them, straight in papers.db. Run it on the machine that hosts the linXiv-web
# container, from the folder with its docker-compose.yml.
#
#   The CSV has one row per paper per tag (source_id,new_tag, or source_id,tag
#   as scripts/export-tags.sh writes it). A paper's rows are its whole new tag
#   set: tags it has now that the CSV does not list are removed. Papers not in
#   the CSV keep their tags. A `reading-list` tag already on a paper is kept.
#
#   One throwaway container runs the change in a single transaction, so either
#   every paper gets its new tags or nothing changes. The container must be
#   stopped for a real run; papers.db is backed up first. --dry-run only reads
#   and may run while the server is up.
#
# See docs/import-tags.md.
set -eu

usage() {
  cat <<'EOF'
Usage: import-tags.sh [options] <csv>

Options:
  --dry-run            Show what would change, then stop (read only; the
                       container may keep running)
  --compose-dir DIR    Folder with the docker-compose.yml (default .)
  --service NAME       Compose service name (default linxiv-web)
  --log FILE           Log file (default ./import-tags-<date>-<time>.log)
  -h, --help           Show this help

CSV: header source_id,new_tag (or source_id,tag), one row per paper per tag.
Needs docker compose. A real run needs the service stopped:
  docker compose stop linxiv-web
EOF
}

die() { echo "import-tags: $*" >&2; exit 2; }

COMPOSE_DIR=.
SERVICE=linxiv-web
LOG=
DRY_RUN=0
CSV=

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --compose-dir) COMPOSE_DIR=${2:?--compose-dir needs a value}; shift 2 ;;
    --service) SERVICE=${2:?--service needs a value}; shift 2 ;;
    --log) LOG=${2:?--log needs a value}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) die "unknown option: $1 (see --help)" ;;
    *) [ -z "$CSV" ] || die "only one CSV, got '$CSV' and '$1'"; CSV=$1; shift ;;
  esac
done
[ -z "$CSV" ] && [ $# -gt 0 ] && CSV=$1
[ -n "$CSV" ] || { usage >&2; exit 2; }
[ -f "$CSV" ] || die "no such file: $CSV"
CSV=$(cd "$(dirname "$CSV")" && pwd)/$(basename "$CSV")
[ -n "$LOG" ] || LOG="./import-tags-$(date +%Y%m%d-%H%M%S).log"
case "$LOG" in /*) ;; *) LOG=$(pwd)/$LOG ;; esac
command -v docker >/dev/null 2>&1 || die "docker not found"

cd "$COMPOSE_DIR" || die "no such directory: $COMPOSE_DIR"
if [ "$DRY_RUN" = 0 ] && [ -n "$(docker compose ps -q --status running "$SERVICE")" ]; then
  die "$SERVICE is running; stop it first: docker compose stop $SERVICE (or use --dry-run)"
fi

: > "$LOG"
echo "import-tags: $CSV$( [ "$DRY_RUN" = 1 ] && echo ' (dry run)')" | tee -a "$LOG"

# Runs inside the container (python3 -c), as the image user, so papers.db and
# the backup keep their owner. The CSV is mounted read-only at /import/tags.csv.
HELPER=$(cat <<'PY'
import csv, json, os, sqlite3, sys, time
from pathlib import Path

DATA = Path(os.environ.get("LINXIV_DATA_DIR", "/data"))
DB = DATA / "papers.db"
CSV = Path("/import/tags.csv")
DRY = os.environ.get("DRY_RUN") == "1"
KEEP = {"reading-list"}   # internal reading-list marker, never removed

# SQLite NOCASE folds ASCII letters only; dedupe the same way TAG does.
_FOLD = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
def nocase(s):
    return s.translate(_FOLD)

def out(*parts):
    print(" ".join(str(p) for p in parts), flush=True)

def abort(msg):
    out("ABORT", msg)
    sys.exit(1)

# Same encoding as the CLI's list_to_sql (serde_json::to_string).
def to_json(tags):
    return json.dumps(tags, ensure_ascii=False, separators=(",", ":"))

def from_json(s):
    if not s:
        return []
    try:
        v = json.loads(s)
    except ValueError:
        return None
    return v if isinstance(v, list) else None

NEED = {
    "PAPER": {"PAPER_ID", "SOURCE_ID", "VERSION"},
    "PAPER_META": {"PAPER_ID", "TAGS"},
    "TAG": {"TAG_FK", "TAG"},
    "PAPER_TO_TAG": {"PAPER_ID", "SOURCE_ID", "VERSION", "TAG_FK"},
    "PROJECT_TO_TAG": {"TAG_FK"},
}

UNUSED = ("SELECT COUNT(*) FROM TAG t "
          "WHERE NOT EXISTS (SELECT 1 FROM PAPER_TO_TAG p WHERE p.TAG_FK = t.TAG_FK) "
          "AND NOT EXISTS (SELECT 1 FROM PROJECT_TO_TAG j WHERE j.TAG_FK = t.TAG_FK)")


def read_csv():
    with open(CSV, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        cols = r.fieldnames or []
        col = "new_tag" if "new_tag" in cols else "tag" if "tag" in cols else None
        if "source_id" not in cols or col is None:
            abort(f"CSV header must be source_id,new_tag or source_id,tag (got {','.join(cols)})")
        want, rows = {}, 0
        for row in r:
            rows += 1
            sid = (row.get("source_id") or "").strip()
            tag = (row.get(col) or "").strip()
            if not sid or not tag:
                continue
            tags = want.setdefault(sid, [])
            if all(nocase(t) != nocase(tag) for t in tags):
                tags.append(tag)
    return want, rows


def main():
    if not DB.is_file():
        abort(f"{DB} not found")
    want, rows = read_csv()
    out(f"CSV: {rows} rows, {len(want)} papers, "
        f"{len({nocase(t) for ts in want.values() for t in ts})} distinct tags")

    uri = f"file:{DB}?mode=ro" if DRY else f"file:{DB}"
    conn = sqlite3.connect(uri, uri=True, timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 30000")

    missing = []
    for table, cols in NEED.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if not have:
            missing.append(table)
        else:
            missing += [f"{table}.{c}" for c in sorted(cols - have)]
    if missing:
        abort("papers.db schema is not the one this script knows; missing " + ", ".join(missing))

    # Every version of every paper, trash included: sid -> [(paper_id, version, json)].
    versions = {}
    for pid, sid, ver, tags in conn.execute(
            "SELECT p.PAPER_ID, p.SOURCE_ID, p.VERSION, m.TAGS FROM PAPER p "
            "LEFT JOIN PAPER_META m ON m.PAPER_ID = p.PAPER_ID ORDER BY p.SOURCE_ID, p.VERSION"):
        versions.setdefault(sid, []).append((pid, ver, tags))
    links = {}
    for pid, fk in conn.execute("SELECT PAPER_ID, TAG_FK FROM PAPER_TO_TAG"):
        links.setdefault(pid, []).append(fk)

    fk_cache = {}
    def tag_fk(label, create=False):
        if label in fk_cache:
            return fk_cache[label]
        row = conn.execute("SELECT TAG_FK FROM TAG WHERE TAG = ? COLLATE NOCASE LIMIT 1",
                           (label,)).fetchone()
        if row:
            fk_cache[label] = row[0]
        elif create:
            fk_cache[label] = conn.execute("INSERT INTO TAG (TAG) VALUES (?)", (label,)).lastrowid
        return fk_cache.get(label)

    plan, skipped, same = [], 0, 0
    for sid, tags in want.items():
        vers = versions.get(sid)
        if not vers:
            out("SKIP", sid, "not in papers.db")
            skipped += 1
            continue
        current = from_json(vers[-1][2]) or []
        target = list(tags)
        for t in current:
            if isinstance(t, str) and nocase(t) in KEEP and all(nocase(x) != nocase(t) for x in target):
                target.append(t)
        # Same tags in another order count as unchanged.
        fks = [tag_fk(t) for t in target]
        unchanged = None not in fks and all(
            (js is None or sorted(from_json(js) or []) == sorted(target))
            and sorted(links.get(pid, [])) == sorted(fks)
            for pid, _, js in vers)
        if unchanged:
            same += 1
            continue
        plan.append((sid, vers, target))
        out("CHANGE", sid, f"{len(current)} -> {len(target)} tags:", " | ".join(target))

    untouched = [sid for sid, vers in versions.items()
                 if sid not in want and (from_json(vers[-1][2]) or [])]
    for sid in untouched:
        out("UNTOUCHED", sid, "has tags, not in CSV")
    new_tags = len({nocase(t) for _, _, ts in plan for t in ts if tag_fk(t) is None})

    out(f"papers: {len(plan)} to change, {same} already match, {skipped} not in papers.db, "
        f"{len(untouched)} tagged papers not in CSV (left alone); new TAG rows: {new_tags}")
    if DRY:
        out("DONE dry run, nothing changed")
        return
    if not plan:
        out("DONE nothing to change")
        return

    backup = DATA / f"papers-before-import-tags-{time.strftime('%Y%m%d-%H%M%S')}.db"
    dst = sqlite3.connect(backup)
    conn.backup(dst)
    dst.close()
    out("backup:", backup)

    conn.execute("BEGIN IMMEDIATE")
    try:
        written = 0
        for sid, vers, target in plan:
            js = to_json(target)
            conn.execute("UPDATE PAPER_META SET TAGS = ? WHERE PAPER_ID IN "
                         "(SELECT PAPER_ID FROM PAPER WHERE SOURCE_ID = ?)", (js, sid))
            fks = [tag_fk(t, create=True) for t in target]
            for pid, ver, _ in vers:
                conn.execute("DELETE FROM PAPER_TO_TAG WHERE PAPER_ID = ?", (pid,))
                conn.executemany(
                    "INSERT INTO PAPER_TO_TAG (PAPER_ID, SOURCE_ID, VERSION, TAG_FK) VALUES (?, ?, ?, ?)",
                    [(pid, sid, ver, fk) for fk in fks])
                written += len(fks)
        # Check before commit: every version row carries the new list and links.
        bad = []
        for sid, vers, target in plan:
            js = to_json(target)
            for pid, _, _ in vers:
                row = conn.execute("SELECT TAGS FROM PAPER_META WHERE PAPER_ID = ?", (pid,)).fetchone()
                n = conn.execute("SELECT COUNT(*) FROM PAPER_TO_TAG WHERE PAPER_ID = ?", (pid,)).fetchone()[0]
                if (row is not None and row[0] != js) or n != len(target):
                    bad.append(sid)
                    break
        if bad:
            raise RuntimeError(f"check failed for {len(bad)} paper(s), e.g. {bad[0]}")
        conn.execute("COMMIT")
    except Exception as e:
        conn.execute("ROLLBACK")
        abort(f"rolled back, nothing changed: {e}")

    orphans = conn.execute(UNUSED).fetchone()[0]
    out(f"DONE {len(plan)} papers changed, {written} tag links written, "
        f"{orphans} tags without papers (run Clean tags without papers); backup {backup}")


main()
PY
)

FLAG=0
docker compose run --rm --no-deps -T \
  -v "$CSV:/import/tags.csv:ro" -e "DRY_RUN=$DRY_RUN" "$SERVICE" \
  python3 -c "$HELPER" 2>&1 | tee -a "$LOG"
# The pipe hides the container's exit status; the helper's last line is DONE
# only when it finished.
tail -n 1 "$LOG" | grep -q '^DONE' || FLAG=1

echo "log: $LOG"
if [ "$FLAG" = 1 ]; then
  echo "import-tags: failed; see the log" >&2
  exit 1
fi
if grep -q '^DONE [0-9]* papers changed' "$LOG"; then
  cat <<EOF
next:
  docker compose start $SERVICE
  Settings > Maintenance > Clean tags without papers (POST /api/maintenance/clean-tags/run)
  scripts/export-tags.sh, then compare with $CSV
EOF
fi
