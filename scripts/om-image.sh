#!/usr/bin/env bash
# Build the OpenMetadata server and ingestion images from .om/ (overlay + patches applied), so they know
# the Iris service type. A stock server rejects it and has no Iris test-connection definition (SPIKE-01).
# Heavy: Maven (Java 21) and the UI build run in Docker; give Docker at least 8 GB of memory.
# Connector unit and integration tests do not need these images.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(tr -d '[:space:]' < openmetadata.version)"
TAG="${OM_IMAGE_TAG:-${VERSION}-iris}"
SERVER_IMAGE="${OM_SERVER_IMAGE:-openmetadata-iris/openmetadata-server}:${TAG}"
INGESTION_IMAGE="${OM_INGESTION_IMAGE:-openmetadata-iris/openmetadata-ingestion}:${TAG}"
MAVEN_IMAGE="${OM_MAVEN_IMAGE:-maven:3.9-eclipse-temurin-21}"

fail() { echo "om-image: $*" >&2; exit 1; }
[ -d .om/.git ] || fail ".om not found; run 'make om-import' first"
docker info >/dev/null 2>&1 || fail "docker is not running"

scripts/antlr4 >/dev/null 2>&1 || true  # downloads and checks the pinned ANTLR jar into .cache/
[ -f .cache/antlr-4.9.2-complete.jar ] || fail "the pinned ANTLR jar is missing from .cache/"
echo "om-image: building the server distribution with Maven (spec, service, UI)..."
docker run --rm \
  -v "$ROOT/.om:/om" -v "$ROOT/.cache:/cache:ro" -v om-iris-m2:/root/.m2 -w /om \
  "$MAVEN_IMAGE" \
  bash -c 'apt-get -qq update && apt-get -qq install -y --no-install-recommends python3 python3-pip >/dev/null \
    && printf "#!/bin/sh\\nexec java -jar /cache/antlr-4.9.2-complete.jar \"\$@\"\\n" > /usr/local/bin/antlr4 && chmod +x /usr/local/bin/antlr4 \
    && mvn -B -ntp -DskipTests -Dspotless.check.skip=true clean package -pl openmetadata-dist -am'

echo "om-image: building $SERVER_IMAGE ..."
docker build -f .om/docker/development/Dockerfile -t "$SERVER_IMAGE" .om

echo "om-image: building $INGESTION_IMAGE (iris extra) ..."
docker build -f .om/ingestion/Dockerfile.ci --build-arg INGESTION_DEPENDENCY=iris -t "$INGESTION_IMAGE" .om

echo "om-image: built $SERVER_IMAGE and $INGESTION_IMAGE"
