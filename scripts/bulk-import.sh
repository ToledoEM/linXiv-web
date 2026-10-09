#!/bin/sh
# Import every PDF under a directory into linXiv-web, without the web UI.
# Run it on the machine that hosts the linXiv-web container.
#
#   api mode (default): the container keeps running; each PDF is uploaded to
#     POST /api/pdfs/import over loopback, so the server's CLI lock orders the writes.
#   offline mode: the container must be stopped; one throwaway container runs
#     `linxiv pdf import` for each file, with the directory mounted read-only.
#
#   --place copy (default): linXiv keeps its own copy; the source stays.
#   --place move: as copy, then the source file is deleted.
#   --place in-situ (offline only, folder inside the PDF folder): each paper
#     points at the file where it is; linXiv's copy is removed.
#
# See docs/BULK-IMPORT.md.
set -eu

usage() {
  cat <<'EOF'
Usage: bulk-import.sh [options] <dir>

Options:
  --mode api|offline   api (default): upload through the running server.
                       offline: run the linxiv CLI with the container stopped.
  --place copy|move|in-situ
                       copy (default): linXiv stores its own copy, source untouched.
                       move: as copy, then delete each imported source file.
                       in-situ: offline mode only, for a folder inside the PDF
                       folder; papers point at the files where they are.
  --url URL            Server URL for api mode (default http://127.0.0.1:8086)
  --compose-dir DIR    Folder with the docker-compose.yml, for offline mode (default .)
  --service NAME       Compose service name (default linxiv-web)
  --project-id ID      Link every imported paper to this project
  --move-done DIR      Move each imported file to DIR (same relative path), so a
                       rerun skips it
  --index-text         api mode: start the PDF full-text index job at the end
  --log FILE           Log file (default ./bulk-import-<date>-<time>.log)
  --dry-run            List the PDFs that would be imported, then stop
  -h, --help           Show this help

Password (api mode, only when the server has one): read from the file named in
LINXIV_WEB_PASSWORD_FILE, otherwise asked for on the terminal.
EOF
}

die() { echo "bulk-import: $*" >&2; exit 2; }

MODE=api
PLACE=copy
URL=http://127.0.0.1:8086
COMPOSE_DIR=.
SERVICE=linxiv-web
PROJECT_ID=
DONE_DIR=
INDEX_TEXT=0
LOG=
DRY_RUN=0
SRC=
PW=
PW_SET=

while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE=${2:?--mode needs a value}; shift 2 ;;
    --place) PLACE=${2:?--place needs a value}; shift 2 ;;
    --url) URL=${2:?--url needs a value}; shift 2 ;;
    --compose-dir) COMPOSE_DIR=${2:?--compose-dir needs a value}; shift 2 ;;
    --service) SERVICE=${2:?--service needs a value}; shift 2 ;;
    --project-id) PROJECT_ID=${2:?--project-id needs a value}; shift 2 ;;
    --move-done) DONE_DIR=${2:?--move-done needs a value}; shift 2 ;;
    --index-text) INDEX_TEXT=1; shift ;;
    --log) LOG=${2:?--log needs a value}; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) die "unknown option: $1 (see --help)" ;;
    *) [ -z "$SRC" ] || die "only one directory, got '$SRC' and '$1'"; SRC=$1; shift ;;
  esac
done
[ -z "$SRC" ] && [ $# -gt 0 ] && SRC=$1
[ -n "$SRC" ] || { usage >&2; exit 2; }
[ -d "$SRC" ] || die "not a directory: $SRC"
case "$MODE" in api|offline) ;; *) die "--mode must be api or offline" ;; esac
case "$PROJECT_ID" in *[!0-9]*) die "--project-id must be a number" ;; esac
case "$PLACE" in copy|move|in-situ) ;; *) die "--place must be copy, move or in-situ" ;; esac
[ "$PLACE" = copy ] || [ -z "$DONE_DIR" ] || die "--move-done only works with --place copy"
[ "$PLACE" != in-situ ] || [ "$MODE" = offline ] || die "--place in-situ needs --mode offline"

SRC=$(cd "$SRC" && pwd)
if [ -n "$DONE_DIR" ]; then
  mkdir -p "$DONE_DIR"
  DONE_DIR=$(cd "$DONE_DIR" && pwd)
  case "$DONE_DIR/" in "$SRC"/*) die "--move-done must be outside $SRC" ;; esac
fi
URL=${URL%/}
[ -n "$LOG" ] || LOG="./bulk-import-$(date +%Y%m%d-%H%M%S).log"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
trap 'exit 130' INT TERM

# Relative paths of every PDF under SRC, one per line, sorted. macOS "._*"
# AppleDouble files carry a .pdf name but are never PDFs.
(cd "$SRC" && find . -type f -iname '*.pdf' ! -name '._*' | sed 's|^\./||' | LC_ALL=C sort) > "$WORK/list"
TOTAL=$(wc -l < "$WORK/list" | tr -d ' ')

if [ "$DRY_RUN" = 1 ]; then
  cat "$WORK/list"
  echo "$TOTAL PDF(s) under $SRC; would import with --mode $MODE --place $PLACE"
  [ "$PLACE" != in-situ ] || echo "in-situ: the folder must be inside the PDF folder; checked when the import starts"
  exit 0
fi
[ "$TOTAL" -gt 0 ] || { echo "no PDFs under $SRC"; exit 0; }

: > "$LOG"
log() { printf '%s\n' "$*" | tee -a "$LOG"; }
OK=0
FAIL=0

# After a successful import: --move-done moves the source away, --place move deletes it.
move_done() {
  if [ "$PLACE" = move ]; then
    rm -f -- "$SRC/$1" || log "      could not delete $1"
    return 0
  fi
  [ -n "$DONE_DIR" ] || return 0
  mkdir -p "$DONE_DIR/$(dirname "$1")"
  mv -- "$SRC/$1" "$DONE_DIR/$1" || log "      could not move $1 to $DONE_DIR"
}

# --- api mode ---------------------------------------------------------------

# Value of one cookie from curl's jar (HttpOnly cookies carry a "#HttpOnly_" prefix).
jar_value() {
  [ -f "$WORK/jar" ] || return 0
  awk -v n="$1" -F '\t' 'NF >= 7 && $6 == n { v = $7 } END { if (v != "") print v }' "$WORK/jar"
}

# Message from a JSON error body ({"detail": "..."}), or the raw body.
detail() {
  sed -n 's/.*"detail" *: *"\([^"]*\)".*/\1/p' "$1" | head -n 1 | grep . || head -c 300 "$1"
}

login() {
  me=$(curl -sS "$URL/api/me") || die "cannot reach $URL (is the container running?)"
  case "$me" in
    *'"setup_required":true'*) die "first-run setup is not done; set the password in the web UI first" ;;
    *'"auth_enabled":false'*) return 0 ;;
  esac
  if [ -z "$PW_SET" ]; then
    if [ -n "${LINXIV_WEB_PASSWORD_FILE:-}" ]; then
      PW=$(head -n 1 "$LINXIV_WEB_PASSWORD_FILE")
    elif [ -t 0 ]; then
      printf 'linXiv-web password: ' >&2
      stty -echo; IFS= read -r PW || true; stty echo; echo >&2
    else
      die "no terminal to ask for the password; set LINXIV_WEB_PASSWORD_FILE"
    fi
    PW_SET=1
  fi
  # JSON-escape backslashes and quotes; the body goes through stdin, not argv.
  esc=$(printf '%s' "$PW" | sed 's/\\/\\\\/g; s/"/\\"/g')
  rm -f "$WORK/jar"
  code=$(printf '{"password":"%s"}' "$esc" | curl -sS -o "$WORK/body" -w '%{http_code}' \
    -c "$WORK/jar" -H 'Content-Type: application/json' --data-binary @- "$URL/api/login") \
    || die "login request failed"
  [ "$code" = 200 ] || die "login failed ($code): $(detail "$WORK/body")"
}

# Session cookies sent by hand, so they work over plain HTTP even when
# LINXIV_WEB_COOKIE_SECURE=true marks them https-only.
write_cookie_config() {
  s=$(jar_value lxw_session); c=$(jar_value lxw_csrf)
  : > "$WORK/curlrc"
  [ -n "$s" ] || return 0
  printf 'header = "Cookie: lxw_session=%s; lxw_csrf=%s"\nheader = "X-CSRF-Token: %s"\n' \
    "$s" "$c" "$c" > "$WORK/curlrc"
}

upload() {
  curl -sS -o "$WORK/body" -w '%{http_code}' -K "$WORK/curlrc" \
    -F "file=@$SRC/$1;type=application/pdf" "$URL/api/pdfs/import" 2>"$WORK/err" || true
}

run_api() {
  [ -z "$PROJECT_ID" ] || die "--project-id is offline mode only; the upload route has no project option"
  login
  write_cookie_config
  log "importing $TOTAL PDF(s) from $SRC through $URL"
  while IFS= read -r rel; do
    code=$(upload "$rel")
    if [ "$code" = 401 ]; then  # session lost, e.g. the container restarted
      login; write_cookie_config; code=$(upload "$rel")
    fi
    if [ "$code" = 000 ]; then
      log "FAIL  $rel (no response): $(cat "$WORK/err")"
      FAIL=$((FAIL + 1))
    elif [ "$code" = 200 ]; then
      sid=$(sed -n 's/.*"source_id" *: *"\([^"]*\)".*/\1/p' "$WORK/body")
      log "OK    $rel -> ${sid:-?}"
      OK=$((OK + 1))
      move_done "$rel"
    else
      log "FAIL  $rel ($code): $(detail "$WORK/body")"
      FAIL=$((FAIL + 1))
    fi
  done < "$WORK/list"

  if [ "$INDEX_TEXT" = 1 ]; then
    code=$(curl -sS -o "$WORK/body" -w '%{http_code}' -K "$WORK/curlrc" -X POST \
      "$URL/api/jobs/index-pdf-text") || code=000
    case "$code" in
      200) log "started the PDF full-text index job (Settings shows progress)" ;;
      *) log "could not start the PDF full-text index job ($code): $(detail "$WORK/body")" ;;
    esac
  fi
}

# --- offline mode -----------------------------------------------------------

run_offline() {
  [ "$INDEX_TEXT" = 0 ] || die "--index-text needs the server; use it in api mode or click Index in Settings"
  cd "$COMPOSE_DIR" || die "no such directory: $COMPOSE_DIR"
  if [ -n "$(docker compose ps -q --status running "$SERVICE")" ]; then
    die "$SERVICE is running; stop it first: docker compose stop $SERVICE"
  fi
  log "importing $TOTAL PDF(s) from $SRC with the linxiv CLI (container stopped, --place $PLACE)"
  # One container for the whole batch, running OFFLINE_HELPER (below) with the
  # file list on stdin. The image entrypoint links /data/pdfs to /pdfs first.
  # The helper prints one "STATUS path source_id detail" line per file as it
  # goes, fields split by the ASCII unit separator (a tab would let empty fields
  # collapse). Each line is logged at once, so the log shows live progress.
  sep=$(printf '\037')
  docker compose run --rm --no-deps -T \
    -v "$SRC:/import:ro" -e "PLACE=$PLACE" -e "PROJECT_ID=$PROJECT_ID" "$SERVICE" \
    python3 -c "$OFFLINE_HELPER" < "$WORK/list" | while IFS="$sep" read -r st rel sid detail; do
      printf '%s%s%s%s%s%s%s\n' "$st" "$sep" "$rel" "$sep" "$sid" "$sep" "$detail" >> "$WORK/results"
      case "$st" in
        OK) log "OK    $rel -> $sid" ;;
        DUP) log "DUP   $rel -> $sid (paper already uses $detail)" ;;
        SKIP) log "SKIP  $rel: $detail" ;;
        ABORT) log "ABORT $detail" ;;
        *) log "FAIL  $rel: $detail" ;;
      esac
    done
  touch "$WORK/results"
  grep -q "^ABORT$sep" "$WORK/results" && die "nothing imported; see the ABORT line above"

  while IFS="$sep" read -r st rel _; do
    [ "$st" = OK ] && move_done "$rel"
  done < "$WORK/results"
  OK=$(grep -c "^OK$sep" "$WORK/results" || true)
  DUP=$(grep -c "^DUP$sep" "$WORK/results" || true)
  SKIP=$(grep -c "^SKIP$sep" "$WORK/results" || true)
  FAIL=$(grep -c "^FAIL$sep" "$WORK/results" || true)
  missing=$((TOTAL - OK - DUP - SKIP - FAIL))
  [ "$missing" -eq 0 ] || { log "$missing file(s) gave no result; see docker compose output above"; FAIL=$((FAIL + missing)); }
  [ "$DUP$SKIP" = 00 ] || log "duplicates kept on disk but not linked: $DUP, skipped: $SKIP"
}

# Runs inside the container (python3 -c). Reads relative paths on stdin.
OFFLINE_HELPER=$(cat <<'PY'
import json, os, re, sqlite3, subprocess, sys
from pathlib import Path

DATA = Path(os.environ.get("LINXIV_DATA_DIR", "/data"))
PDFS = DATA / "pdfs"              # how linXiv writes PDF_PATH values
IMPORT = Path("/import")
PLACE = os.environ.get("PLACE", "copy")
PROJECT = os.environ.get("PROJECT_ID", "")
# linXiv's own file name for a paper's PDF, e.g. doi_10.1000_xyzv1.pdf
MANAGED = re.compile(r"^[a-z]+_.+v\d+\.pdf$")


def emit(st, rel="", sid="", detail=""):
    clean = lambda s: str(s).replace("\x1f", " ").replace("\n", " ")
    print("\x1f".join(clean(x) for x in (st, rel, sid, detail)), flush=True)


def linxiv(*args):
    p = subprocess.run(["linxiv", *args], capture_output=True, text=True)
    if p.returncode != 0:
        msg = p.stderr.strip()[-300:] or "linxiv failed"
        for line in reversed(p.stderr.strip().splitlines()):
            try:
                msg = json.loads(line)["error"]
                break
            except (ValueError, KeyError, TypeError):
                continue
        raise RuntimeError(msg)
    return json.loads(p.stdout) if p.stdout.strip() else {}


def prefix_in_pdf_dir():
    """Path of /import inside the PDF folder, matched by device and inode."""
    want = os.stat(IMPORT)
    root = PDFS.resolve()
    for dirpath, _, _ in os.walk(root):
        st = os.stat(dirpath)
        if (st.st_dev, st.st_ino) == (want.st_dev, want.st_ino):
            return Path(dirpath).relative_to(root)
    return None


def db():
    conn = sqlite3.connect(DATA / "papers.db", timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def latest(conn, sid):
    return conn.execute(
        "SELECT p.PAPER_ID, m.PDF_PATH FROM PAPER p JOIN PAPER_META m ON m.PAPER_ID = p.PAPER_ID "
        "WHERE p.SOURCE_ID = ? ORDER BY p.VERSION DESC LIMIT 1", (sid,)).fetchone()


def same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def linxiv_copy(path):
    """True for linXiv's own copy: a managed file name directly in the PDF folder."""
    p = Path(path)
    return bool(MANAGED.match(p.name)) and same_file(p.parent, PDFS)


def shown(path):
    try:
        return Path(path).relative_to(PDFS)
    except ValueError:
        return path


def main():
    proj = ["--project-id", PROJECT] if PROJECT else []
    prefix = None
    known = {}
    if PLACE == "in-situ":
        prefix = prefix_in_pdf_dir()
        if prefix is None:
            emit("ABORT", detail="--place in-situ needs a folder inside the PDF folder "
                 "(LINXIV_WEB_PDF_HOST); this one is outside it")
            return 3
        linxiv("stats")      # lets linXiv create or migrate papers.db before we read it
        # Your own files that papers already point at: the first one wins. linXiv's
        # copies don't count; an in-situ file replaces them.
        with db() as conn:
            for sid, path in conn.execute(
                    "SELECT p.SOURCE_ID, m.PDF_PATH FROM PAPER p JOIN PAPER_META m "
                    "ON m.PAPER_ID = p.PAPER_ID WHERE coalesce(m.PDF_PATH, '') <> ''"):
                if Path(path).is_file() and not linxiv_copy(path):
                    known[sid] = path
    for line in sys.stdin:
        rel = line.rstrip("\n")
        if not rel:
            continue
        try:
            if prefix is not None and str(prefix / rel) == Path(rel).name and MANAGED.match(rel):
                emit("SKIP", rel, detail="named like a linXiv-managed file at the PDF folder root")
                continue
            sid = linxiv("pdf", "import", *proj, "--", str(IMPORT / rel)).get("source_id", "")
            if prefix is None or not sid:
                emit("OK", rel, sid)
                continue
            own = PDFS / prefix / rel
            flat = Path(linxiv("pdf", "path", "--", sid).get("path", ""))
            with db() as conn:
                row = latest(conn, sid)
                if row is None:
                    raise RuntimeError(f"{sid} not found in papers.db after import")
                paper_id = row[0]
                prev = known.get(sid)
                target = prev if prev and not same_file(prev, own) else str(own)
                conn.execute("UPDATE PAPER_META SET PDF_PATH = ? WHERE PAPER_ID = ?", (target, paper_id))
            if flat.is_file() and not same_file(flat, own) and not same_file(flat, target) \
                    and flat.resolve().is_relative_to(PDFS.resolve()):
                flat.unlink()
            if target != str(own):
                emit("DUP", rel, sid, shown(target))
            else:
                known[sid] = target
                emit("OK", rel, sid)
        except Exception as e:  # one bad file must not stop the batch
            emit("FAIL", rel, detail=e)
    return 0


sys.exit(main())
PY
)

"run_$MODE"
log "done: $OK imported, $FAIL failed, $TOTAL total. Log: $LOG"
[ "$FAIL" -eq 0 ]
