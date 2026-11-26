#!/usr/bin/env bash
# Round-trip check: om-import then om-export must leave overlay/ and patches/ exactly as they were.
# Compares against a snapshot taken first, so it also works before the files are committed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BEFORE="$ROOT/.cache/check-before"

mkdir -p overlay patches "$BEFORE/overlay" "$BEFORE/patches"
rsync -a --delete overlay/ "$BEFORE/overlay/"
rsync -a --delete patches/ "$BEFORE/patches/"

scripts/om-import.sh
scripts/om-export.sh

status=0
diff -r "$BEFORE/overlay" overlay || status=1
diff -r "$BEFORE/patches" patches || status=1
if [ "$status" -ne 0 ]; then
  echo "om-check: FAIL: om-import followed by om-export changed overlay/ or patches/" >&2
  exit 1
fi
echo "om-check: no diff"
