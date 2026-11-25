# Contract: CI matrix

Implements FR-008..FR-015. File: `.github/workflows/iris-matrix.yml`.

- Triggers: `pull_request`, `push` on `main` only, `workflow_dispatch`. `workflow_dispatch` works only
  once the workflow is on `main`; until then, runs come from a draft pull request.
- `permissions: contents: read`. No secrets.
- `concurrency: { group: iris-matrix-${{ github.event.pull_request.number || github.ref }},
  cancel-in-progress: ${{ github.event_name == 'pull_request' }} }`, so a new commit on a pull request
  cancels the previous run.
- Every job: `actions/checkout@v4` with `persist-credentials: false`, `astral-sh/setup-uv` (for
  `make om-import`), `actions/cache@v4` on the uv download cache and `.cache/` (ANTLR jar), key
  `om-${{ hashFiles('openmetadata.version','patches/**','scripts/**','Makefile') }}`.
- `OM_SKIP_UI_CODEGEN=1` in every job (generated UI files are never exported; research R7).

## Jobs

| Job id / check name | Needs | Blocking |
|---|---|---|
| `overlay-roundtrip` | — | yes (required check) |
| `iris-<tag>-<login>` × 9 (`strategy.fail-fast: false`) | `overlay-roundtrip` | `latest-em`, `latest-cd`: required checks; `latest-preview`: `continue-on-error: true`, not required |

## `overlay-roundtrip` steps

1. checkout, setup-uv, cache (above).
2. `make om-import`.
3. `make om-check` (a second `om-import`, then `om-export` and the diff; fails on any change to
   `overlay/` or `patches/`). Until spec 000's ANTLR container runs as the calling user (research
   R16), `make om-import` fails on GitHub's runners, here and in every cell.

## Cell steps

| # | Step |
|---|---|
| 1 | checkout, setup-uv, cache; `actions/setup-python@v5` (3.11) for the plain venv |
| 2 | `pip install -r fixtures/iris/requirements.txt` (plain venv: `intersystems-irispython==5.4.1`, `pytest==9.0.3`); before step 3 because the readiness probe uses the driver |
| 3 | `fixtures/iris/start-iris.sh "$IRIS_TAG" 1972 iris`: pull, start, wait, unexpire, readiness, print digest + `$ZVERSION` |
| 4 | `python fixtures/iris/seed.py` (loads and self-checks; runs the `overlay/` copy, `.om/` does not exist yet) |
| 5 | `python fixtures/iris/check_dialect.py` (plain venv) |
| 6 | `pytest fixtures -q -rs` (fixture tests, gap-report format, repo rules, the cell's login) |
| 7 | `make om-import && make om-test-deps` |
| 8 | `.om/env/bin/python fixtures/iris/check_dialect.py` |
| 9 | unit, from `.om/ingestion`: `../env/bin/python -m pytest tests/unit/topology/database/test_iris.py -rs` |
| 10 | integration, from `.om/ingestion`: `../env/bin/python -m pytest tests/integration/iris -m iris -rs` |
| 11 | summary (always): cell name, digest, `$ZVERSION`, step timings, pytest summary lines, skip reasons → `$GITHUB_STEP_SUMMARY` |
| 12 | on failure: `docker logs --tail 200 iris` |

Cell environment: `IRIS_HOST=127.0.0.1`, `IRIS_PORT=1972`, `IRIS_NAMESPACE=USER`,
`IRIS_TAG=${{ matrix.tag }}`, `IRIS_LOGIN=${{ matrix.login }}`.

Steps 7–10 run after the IRIS steps so the fixture verdict (steps 4–6) is reported even when the
rebuild fails.

## Branch protection (after the repository is public)

Required on `main`: `overlay-roundtrip`, `iris-latest-em-admin`, `iris-latest-em-reader`,
`iris-latest-em-reader_dict`, `iris-latest-cd-admin`, `iris-latest-cd-reader`,
`iris-latest-cd-reader_dict`. The `iris-latest-preview-*` checks are never required.

## Budget

SPIKE-06 (IRIS steps only): 82 s wall time and 14 billed minutes per run. The rebuild adds one
round-trip job and a cold `om-import` per cell, measured on the first run. Target: under 15 min wall
time (SC-004). First optimization if it is missed: cache `.om/` (research R7).
