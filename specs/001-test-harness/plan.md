# Implementation Plan: Test harness (shared fixtures + CI matrix)

**Branch**: `001-test-harness` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-test-harness/spec.md`

## Summary

Build the test environment every spec is accepted on:

- one idempotent fixture loader with a built-in self-check;
- a shared IRIS start/prepare script used by CI and by developers;
- the pytest interface (`iris_cell`, engines, service connection, `seeded`, marker `iris`) with a
  testcontainers fallback for upstream;
- a 9-cell GitHub Actions matrix plus the overlay round-trip check;
- `GAP-REPORT.md` and a README "Running tests" section.

SPIKE-06 already proved the CI mechanics on all three tracks (`docker run`, unexpire, seed, per-login
pytest, fallback); this plan promotes that evidence.

Delivery runs in two phases because spec 000 (Henry) owns `make om-import`, the `iris/` package
and the `Makefile`:

- **Phase A** (no 000 dependency): loader, start script, fixture tests, CI cells running IRIS +
  seed + fixture tests + guard, gap report.
- **Phase B** (after 000 merges): `test-cell` target, round-trip job, `.om/` cache, conftest +
  placeholder test, unit and integration test steps.

## Technical Context

**Language/Version**: Python 3.11 (OpenMetadata 2.1.1 ingestion; SPIKE-01); POSIX shell for the start
script and Makefile targets.

**Primary Dependencies**: `intersystems-irispython` 5.4.1 (loader, fixture tests, readiness probe);
`sqlalchemy-intersystems-iris` 1.0.2 via the connector's `get_connection` (engines in tests);
`pytest` 9.0.3 and `testcontainers` ~= 4.8.0 (OpenMetadata's test profile pins); OpenMetadata
2.1.1 test utilities (`ingestion/tests/integration/conftest.py`).

**Storage**: IRIS Community containers, Namespace `USER` (throwaway); no persistent storage.

**Testing**: pytest in two environments:

- a plain venv with only the driver and pytest, for the fixture self-check tests under `fixtures/`;
- the `.om/ingestion` environment for connector unit and integration tests.

**Target Platform**: GitHub-hosted `ubuntu-latest` runners; developer machines on Linux or WSL2 with
Docker.

**Project Type**: Test infrastructure inside an overlay repository (ADR-0014): dev-repo root files,
plus OpenMetadata-tree files under `overlay/`.

**Performance Goals**:

- Fixture load and verify in under 2 min from instance start (SC-001). SPIKE-06 measured
  ≈ 10–25 s for start and seed in CI.
- Full CI run in under 15 min wall time, rebuild included (SC-004).

**Constraints**:

- Official driver only; no community dialect anywhere (II).
- Tests never create users or datasets (VI).
- CI needs no secrets (OpenMetadata `REVIEW.md`).
- Overlay Python files carry the Collate Community License header.
- `make om-export` before every commit touching `overlay/`.
- No AI attribution in commits or PRs.

**Scale/Scope**: 9 cells per run (3 tracks × 3 logins) plus 1 round-trip job. Fixture catalog v1 has
4 tables, 1 view, the `Scratch` schema and 2 least-privilege logins. About 14 billed Actions minutes
per run while the repository is private (SPIKE-06).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Framework First | Tests reuse OpenMetadata's integration conftest, test profile and testcontainers; engines come from the connector's own `get_connection`, not a parallel connection path | ✅ |
| II. Official Driver Only | Loader and tests use `iris` (driver) and the official dialect only; CI guard fails if the community `sqlalchemy-iris` distribution is installed or if the `iris` dialect entry point resolves anywhere else (research R6) | ✅ |
| III. IRIS Fidelity | Fixture names keep mixed case; the self-check compares exact names and never uses `GROUP BY` on names, which IRIS upper-cases (R9) | ✅ |
| IV. Least Privilege | `reader` = SELECT on 3 schemas only; `reader_dict` adds read-only dictionary grants; write refusal is verified; credentials are test-only and never logged (the loader prints user names, never passwords) | ✅ |
| V. Nothing Silent, Nothing Hidden | `GAP-REPORT.md` created with GAP-001..009; no workaround in harness code. The ADR-0015 presets stay in 000's `connection.py`, and the harness uses them only through `get_connection` | ✅ |
| VI. Tested on the Matrix | This spec builds the matrix: 3 tracks × admin/reader/reader_dict, preview informative; shared fixtures only; non-applicable tests skip with the cell name | ✅ |
| VII. Upstream-Ready | Conftest follows OpenMetadata's per-connector integration-package shape; testcontainers fallback lets upstream run it; license headers; `make py_format` on overlay files | ✅ |
| VIII. English Artifacts | All artifacts, code comments and commit messages in English | ✅ |
| Workflow: spikes reviewed first | SPIKE-06 findings are written, not yet reviewed by Henry; the user authorized starting in parallel. `research.md` links the findings | ⚠️ tracked, see Complexity Tracking |

**Post-design re-check (after Phase 1)**: unchanged; all gates ✅. The ⚠️ remains until Henry reviews
SPIKE-06.

## Project Structure

### Documentation (this feature)

```text
specs/001-test-harness/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R14
├── data-model.md        # Phase 1: tracks, logins, cells, fixture catalog v1, gap entry
├── quickstart.md        # Phase 1: validation scenarios
├── contracts/
│   ├── fixture-loader.md   # loader command, configuration, exit codes, self-check output
│   ├── test-interface.md   # env vars, pytest fixtures, marker, skip rules
│   └── ci-matrix.md        # jobs, names, steps, required checks
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
# Dev-repo files (Apache-2.0)
fixtures/iris/
├── seed.py                  # CLI entry point: runs the canonical loader (R3)
├── start-iris.sh            # start + wait + unexpire + readiness probe; used by CI and make (R2)
├── check_dialect.py         # community-dialect guard: distribution + entry point (R6)
├── requirements.txt         # plain-venv pins: intersystems-irispython 5.4.1, pytest 9.0.3 (CI and quickstart)
├── conftest.py              # plain-venv fixtures for the self-check tests
├── test_seed.py             # fixture tests: catalog, idempotency, toggle, write refusal, self-check can fail
├── test_check_dialect.py    # guard tests (simulated community dialect and entry-point clash)
├── test_gap_report.py       # GAP-REPORT.md format: entry fields, sequential ids, GAP-001..009
└── test_repo_rules.py       # SC-008: no IRIS user or dataset creation outside the loader
.github/workflows/iris-matrix.yml
.gitattributes               # LF for *.sh, *.py, *.yml (SPIKE-06 surprise 6; coordinate with 000)
GAP-REPORT.md
README.md                    # "Running tests" section (stub from 000)
Makefile                     # section "# --- 001: test harness ---": iris-up, iris-seed, iris-down, test-cell (Phase B)

# OpenMetadata-tree files (overlay/, Collate Community License header)
overlay/ingestion/tests/integration/iris/
├── __init__.py
├── conftest.py              # iris_cell, iris_engine, iris_admin_engine, iris_service_connection, seeded, marker
├── data/__init__.py
├── data/seed.py             # canonical fixture catalog + loader + self-check (R3); runnable as a script
└── test_harness.py          # placeholder test (FR-022)
```

**Structure Decision**: the canonical loader lives in `overlay/ingestion/tests/integration/iris/data/`
so that it ships upstream with the tests, the same way the MySQL integration tests keep their data
under `tests/integration/mysql/data/`. `fixtures/iris/seed.py` is the stable one-command entry point
named in the fixtures contract and runs that same file; there is still exactly one loader. Everything
else follows the repository-layout contract's ownership table (001 owns `fixtures/iris/*`,
`.github/workflows/*`, the integration `conftest.py` and `GAP-REPORT.md`, and extends the `Makefile`).

## Phasing and dependency on spec 000

| Phase | Deliverable | Needs 000? |
|---|---|---|
| A1 | `data/seed.py` loader + self-check; `fixtures/iris/seed.py` entry point | no |
| A2 | `start-iris.sh`; `fixtures/iris/test_seed.py` | no |
| A3 | `iris-matrix.yml`: 9 cells running start → seed → fixture tests → guard | no |
| A4 | `GAP-REPORT.md` (GAP-001..009); `.gitattributes` | no |
| B1 | `Makefile` section with `test-cell` (rebased on 000's Makefile; owner merges first) | yes |
| B2 | `overlay-roundtrip` job (`make om-import && make om-export && git diff --exit-code overlay patches`), `.om/` cache | yes |
| B3 | integration `conftest.py` + `test_harness.py`; unit and integration steps in each cell; guard in the `.om/` env | yes |
| B4 | README "Running tests"; `is-omd` contract PR (fixtures, test-matrix) | yes |

Phase A can merge first. Phase B lands once 000 is on `main`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Spec started before SPIKE-06 review (Development Workflow) | Wave 0 is on the critical path (every spec's acceptance needs the matrix). The findings exist and CI evidence is public in Actions; the user authorized starting in parallel on 2026-11-25 | Waiting idles the fixture owner for the duration of the review. Mitigation: no merge to `main` until Henry has reviewed SPIKE-06 |
| Loader source under `overlay/` instead of `fixtures/iris/` (fixtures contract wording) | Upstream must be able to seed IRIS from inside the OpenMetadata tree (FR-020) | Keeping it only in `fixtures/` breaks the upstream fallback. Two copies would break "one loader" (FR-001). The contract is updated in B4 |
