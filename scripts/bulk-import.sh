#!/bin/sh
# Import every PDF under a directory into linXiv-web, without the web UI.
# Run it on the machine that hosts the linXiv-web container.
#
#   api mode (default): the container keeps running; each PDF is uploaded to
#     POST /api/pdfs/import over loopback, so the server's CLI lock orders the writes.
#   offline mode: the container must be stopped; one throwaway container runs
#     `linxiv pdf import` for each file, with the directory mounted read-only.
#
# See docs/BULK-IMPORT.md.
set -eu

usage() {
  cat <<'EOF'
Usage: bulk-import.sh [options] <dir>

Options:
  --mode api|offline   api (default): upload through the running server.
                       offline: run the linxiv CLI with the container stopped.
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

# Relative paths of every PDF under SRC, one per line, sorted.
(cd "$SRC" && find . -type f -iname '*.pdf' | sed 's|^\./||' | LC_ALL=C sort) > "$WORK/list"
TOTAL=$(wc -l < "$WORK/list" | tr -d ' ')

if [ "$DRY_RUN" = 1 ]; then
  cat "$WORK/list"
  echo "$TOTAL PDF(s) under $SRC"
  exit 0
fi
[ "$TOTAL" -gt 0 ] || { echo "no PDFs under $SRC"; exit 0; }

: > "$LOG"
log() { printf '%s\n' "$*" | tee -a "$LOG"; }
OK=0
FAIL=0

move_done() {
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
  log "importing $TOTAL PDF(s) from $SRC with the linxiv CLI (container stopped)"
  # One container for the whole batch. The image entrypoint links /data/pdfs to
  # /pdfs before running the command. Each line out is "OK|FAIL<TAB>path<TAB>detail".
  docker compose run --rm --no-deps -T \
    -v "$SRC:/import:ro" -e "PROJECT_ID=$PROJECT_ID" "$SERVICE" sh -c '
      while IFS= read -r rel; do
        if [ -n "$PROJECT_ID" ]; then
          out=$(linxiv pdf import --project-id "$PROJECT_ID" -- "/import/$rel" 2>&1)
        else
          out=$(linxiv pdf import -- "/import/$rel" 2>&1)
        fi
        if [ $? -eq 0 ]; then st=OK; else st=FAIL; fi
        printf "%s\t%s\t%s\n" "$st" "$rel" "$(printf "%s" "$out" | tr "\n" " ")"
      done
    ' < "$WORK/list" > "$WORK/results" || true

  while IFS="$(printf '\t')" read -r st rel out; do
    if [ "$st" = OK ]; then
      sid=$(printf '%s' "$out" | sed -n 's/.*"source_id" *: *"\([^"]*\)".*/\1/p')
      log "OK    $rel -> ${sid:-?}"
      OK=$((OK + 1))
      move_done "$rel"
    else
      log "FAIL  $rel: $(printf '%s' "$out" | sed -n 's/.*"error" *: *"\([^"]*\)".*/\1/p' | grep . || printf '%s' "$out" | head -c 300)"
      FAIL=$((FAIL + 1))
    fi
  done < "$WORK/results"
  missing=$((TOTAL - OK - FAIL))
  [ "$missing" -eq 0 ] || { log "$missing file(s) gave no result; see docker compose output above"; FAIL=$((FAIL + missing)); }
}

"run_$MODE"
log "done: $OK imported, $FAIL failed, $TOTAL total. Log: $LOG"
[ "$FAIL" -eq 0 ]
