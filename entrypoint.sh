#!/bin/sh
# linxiv always stores PDFs in $LINXIV_DATA_DIR/pdfs. To keep them on a separate
# mount (LINXIV_WEB_PDF_DIR), make that path a symlink to the PDF dir.
set -eu

DATA_DIR="${LINXIV_WEB_DATA_DIR:-/data}"
PDF_DIR="${LINXIV_WEB_PDF_DIR:-$DATA_DIR/pdfs}"
LINK="$DATA_DIR/pdfs"

fail() { echo "linxiv-web: $*" >&2; exit 1; }

[ -d "$DATA_DIR" ] || fail "LINXIV_WEB_DATA_DIR=$DATA_DIR does not exist"
[ -d "$PDF_DIR" ] || fail "LINXIV_WEB_PDF_DIR=$PDF_DIR does not exist (mount the PDF directory)"

if [ "$PDF_DIR" != "$LINK" ]; then
  if [ -L "$LINK" ]; then
    ln -sfn "$PDF_DIR" "$LINK"
  elif [ -d "$LINK" ]; then
    # An empty dir left by an earlier run is safe to replace; files are not.
    rmdir "$LINK" 2>/dev/null \
      || fail "$LINK holds files; move them into $PDF_DIR, then remove it"
    ln -s "$PDF_DIR" "$LINK"
  elif [ -e "$LINK" ]; then
    fail "$LINK exists and is not a directory"
  else
    ln -s "$PDF_DIR" "$LINK"
  fi
fi

export LINXIV_DATA_DIR="$DATA_DIR"
exec "$@"
