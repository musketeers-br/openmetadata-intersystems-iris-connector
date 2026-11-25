# Contract: CI matrix

Implements FR-008..FR-015. File: `.github/workflows/iris-matrix.yml`. Triggers: `push`, `pull_request`.
`permissions: contents: read`. No secrets.

## Jobs

| Job id / check name | Phase | Needs | Blocking |
|---|---|---|---|
| `overlay-roundtrip` | B | — | yes (required check) |
| `iris-<tag>-<login>` × 9 (`strategy.fail-fast: false`) | A (steps marked B are added later) | `overlay-roundtrip` (B) | `latest-em`, `latest-cd`: required checks; `latest-preview`: `continue-on-error: true`, not required |

## `overlay-roundtrip` steps (B)

1. `actions/checkout@v4` with `persist-credentials: false`; `actions/setup-python@v5` (3.11).
2. Restore the `.om/` cache (key: `om-${{ hashFiles('openmetadata.version','patches/**','Makefile') }}`).
3. `make om-import && make om-export && git diff --exit-code overlay patches`.

## Cell steps

| # | Step | Phase |
|---|---|---|
| 1 | checkout (`persist-credentials: false`), setup-python 3.11 | A |
| 2 | `pip install -r fixtures/iris/requirements.txt` (plain venv: `intersystems-irispython==5.4.1`, `pytest==9.0.3`); before step 3 because the readiness probe uses the driver | A |
| 3 | `fixtures/iris/start-iris.sh "$IRIS_TAG" 1972 iris`: pull, start, wait, unexpire, readiness, print digest + `$ZVERSION` | A |
| 4 | `python fixtures/iris/seed.py` (loads and self-checks) | A |
| 5 | `python fixtures/iris/check_dialect.py` (plain venv) | A |
| 6 | `pytest fixtures -q` | A |
| 7 | restore the `.om/` cache, `make om-import` | B |
| 8 | `check_dialect.py` with the `.om/` interpreter | B |
| 9 | unit: `pytest .om/ingestion/tests/unit/topology/database/test_iris.py` | B |
| 10 | integration: `pytest .om/ingestion/tests/integration/iris -m iris` | B |
| 11 | summary (always): cell name, digest, `$ZVERSION`, step timings → `$GITHUB_STEP_SUMMARY` | A |
| 12 | on failure: `docker logs --tail 200 iris` | A |

Cell environment: `IRIS_HOST=127.0.0.1`, `IRIS_PORT=1972`, `IRIS_NAMESPACE=USER`,
`IRIS_TAG=${{ matrix.tag }}`, `IRIS_LOGIN=${{ matrix.login }}`.

## Branch protection (after the repository is public)

Required on `main`: `overlay-roundtrip`, `iris-latest-em-admin`, `iris-latest-em-reader`,
`iris-latest-em-reader_dict`, `iris-latest-cd-admin`, `iris-latest-cd-reader`,
`iris-latest-cd-reader_dict`. The `iris-latest-preview-*` checks are never required.

## Budget

SPIKE-06: 82 s wall time and 14 billed minutes per run (Phase A steps only). Phase B adds the
round-trip job and `om-import` per cell. Target: under 15 min wall time (SC-004), measured once B
lands.
