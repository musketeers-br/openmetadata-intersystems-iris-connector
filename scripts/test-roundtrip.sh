#!/usr/bin/env bash
# Tooling test for the overlay round trip (spec 000, User Story 1). Needs a current .om/ (make om-import).
# 1) no-op export changes nothing; 2) a new file lands in overlay/; 3) an edit lands as one patch;
# then the sample changes are reverted with git and the repository is checked clean again.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
NEW="docs/om-roundtrip-sample.txt"
EDIT="README.md"
PATCH="patches/README.md.patch"

fail() { echo "test-roundtrip: FAIL: $*" >&2; exit 1; }
revert() {
  git -C .om checkout -q -- "$EDIT"
  git -C .om clean -q -f -- "$NEW"
  scripts/om-export.sh >/dev/null
}
trap revert EXIT

[ -z "$(git status --porcelain overlay patches)" ] || fail "overlay/ or patches/ not clean before the test"

scripts/om-export.sh >/dev/null
[ -z "$(git status --porcelain overlay patches)" ] || fail "no-op export changed the repository"

echo "sample" > ".om/$NEW"
echo "<!-- om-roundtrip -->" >> ".om/$EDIT"
scripts/om-export.sh >/dev/null
[ -f "overlay/$NEW" ] || fail "new file was not captured in overlay/"
[ -f "$PATCH" ] || fail "edit was not captured as $PATCH"
[ "$(ls patches | wc -l | tr -d ' ')" = "1" ] || fail "expected exactly one patch"
[ "$(find overlay -type f | wc -l | tr -d ' ')" = "1" ] || fail "expected exactly one overlay file"

trap - EXIT
revert
[ -z "$(git status --porcelain overlay patches)" ] || fail "repository not clean after reverting the sample changes"
echo "test-roundtrip: ok"
