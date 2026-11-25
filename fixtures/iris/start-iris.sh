#!/usr/bin/env bash
# Start an IRIS Community container of one release track and prepare it for tests (spec 001, R2):
# wait until IRIS runs, unexpire the default passwords, then wait for an admin SQL login.
# Docker's healthcheck lags behind readiness, so it is not used.
#
# Usage: fixtures/iris/start-iris.sh TAG [PORT=1972] [NAME=iris]
# Env:   IRIS_ADMIN_USER (_SYSTEM), IRIS_ADMIN_PASSWORD (SYS), IRIS_NAMESPACE (USER), PYTHON (python3)
# Exit:  0 ready; 1 docker or start failure; 2 readiness timeout or missing driver.
set -euo pipefail

TAG="${1:?usage: start-iris.sh TAG [PORT] [NAME]}"
PORT="${2:-1972}"
NAME="${3:-iris}"
IMAGE="containers.intersystems.com/intersystems/iris-community:${TAG}"
PYTHON="${PYTHON:-python3}"
QLIST_TIMEOUT=180
LOGIN_TIMEOUT=120
export IRIS_ADMIN_USER="${IRIS_ADMIN_USER:-_SYSTEM}"
export IRIS_ADMIN_PASSWORD="${IRIS_ADMIN_PASSWORD:-SYS}"
export IRIS_NAMESPACE="${IRIS_NAMESPACE:-USER}"

fail() {
  echo "start-iris: $2" >&2
  exit "$1"
}

"$PYTHON" -c "import iris" 2>/dev/null ||
  fail 2 "the IRIS driver is not importable with $PYTHON: install fixtures/iris/requirements.txt"

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -p "127.0.0.1:${PORT}:1972" "$IMAGE" --check-caps false >/dev/null ||
  fail 1 "docker run failed for $IMAGE"

deadline=$((SECONDS + QLIST_TIMEOUT))
until [[ "$(docker exec "$NAME" iris qlist 2>/dev/null | cut -d'^' -f4)" == running* ]]; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" == true ]] ||
    fail 1 "container $NAME stopped; see: docker logs $NAME"
  ((SECONDS < deadline)) || fail 2 "IRIS did not reach state 'running' within ${QLIST_TIMEOUT}s (iris qlist)"
  sleep 2
done

docker exec "$NAME" iris session IRIS -U %SYS '##class(Security.Users).UnExpireUserPasswords("*")' >/dev/null ||
  fail 1 "unexpiring the default passwords failed"

probe() {
  "$PYTHON" - "$PORT" <<'PY'
import os
import sys

import iris

conn = iris.connect(
    "127.0.0.1",
    int(sys.argv[1]),
    os.environ["IRIS_NAMESPACE"],
    os.environ["IRIS_ADMIN_USER"],
    os.environ["IRIS_ADMIN_PASSWORD"],
)
try:
    cursor = conn.cursor()
    cursor.execute("SELECT $ZVERSION")
    print(cursor.fetchone()[0])
finally:
    conn.close()
PY
}

deadline=$((SECONDS + LOGIN_TIMEOUT))
until zversion="$(probe 2>/dev/null)"; do
  ((SECONDS < deadline)) || fail 2 "no admin SQL login on 127.0.0.1:${PORT} within ${LOGIN_TIMEOUT}s"
  sleep 2
done

digest="$(docker image inspect -f '{{index .RepoDigests 0}}' "$IMAGE" 2>/dev/null || echo unknown)"
echo "digest=${digest}"
echo "zversion=${zversion}"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'digest=%s\nzversion=%s\n' "$digest" "$zversion" >>"$GITHUB_OUTPUT"
fi
echo "start-iris: ${NAME} ready on 127.0.0.1:${PORT} (${TAG})"
