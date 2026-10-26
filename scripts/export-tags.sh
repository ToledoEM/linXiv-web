#!/bin/sh
# Export every paper's tags from linXiv-web as a tidy CSV: one row per paper
# per tag, columns source_id,tag. Run it on the machine that hosts the
# linXiv-web container.
#
#   Papers are read with GET /api/papers, 1000 at a time. source_id is the key
#   the tag endpoints (/api/papers/{source_id}/tags) take, so the file can be
#   used to put the tags back. Papers with no tags have no rows.
set -eu

usage() {
  cat <<'EOF'
Usage: export-tags.sh [options]

Options:
  --out FILE           CSV file to write (default ./paper-tags-<date>-<time>.csv)
  -h, --help           Show this help

Needs curl and jq.

Password (only when the server has one): read from the file named in
LINXIV_WEB_PASSWORD_FILE, otherwise asked for on the terminal.
EOF
}

die() { echo "export-tags: $*" >&2; exit 2; }

# The port docker-compose.yml publishes on the server.
URL=http://127.0.0.1:8086
OUT=
PW=
PW_SET=
PAGE=1000      # the most GET /api/papers returns per call

while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT=${2:?--out needs a value}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1 (see --help)" ;;
  esac
done
command -v curl >/dev/null 2>&1 || die "curl not found"
command -v jq >/dev/null 2>&1 || die "jq not found; install it (apt install jq)"
[ -n "$OUT" ] || OUT="./paper-tags-$(date +%Y%m%d-%H%M%S).csv"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
CODE=
T=$WORK

# --- server calls -----------------------------------------------------------

# Value of one cookie from curl's jar (HttpOnly cookies carry a "#HttpOnly_" prefix).
jar_value() {
  [ -f "$WORK/jar" ] || return 0
  awk -v n="$1" -F '\t' 'NF >= 7 && $6 == n { v = $7 } END { if (v != "") print v }' "$WORK/jar"
}

# Message from a JSON error body ({"detail": "..."}), or the raw body.
detail() {
  jq -er '.detail | if type == "string" then . else tojson end' "$1" 2>/dev/null || head -c 300 "$1"
}

# Why the last call failed: its status and message.
reason() {
  if [ "$CODE" = 000 ]; then
    printf '(no response): %s' "$(head -c 300 "$T/err")"
  else
    printf '(%s): %s' "$CODE" "$(detail "$T/body")"
  fi
}

login() {
  me=$(curl -sS "$URL/api/me") || die "cannot reach $URL (is the container running?)"
  state=$(printf '%s' "$me" | jq -r 'if .setup_required == true then "setup"
    elif .auth_enabled == false then "open" else "auth" end' 2>/dev/null) || state=auth
  case "$state" in
    setup) die "first-run setup is not done; set the password in the web UI first" ;;
    open) return 0 ;;
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
  # The body goes through stdin, not argv.
  rm -f "$WORK/jar"
  code=$(printf '%s' "$PW" | jq -Rs '{password: .}' | curl -sS -o "$WORK/body" -w '%{http_code}' \
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

# api METHOD PATH: prints the HTTP status (000 when no response);
# the body lands in $T/body.
api() {
  curl -sS -o "$T/body" -w '%{http_code}' -K "$WORK/curlrc" -X "$1" \
    "$URL$2" 2>"$T/err" || true
}

# As api, status in CODE. Logs in again once when the session is lost
# (e.g. the container restarted).
call() {
  CODE=$(api "$@")
  if [ "$CODE" = 401 ]; then
    login; write_cookie_config; CODE=$(api "$@")
  fi
}

# --- export -------------------------------------------------------------------

login
write_cookie_config

echo 'source_id,tag' > "$WORK/out.csv"
papers=0
offset=0
while :; do
  call GET "/api/papers?limit=$PAGE&offset=$offset"
  [ "$CODE" = 200 ] || die "could not list papers $(reason)"
  jq -r '.[] | .source_id as $s | (.tags // []) | unique[] | [$s, .] | @csv' \
    "$T/body" >> "$WORK/out.csv"
  n=$(jq length "$T/body")
  papers=$((papers + n))
  [ "$n" -ge "$PAGE" ] || break
  offset=$((offset + PAGE))
done

rows=$(($(wc -l < "$WORK/out.csv") - 1))
mv "$WORK/out.csv" "$OUT"
echo "export-tags: $rows rows from $papers papers -> $OUT" >&2
