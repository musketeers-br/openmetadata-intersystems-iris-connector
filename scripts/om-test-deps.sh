#!/usr/bin/env bash
# Install into .om/env what the IRIS tests need and the dev profile of make om-import does not have:
# the connector's iris extra (official driver and dialect) and testcontainers (fallback mode).
# Versions come from .om/ingestion/uv.lock, so they match the setup.py patch and OpenMetadata's pins.
# Idempotent. Spec 001, research R7.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OM_PY="$ROOT/.om/env/bin/python"
LOCK="$ROOT/.om/ingestion/uv.lock"

fail() {
  echo "om-test-deps: $1" >&2
  exit 1
}

[ -x "$OM_PY" ] && [ -f "$LOCK" ] || fail "no .om/env: run make om-import first"
UV="$(command -v uv || echo "$ROOT/.om/env/bin/uv")"
[ -x "$UV" ] || fail "uv not found"

pins="$("$OM_PY" - "$LOCK" <<'PY'
import sys
import tomllib

want = ("intersystems-irispython", "sqlalchemy-intersystems-iris", "testcontainers")
with open(sys.argv[1], "rb") as stream:
    found = {p["name"]: p["version"] for p in tomllib.load(stream)["package"] if p["name"] in want}
missing = [name for name in want if name not in found]
if missing:
    sys.exit(f"not pinned in uv.lock: {', '.join(missing)}")
print(" ".join(f"{name}=={found[name]}" for name in want))
PY
)" || fail "cannot read the pins from $LOCK"

# shellcheck disable=SC2086  # pins is a space-separated list of requirements
"$UV" pip install --quiet --python "$OM_PY" $pins
"$OM_PY" - <<'PY'
from importlib.metadata import version

for name in ("intersystems-irispython", "sqlalchemy-intersystems-iris", "testcontainers"):
    print(f"om-test-deps: {name} {version(name)}")
PY
