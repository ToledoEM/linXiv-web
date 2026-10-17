#!/bin/sh
# Tag every untagged paper in linXiv-web with the AI set in Settings → AI.
# Run it on the machine that hosts the linXiv-web container.
#
#   The list of papers with no tags (every paper with --all) is read once at
#   the start. Each paper is
#   sent to POST /api/ai/tags/{id} (the same suggestions as "AI Tags" on the
#   paper page), and the suggested tags are added with POST /api/papers/{id}/tags.
#   Papers with neither a title nor an abstract are skipped: the model would
#   have nothing to read. --jobs N keeps N papers in flight at once.
#
# See docs/BULK-AI-TAGS.md.
set -eu

usage() {
  cat <<'EOF'
Usage: bulk-ai-tags.sh [options]

Options:
  --all                Also ask about papers that already have tags; the AI is told
                       their current tags and only new ones are added
                       (default: only papers with no tags)
  --max-tags N         Add at most N of the suggested tags per paper, 1 to 8
                       (default: all of them, as the web UI does)
  --jobs N             Ask the AI about N papers at a time, 1 to 4 (default 1).
                       A local model needs as many parallel slots (LM Studio:
                       Max Concurrent Predictions); see docs/BULK-AI-TAGS.md
  --log FILE           Log file (default ./bulk-ai-tags-<date>-<time>.log)
  --dry-run            List the papers it would tag, then stop (no AI calls, no changes)
  -h, --help           Show this help

Needs curl and jq. AI must be on and working in Settings → AI.

Password (only when the server has one): read from the file named in
LINXIV_WEB_PASSWORD_FILE, otherwise asked for on the terminal.
EOF
}

die() { echo "bulk-ai-tags: $*" >&2; exit 2; }

# The port docker-compose.yml publishes on the server.
URL=http://127.0.0.1:8086
MAX_TAGS=
JOBS=1
LOG=
DRY_RUN=0
ALL=0
PW=
PW_SET=
PAGE=1000      # the most GET /api/papers returns per call

while [ $# -gt 0 ]; do
  case "$1" in
    --max-tags) MAX_TAGS=${2:?--max-tags needs a value}; shift 2 ;;
    --jobs) JOBS=${2:?--jobs needs a value}; shift 2 ;;
    --log) LOG=${2:?--log needs a value}; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --all) ALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1 (see --help)" ;;
  esac
done
case "$MAX_TAGS" in
  '') ;;
  *[!0-9]*) die "--max-tags must be a number from 1 to 8" ;;
  *) [ "$MAX_TAGS" -ge 1 ] && [ "$MAX_TAGS" -le 8 ] || die "--max-tags must be a number from 1 to 8" ;;
esac
case "$JOBS" in
  ''|*[!0-9]*) die "--jobs must be a number from 1 to 4" ;;
  *) [ "$JOBS" -ge 1 ] && [ "$JOBS" -le 4 ] || die "--jobs must be a number from 1 to 4" ;;
esac
command -v curl >/dev/null 2>&1 || die "curl not found"
command -v jq >/dev/null 2>&1 || die "jq not found; install it (apt install jq)"
[ -n "$LOG" ] || LOG="./bulk-ai-tags-$(date +%Y%m%d-%H%M%S).log"

WORK=$(mktemp -d)
PIDS=
trap 'rm -rf "$WORK"' EXIT
# Background workers ignore Ctrl+C (non-interactive sh), so stop them by pid.
# shellcheck disable=SC2086
trap '[ -z "$PIDS" ] || kill $PIDS 2>/dev/null; exit 130' INT TERM
sep=$(printf '\037')
CODE=
T=$WORK        # temp files of the current worker (body, err, tags.json)

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

# api METHOD PATH [JSON-FILE]: prints the HTTP status (000 when no response);
# the body lands in $T/body.
api() {
  if [ $# -ge 3 ]; then
    curl -sS -o "$T/body" -w '%{http_code}' -K "$WORK/curlrc" -X "$1" \
      -H 'Content-Type: application/json' --data-binary "@$3" "$URL$2" 2>"$T/err" || true
  else
    curl -sS -o "$T/body" -w '%{http_code}' -K "$WORK/curlrc" -X "$1" \
      "$URL$2" 2>"$T/err" || true
  fi
}

# As api, status in CODE. With one job, logs in again once when the session is
# lost (e.g. the container restarted). Parallel workers share the session and
# can't each log in again, so they report the 401 and a rerun picks those up.
call() {
  CODE=$(api "$@")
  if [ "$CODE" = 401 ] && [ "$JOBS" = 1 ]; then
    login; write_cookie_config; CODE=$(api "$@")
  fi
}

# Paper id as a URL path, each segment encoded like the web UI does
# (old arXiv ids such as hep-th/9901001 keep their slash).
id_path() {
  jq -rn --arg s "$1" '$s | split("/") | map(@uri) | join("/")'
}

# --- papers to tag ------------------------------------------------------------

login
write_cookie_config

if [ "$ALL" = 1 ]; then
  FILTER=; WHAT=paper
else
  FILTER='untagged=true&'; WHAT='untagged paper'
fi

# One "source_id <US> pdf_file <US> title <US> has_text" line per paper,
# read in full before any paper is tagged (tagging shrinks the untagged list).
: > "$WORK/list"
offset=0
while :; do
  call GET "/api/papers?${FILTER}limit=$PAGE&offset=$offset"
  [ "$CODE" = 200 ] || die "could not list ${WHAT}s $(reason)"
  jq -r '.[] | [
      .source_id,
      (if (.pdf_file // "") == "" then "-" else .pdf_file end),
      ((.title // "") | gsub("[\\s\u001f]+"; " ")),
      (if ((.title // "") | test("\\S")) or ((.summary // "") | test("\\S")) then "1" else "0" end)
    ] | join("\u001f")' "$WORK/body" >> "$WORK/list"
  [ "$(jq length "$WORK/body")" -ge "$PAGE" ] || break
  offset=$((offset + PAGE))
done
TOTAL=$(wc -l < "$WORK/list" | tr -d ' ')
EMPTY=$(grep -c "${sep}0\$" "$WORK/list" || true)

if [ "$DRY_RUN" = 1 ]; then
  while IFS="$sep" read -r sid file title text <&3; do
    [ "$text" = 1 ] || title="(no title or abstract: would be skipped)"
    printf '%s  %s  %s\n' "$sid" "$file" "$title"
  done 3< "$WORK/list"
  echo "$TOTAL $WHAT(s) on $URL; $EMPTY would be skipped (no title or abstract)"
  exit 0
fi
[ "$TOTAL" -gt 0 ] || { echo "no ${WHAT}s on $URL"; exit 0; }

# --- tagging ------------------------------------------------------------------

: > "$LOG"
# One short line per write, appended: lines from parallel workers don't mix.
log() { printf '%s\n' "$*" | tee -a "$LOG"; }
line() { log "$(printf '%-5s %s  %s  %s' "$1" "$2" "$3" "$4")"; }

# Fail early, before the loop, when AI is off or not set up.
call POST /api/ai/test
[ "$CODE" = 200 ] || die "AI check failed $(reason)"
jq -e '.ok == true' "$WORK/body" >/dev/null || die "AI check failed: the model did not answer as expected"
model=$(jq -r '"\(.provider) / \(.model)"' "$WORK/body")

log "started $(date '+%Y-%m-%d %H:%M:%S'): $TOTAL $WHAT(s) on $URL"
log "AI $model, max tags per paper: ${MAX_TAGS:-all}, jobs: $JOBS"
max=${MAX_TAGS:-8}

# Tags the papers listed in DIR/list, keeping its temp files in DIR. Results go
# to the log only; the totals are counted from it at the end.
tag_papers() {
  T=$1
  while IFS="$sep" read -r sid file _ text <&3; do
    if [ "$text" != 1 ]; then
      line SKIP "$sid" "$file" "no title or abstract"
      continue
    fi
    path=$(id_path "$sid")
    call POST "/api/ai/tags/$path"
    # The provider's rate limit or overload comes back as 502 "<Provider> error 429 ...".
    if [ "$CODE" = 502 ] && detail "$T/body" | grep -Eq 'error (429|503|529)'; then
      sleep 30
      call POST "/api/ai/tags/$path"
    fi
    if [ "$CODE" != 200 ]; then
      line FAIL "$sid" "$file" "$(reason)"
      continue
    fi
    n=$(jq --argjson m "$max" '.suggested[:$m] | length' "$T/body")
    if [ "$n" -eq 0 ]; then
      line NONE "$sid" "$file" "model returned no usable tags"
      continue
    fi
    tags=$(jq -r --argjson m "$max" \
      '[.suggested[:$m][] | .tag + (if .known then "" else " (new)" end)] | join(", ")' "$T/body")
    jq --argjson m "$max" '{tags: [.suggested[:$m][].tag]}' "$T/body" > "$T/tags.json"
    call POST "/api/papers/$path/tags" "$T/tags.json"
    if [ "$CODE" = 200 ]; then
      line OK "$sid" "$file" "$tags"
    else
      line FAIL "$sid" "$file" "$(reason); not saved: $tags"
    fi
  done 3< "$T/list"
}

# Paper i goes to worker ((i - 1) mod JOBS) + 1. One job runs in the foreground.
k=1
while [ "$k" -le "$JOBS" ]; do
  mkdir "$WORK/w$k"
  awk -v n="$JOBS" -v k="$k" '(NR - 1) % n == k - 1' "$WORK/list" > "$WORK/w$k/list"
  if [ "$JOBS" = 1 ]; then
    tag_papers "$WORK/w1"
  else
    tag_papers "$WORK/w$k" &
    PIDS="$PIDS $!"
  fi
  k=$((k + 1))
done
wait

count() { grep -c "^$1 " "$LOG" || true; }
OK=$(count OK)
NONE=$(count NONE)
SKIP=$(count SKIP)
FAIL=$(count FAIL)
missing=$((TOTAL - OK - NONE - SKIP - FAIL))
[ "$missing" -eq 0 ] || { log "$missing paper(s) gave no result; a worker stopped early"; FAIL=$((FAIL + missing)); }
log "done: $OK tagged, $NONE none, $SKIP skipped, $FAIL failed, $TOTAL total. Log: $LOG"
[ "$FAIL" -eq 0 ]
