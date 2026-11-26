#!/usr/bin/env bash
# Rebuild .om/ (OpenMetadata at the pinned tag + overlay/ + patches/). Idempotent. See ADR-0014.
# Never deletes .om/ itself: a stale tree is reported and the developer removes it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(tr -d '[:space:]' < openmetadata.version)"
TAG="${VERSION}-release"
OM=".om"
MARK="$OM/.git/om-version"
FORCE="${FORCE:-0}"

fail() { echo "om-import: $*" >&2; exit 1; }
command -v git >/dev/null || fail "git not found"
command -v uv >/dev/null || fail "uv not found (https://docs.astral.sh/uv/)"
command -v docker >/dev/null || fail "docker not found (needed by scripts/antlr4)"
docker info >/dev/null 2>&1 || fail "docker is not running (needed by scripts/antlr4)"

if [ -d "$OM/.git" ]; then
  [ "$(cat "$MARK" 2>/dev/null || true)" = "$VERSION" ] \
    || fail "$OM is not at $VERSION. Run 'make om-export' to keep your work, then remove $OM and retry."
  # Never throw away work that was not exported.
  if [ "$FORCE" != "1" ]; then
    mkdir -p .cache/check
    OUT="$ROOT/.cache/check" "$ROOT/scripts/om-export.sh" >/dev/null
    for d in overlay patches; do
      mkdir -p "$d"
      diff -r "$d" ".cache/check/$d" >/dev/null 2>&1 \
        || fail "$OM has changes that are not exported ($d differs). Run 'make om-export' first, or FORCE=1 to discard them."
    done
  fi
  git -C "$OM" reset -q --hard HEAD
  git -C "$OM" clean -q -fd
else
  [ ! -e "$OM" ] || fail "$OM exists but is not a git tree; remove it and retry"
  git clone -q --depth 1 --branch "$TAG" https://github.com/open-metadata/OpenMetadata.git "$OM"
  printf '%s\n' "$VERSION" > "$MARK"
fi

# Local, untracked excludes for build output so om-export never sees it.
cp scripts/om-local-excludes "$OM/.git/info/exclude"

if [ -d overlay ] && [ -n "$(ls -A overlay 2>/dev/null)" ]; then
  cp -R overlay/. "$OM/"
fi
for p in patches/*.patch; do
  [ -e "$p" ] || continue
  git -C "$OM" apply "$ROOT/$p" || fail "patch does not apply: $p"
done

PY="${PYTHON:-3.11}"
[ -d "$OM/.venv" ] || uv venv -q --python "$PY" "$OM/.venv"
export PATH="$ROOT/scripts:$ROOT/$OM/.venv/bin:$PATH" VIRTUAL_ENV="$ROOT/$OM/.venv"
# OpenMetadata pins the uv version it accepts; use that one for the lock refresh.
UV_PIN="$(sed -n 's/^required-version *= *"==\([^"]*\)" *$/\1/p' "$OM/ingestion/pyproject.toml")"
[ -n "$UV_PIN" ] || fail "cannot read the pinned uv version from $OM/ingestion/pyproject.toml"
( cd "$OM/ingestion" && uv tool run --from "uv==$UV_PIN" uv lock -q && make install_dev )
( cd "$OM" && make generate )
# Generated UI files are not stored in the repository (scripts/om-export-ignore): rebuild them from the schemas.
if [ "${OM_SKIP_UI_CODEGEN:-0}" != "1" ]; then
  "$ROOT/scripts/om-ui-codegen.sh"
fi
echo "om-import: $OM ready at $VERSION"
