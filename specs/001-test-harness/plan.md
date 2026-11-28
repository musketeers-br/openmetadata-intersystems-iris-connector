# Implementation Plan: Test harness (shared fixtures + CI matrix)

**Branch**: `001-test-harness` (from `000-connector-foundation` until spec 000 merges, then from `main`) |
**Date**: 2026-11-25, revised the same day after spec 000's PR | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-test-harness/spec.md`

## Summary

Build the test environment every spec is accepted on:

- one idempotent fixture loader with a built-in self-check;
- a shared IRIS start/prepare script used by CI and by developers;
- the pytest interface (`iris_cell`, engines, service connection, `seeded`, marker `iris`) with a
  testcontainers fallback for upstream, and spec 000's integration test moved onto it;
- a GitHub Actions workflow: the overlay round trip (`make om-check`) plus 9 matrix cells;
- the completed `GAP-REPORT.md`, a README "Running tests" section and an updated ADR-0012.

SPIKE-06 already proved the CI mechanics on all three tracks (`docker run`, unexpire, seed, per-login
pytest, fallback); this plan promotes that evidence. Spec 000 provides the rebuild tooling, the
connector's `IrisConnection` and the integration test package, so there is no staged delivery: 001
is built on 000's branch and merges after it.

## Technical Context

**Language/Version**: Python 3.11 (OpenMetadata 2.1.1 ingestion); POSIX shell for the start script and
Makefile targets.

**Primary Dependencies**:

- `intersystems-irispython` 5.4.1 (loader, fixture tests, readiness probe);
- `sqlalchemy-intersystems-iris` 1.0.2 through the connector: `IrisConnection(config).client`
  (spec 000) gives the engine with the ADR-0015 presets;
- `pytest` 9.0.3 and `testcontainers` ~= 4.8.0 (the versions OpenMetadata 2.1.1 pins for tests);
- OpenMetadata 2.1.1 test utilities (`ingestion/tests/integration/conftest.py`);
- spec 000's tooling: `make om-import`, `om-export`, `om-check`.

**Storage**: IRIS Community containers, Namespace `USER` (throwaway); no persistent storage.

**Testing**: pytest in two environments:

- a plain venv (`fixtures/iris/requirements.txt`) for the fixture self-check tests under `fixtures/`.
  It starts in seconds and does not need `.om/`;
- the `.om/env` environment that `make om-import` builds, for connector unit and integration tests.
  `make om-import` installs the `dev` profile, which has neither the `iris` extra nor
  `testcontainers` (checked 2026-11-25), so 001 adds `scripts/om-test-deps.sh` (target
  `make om-test-deps`), which installs both into `.om/env`, and `om-import.sh` calls it as its last
  step (research R7; agreed with Henry).

**Target Platform**: GitHub-hosted `ubuntu-latest` runners; developer machines on Linux or WSL2 with
Docker.

**Project Type**: Test infrastructure inside an overlay repository (ADR-0014): dev-repo root files,
plus OpenMetadata-tree files under `overlay/`, edited inside `.om/` and written back with
`make om-export`.

**Performance Goals**:

- Fixture load and verify in under 2 min from instance start (SC-001). SPIKE-06 measured
  ≈ 10–25 s for start and seed in CI.
- Full CI run in under 15 min wall time, rebuild included (SC-004).

**Constraints**:

- Official driver only; no community dialect anywhere (II).
- Tests never create users or datasets (VI).
- CI needs no secrets (OpenMetadata `REVIEW.md`).
- Overlay Python files carry the license header spec 000 uses (`#  Copyright 2025 OpenMetadata`,
  Collate Community License 1.0).
- `make om-export` then `make om-check` before every commit touching `overlay/` (constitution).
- Documents in this repository do not refer to planning material kept elsewhere (constitution
  1.2.2): decisions and evidence are written here.
- No upstream issue is opened without both developers agreeing.
- No AI attribution in commits or PRs.

**Scale/Scope**: 9 cells per run (3 tracks × 3 logins) plus 1 round-trip job. Fixture catalog v1 has
4 tables, 1 view, the `Scratch` schema and 2 least-privilege logins. About 14 billed Actions minutes
per run for the cells alone while the repository is private (SPIKE-06); the rebuild adds to that.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Framework First | Tests reuse OpenMetadata's integration conftest, test profile and testcontainers; engines come from the connector's own `IrisConnection`, not a parallel connection path | ✅ |
| II. Official Driver Only | Loader and tests use `iris` (driver) and the official dialect only; CI guard fails if the community `sqlalchemy-iris` distribution is installed or if the `iris` dialect entry point resolves anywhere else (research R6) | ✅ |
| III. IRIS Fidelity | Fixture names keep mixed case; the self-check compares exact names and never uses `GROUP BY` on names, which IRIS upper-cases (R9) | ✅ |
| IV. Least Privilege | `reader` = SELECT on 3 schemas only; `reader_dict` adds read-only dictionary grants; write refusal is verified; credentials are test-only and never logged (the loader prints user names, never passwords) | ✅ |
| V. Nothing Silent, Nothing Hidden | `GAP-REPORT.md` completed to GAP-001..009; no workaround in harness code. The ADR-0015 presets stay in 000's `connection.py`, and the harness uses them only through `IrisConnection` | ✅ |
| VI. Tested on the Matrix | This spec builds the matrix: 3 tracks × admin/reader/reader_dict, preview informative; shared fixtures only; non-applicable tests skip with the cell name | ✅ |
| VII. Upstream-Ready | Conftest follows OpenMetadata's per-connector integration-package shape; testcontainers fallback lets upstream run it; license headers; `make py_format` in `.om/ingestion` before `om-export` | ✅ |
| VIII. English Artifacts | All artifacts, code comments and commit messages in English | ✅ |
| Workflow: self-contained repository (1.2.2) | Spike outcomes and evidence are written in `research.md`; no document refers to external planning material | ✅ |
| Workflow: spikes reviewed first | SPIKE-06 findings were written when the spec started, and the user authorized starting in parallel. Henry reviewed and merged SPIKE-06 on 2026-11-26 | ✅ (was ⚠️, see Complexity Tracking) |

**Post-design re-check (after Phase 1)**: unchanged; all gates ✅. The ⚠️ on "spikes reviewed first"
was cleared when Henry reviewed SPIKE-06 on 2026-11-26.

## Project Structure

### Documentation (this feature)

```text
specs/001-test-harness/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R16 and the evidence behind them
├── data-model.md        # Phase 1: tracks, logins, cells, fixture catalog v1, gap entries
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
├── requirements.txt         # plain-venv pins: intersystems-irispython 5.4.1, pytest 9.0.3
├── conftest.py              # plain-venv fixtures for the self-check tests
├── test_seed.py             # fixture tests: catalog, idempotency, toggle, write refusal, self-check can fail
├── test_cell_login.py       # the cell's login, via the driver (fast check before the connector tests)
├── test_check_dialect.py    # guard tests (simulated community dialect and entry-point clash)
├── test_gap_report.py       # GAP-REPORT.md format: entry fields, sequential ids, GAP-001..009
└── test_repo_rules.py       # SC-008: no IRIS user or dataset creation outside the loader
.github/workflows/iris-matrix.yml
.gitattributes               # LF for *.sh, *.py, *.yml (R14)
GAP-REPORT.md                # extended: GAP-001..003, 006..009 added; tracks filled for all
README.md                    # "Running tests" section replaces 000's integration-test paragraph
Makefile                     # section "# --- 001: test harness ---": om-test-deps, iris-up, iris-seed, iris-down, test-cell
docs/adr/0012-shared-fixtures-and-matrix.md   # updated (FR-026)

# OpenMetadata-tree files (overlay/, edited in .om/, Collate Community License header)
overlay/ingestion/tests/integration/iris/
├── __init__.py              # exists (spec 000)
├── conftest.py              # iris_cell, iris_engine, iris_admin_engine, iris_service_connection, seeded, marker
├── data/__init__.py
├── data/seed.py             # canonical fixture catalog + loader + self-check (R3); runnable as a script
├── test_harness.py          # placeholder test (FR-022)
├── test_connection.py       # spec 000's file, moved onto the conftest fixtures (FR-025, R15)
└── test_workflow.py         # spec 000's file, IRIS settings from the conftest (FR-025, R15)
```

**Structure Decision**: the canonical loader lives in `overlay/ingestion/tests/integration/iris/data/`
so that it ships upstream with the tests, the same way the MySQL integration tests keep their data
under `tests/integration/mysql/data/`. `fixtures/iris/seed.py` is the stable one-command entry point
and runs that same file; there is still exactly one loader. ADR-0012 currently names
`fixtures/iris/seed.py` as the loader and is updated in the same change (FR-026).

## Build order

Each step ends with its tests passing locally; steps 1–3 need only Docker and the plain venv.

| # | Deliverable |
|---|---|
| 1 | `start-iris.sh`, the loader (`data/seed.py`) with its self-check, `fixtures/iris/seed.py`, fixture tests |
| 2 | Guard (`check_dialect.py`), `test_cell_login.py`, `test_repo_rules.py`, `.gitattributes` |
| 3 | `GAP-REPORT.md` completed, `test_gap_report.py` |
| 4 | `Makefile` section (`om-test-deps`, `iris-up`, `iris-seed`, `iris-down`, `test-cell`) |
| 5 | Integration `conftest.py`, `test_harness.py`, `test_connection.py` migration; `om-export` + `om-check` |
| 6 | `iris-matrix.yml`: `overlay-roundtrip` + 9 cells; first run on a draft pull request |
| 7 | README "Running tests", ADR-0012 update |

## Dependencies on spec 000

- 001 merges after 000. Until then, the 001 branch is rebased on `000-connector-foundation`.
- Review findings on 000 that 001 depends on (reported in the PR #11 review, fixed by spec 000 in
  `02a194f`):
  - container steps write root-owned files into `.om/` on Linux, which breaks `om-import` already on
    a fresh clone (`scripts/antlr4`) and leaves `node_modules` owned by root (`om-ui-codegen.sh`);
  - `om-ui-codegen.sh` fails on a fresh clone, because `yarn install` runs the UI's `postinstall`
    (`js-antlr`) and there is no `antlr4` in the Node container.

  Cells run with `OM_SKIP_UI_CODEGEN=1` (generated UI files are never exported). Before the fix,
  `make om-import` failed on GitHub's Linux runners, so the first CI run (T026) waited for it.
- Merge order (agreed with Henry, 2026-11-25): 000 → 001 → 002. Spec 002 (PR #12) then rebases on
  001 and uses the conftest. It uses the fixtures and the `Scratch` schema: `Scratch.Keep` is in
  catalog v1 for its mark-deleted test (R10). Its `GAP-REPORT.md` entries are GAP-010..013, after
  001's GAP-001..009.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Spec started before SPIKE-06 review (Development Workflow) | Wave 0 is on the critical path (every spec's acceptance needs the matrix). The findings exist and the CI evidence is in this repository's Actions history; the user authorized starting in parallel on 2026-11-25 | Waiting idles the fixture owner for the duration of the review. Mitigation: no merge to `main` until Henry has reviewed SPIKE-06. Resolved: Henry reviewed and merged SPIKE-06 on 2026-11-26 |
| Loader source under `overlay/` instead of `fixtures/iris/` (ADR-0012 wording) | Upstream must be able to seed IRIS from inside the OpenMetadata tree (FR-020) | Keeping it only in `fixtures/` breaks the upstream fallback. Two copies would break "one loader" (FR-001). ADR-0012 is updated in the same change (FR-026) |
