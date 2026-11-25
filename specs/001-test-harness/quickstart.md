# Quickstart: validate the test harness

Runnable checks that prove spec 001 works. Interfaces: [fixture-loader](contracts/fixture-loader.md),
[test-interface](contracts/test-interface.md), [ci-matrix](contracts/ci-matrix.md). Catalog:
[data-model](data-model.md).

## Prerequisites

- Linux or WSL2 with Docker, about 4 GB free for one IRIS image.
- Python 3.11 (`uv` provides it).
- A venv with `pip install -r fixtures/iris/requirements.txt` (`intersystems-irispython==5.4.1`,
  `pytest==9.0.3`). `start-iris.sh` uses it for the readiness probe.
- Phase B only: spec 000 merged, then `make om-import` once.
- Local port 11972 free; another IRIS on 1972 is fine.

## Q1 — Fixtures on every track (FR-001..004, SC-001)

```bash
for t in latest-em latest-cd latest-preview; do
  fixtures/iris/start-iris.sh $t 11972 omd-test-iris-$t        # prints digest + $ZVERSION
  IRIS_PORT=11972 python fixtures/iris/seed.py                  # expect: PASS C1..C11, FIXTURES OK v1
  IRIS_PORT=11972 python fixtures/iris/seed.py                  # second run: same output, exit 0
  docker rm -f omd-test-iris-$t
done
```

Expected: exit 0 each time, under 2 minutes from start to `FIXTURES OK` per track.

## Q2 — The self-check can fail (FR-004)

```bash
fixtures/iris/start-iris.sh latest-em 11972 omd-test-iris-latest-em
IRIS_PORT=11972 python fixtures/iris/seed.py
IRIS_HOST=127.0.0.1 IRIS_PORT=11972 pytest fixtures -q
```

Expected: all pass. `test_seed.py` includes a test that runs `self_check` with an extra expected
object, or a wrong expected row count, and asserts exit or raise with that object named. Then drop
`Billing.Patient` as admin and rerun only the self-check: it fails with `C1 … Billing.Patient`.

## Q3 — Not-prepared instance (edge case)

Start a container **without** the unexpire step (`docker run …` directly), then run the loader.
Expected: exit 2 with a message pointing to `start-iris.sh`, not a stack trace.

## Q4 — One cell locally (FR-021, SC-005) — Phase B

```bash
make test-cell TAG=latest-em LOGIN=reader          # iris-up (11972) → iris-seed → pytest -m iris
make test-cell TAG=latest-cd LOGIN=reader_dict
make iris-down
```

Expected: the placeholder tests pass, and `-rs` shows no skips for these cells.

## Q5 — Community-dialect guard can fail (FR-013, SC-006)

```bash
uv venv -p 3.11 /tmp/guard && uv pip install -p /tmp/guard/bin/python sqlalchemy-iris
/tmp/guard/bin/python fixtures/iris/check_dialect.py; echo "exit=$?"     # expect exit=1, names sqlalchemy-iris
python fixtures/iris/check_dialect.py; echo "exit=$?"                    # clean venv: exit=0
```

## Q6 — Upstream mode, no IRIS address (FR-020) — Phase B

```bash
unset IRIS_HOST IRIS_PORT
IRIS_LOGIN=reader <.om python> -m pytest .om/ingestion/tests/integration/iris -m iris -rs   # interpreter path set by spec 000 (research R7)
```

Expected: the conftest starts `latest-em`, prepares and seeds it, runs, and removes it. No container
is left behind (`docker ps -a`).

## Q7 — CI matrix (FR-008..015, SC-002..004)

Open a draft pull request (or push to `main`), then open the run:

- Phase A: 9 checks `iris-<tag>-<login>`, each with digest and `$ZVERSION` in its summary.
- Phase B: plus `overlay-roundtrip`.
- Break one cell on purpose (for example, a failing step in one cell of a throwaway draft pull
  request): only that cell fails, and the other 8 report.
- A failure only on `iris-latest-preview-*` leaves the PR mergeable (required checks list,
  ci-matrix contract).

## Q8 — Gap report (FR-023, SC-007)

`GAP-REPORT.md` has the entry format and GAP-001..009. Each reproduction runs against Q1's
container, except GAP-003, which is marked "pending SPIKE-03".
