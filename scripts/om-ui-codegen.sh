#!/usr/bin/env bash
# Regenerate the UI files OpenMetadata commits for a connection schema, inside a Node container
# (no local yarn or Node): public/jsons/connectionSchemas, src/jsons/ingestionSchemas (parse-schema)
# and src/generated TypeScript (json2ts). Run it after changing a schema in .om/, then 'make om-export'.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
NODE_IMAGE="${OM_NODE_IMAGE:-node:22-bookworm}"
UI="openmetadata-ui/src/main/resources/ui"

fail() { echo "om-ui-codegen: $*" >&2; exit 1; }
[ -d .om/.git ] || fail ".om not found; run 'make om-import' first"
docker info >/dev/null 2>&1 || fail "docker is not running"

docker run --rm -v "$ROOT/.om:/om" -w /om "$NODE_IMAGE" bash -c '
  set -euo pipefail
  apt-get -qq update && apt-get -qq install -y --no-install-recommends jq >/dev/null
  UI=openmetadata-ui/src/main/resources/ui
  if [ ! -d "$UI/node_modules" ]; then (cd "$UI" && yarn install --frozen-lockfile --silent); fi
  (cd "$UI" && node parseSchemas)
  PATH="/om/$UI/node_modules/.bin:$PATH" ./$UI/json2ts-generate-all.sh -l true
'
echo "om-ui-codegen: done; review 'git -C .om status' and run 'make om-export'"
