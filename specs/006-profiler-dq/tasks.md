# Tasks: Profiler and data quality

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: required (constitution VI). Tests are written first and seen failing.

**Order** (from the demand):

1. research from SPIKE-04;
2. fixture rows and expected values;
3. registry;
4. overrides, one task each with its test;
5. unsupported list and warnings;
6. data-quality tests;
7. matrix doc;
8. GAP entries.

The plan adds T-probe (T002) first.

**Cut candidates** (cut order step 3): tasks marked **[CUT]**.

- **The regex tests:** the regex part of T024–T026.
- **The advanced data-quality tests:** median, mean, standard deviation, sum and value lengths
  between in T017.

The core metrics and the basic tests (row count, column count, not null, unique, between, in set)
are never cut.

**Paths**: OpenMetadata files are edited in `.om/` and committed from `overlay/` and `patches/`
after `make om-export` (`make om-check` must stay clean). Connector tests run from `.om/ingestion`.
`…/iris/` is short for `.om/ingestion/src/metadata/ingestion/source/database/iris/`.

## Phase 1: Setup

- [ ] T001 Rebuild `.om/` on this branch (`OM_SKIP_UI_CODEGEN=1 make om-import`, `uv` on `PATH`) and confirm that the unit and integration tests of specs 002–005 pass on `latest-em` as `admin` and `reader`
- [ ] T002 T-probe (research R2, R3; plan build order step 1). This throwaway script lives in the scratchpad and is not committed. On `latest-em`, use a subclass of `SQASampler` that does two things in its constructor: it logs one `WARNING` through `ingestion_logger()`, then raises an exception. Run it with a stub record through `ProfilerProcessor` (via `Step.run`) and through `TestCaseRunner`, with a stub OpenMetadata client. Check that:
  - the warning is in the step's `status.warnings`, keyed on the module name;
  - the exception gives exactly one step failure for the table, and no metric query runs (count statements on the engine);
  - with `sampler/processor.py` and `is_skippable_sampling_error` returning true, there is one warning and no failure.

  Record the results in research.md, section "T-probe results". **If any check fails, stop and revise the plan before T003**

## Phase 2: Foundational — fixtures v5, expected values, harness (blocks every story)

- [ ] T003 Add the catalog v5 expectations to `fixtures/iris/test_seed.py` (data-model "Fixture catalog v5"):
  - `CATALOG_VERSION == 5`, history 1–5;
  - `EXPECTED["rows"]` with 60 rows for `Clinic.Patient` and 60 for `Clinic.Encounter`;
  - rows 1 and 2 of `Clinic.Patient` and row 10 of `Clinic.Encounter` unchanged;
  - no change to objects, columns or grants.

  Run it against `latest-em` and see it fail
- [ ] T004 Extend `.om/ingestion/tests/integration/iris/data/seed.py`:
  - a pure row generator `clinic_rows()` (research R8, no `random`) that yields the `Clinic.Patient` and `Clinic.Encounter` rows, the three existing rows first;
  - `ROWS` built from it;
  - `EXPECTED["rows"]`;
  - version 5 with its history line.

  Makes T003 pass
- [ ] T005 [P] Write `.om/ingestion/tests/integration/iris/data/expected.py` (license header). It computes, from `clinic_rows()` and `Types.AllTypes`' row, for each tested column, every supported metric of the matrix: counts, NULLs, distinct, unique, duplicate, min, max, mean, sum, standard deviation, min and max length, and discrete median and quartiles (as data-model "Expected values"). It also holds, per test case, the passing and failing parameters. Add a test in `fixtures/iris/test_seed.py` that checks three values against a hand count (null count of `Weight`, distinct `FullName`, `Notes = 'checkup'` rows)
- [ ] T006 Run the loader twice on the three tracks (`FIXTURES OK v5`), `pytest fixtures` on each, and every existing integration test as `admin`, `reader` and `reader_dict` (no regression from the grown rows; in particular spec 002's view and spec 005's access tests)
- [ ] T007 Add the harness to `.om/ingestion/tests/integration/iris/conftest.py` (research R9):
  - a stub OpenMetadata client that answers the database and schema names and the built-in test definitions;
  - a `run_status` fixture that attaches a `StatusWarningHandler` to `ingestion_logger()` around a test and yields its `Status`;
  - `profiler_interface(table, sample_config=None)` and `test_suite_interface(table, sample_config=None)` builders, which resolve the sampler and test-suite classes through the IRIS `ServiceSpec` (with the base classes until T020 and T025 register the IRIS ones), set `threadCount=5`, and use `iris_cell`'s connection.

  Add a smoke test that profiles `Clinic.Patient` row count as each login

## Phase 3: User Story 1 — Profile an IRIS table and get its metrics (P1) 🎯 MVP

**Goal**: every supported metric of the matrix, median and quartiles included, equals `expected.py`
on every cell and login.

**Independent test**: `pytest tests/integration/iris/test_profiler.py -m iris` on one cell.

### Tests

- [ ] T008 [P] [US1] Write `.om/ingestion/tests/unit/topology/database/test_iris_median.py` (license header):
  - `Dialects.Iris == "iris"`;
  - the IRIS compilation of `MedianFn(col, "Patient", 0.5)` inside `select(...).select_from(<Clinic.Patient table>)`:
    - contains no `percentile_cont`;
    - uses `ROUND(…, 0)`;
    - references `Clinic.Patient` qualified;
    - aliases the inner value;
    - filters `IS NOT NULL`.

    Same for 0.25 and 0.75;
  - a `Billing.Patient` select compiles against `Billing`, not `Clinic` (Principle III).

  See it fail
- [ ] T009 [P] [US1] Write `.om/ingestion/tests/integration/iris/test_profiler.py` (marked `iris`), with T007's builder and no sampling. It profiles `Clinic.Patient`, `Clinic.Encounter` and `Types.AllTypes` and asserts:
  - row and column counts;
  - every supported metric of every non-stream column equals `expected.py`, with numeric values within 1e-6;
  - median, first and third quartile, IQR and non-parametric skew on `Clinic.Patient.Weight`;
  - an all-NULL case, using a `Scratch` table created and dropped by the test as the administrator;
  - the same values for every login (US1 scenario 4).

  See the median assertions fail

### Implementation

- [ ] T010 [US1] Add `Iris = "iris"` to `PythonDialects` in `.om/ingestion/src/metadata/profiler/orm/registry.py`, one line in alphabetical place. This becomes `patches/ingestion__src__metadata__profiler__orm__registry.py.patch` on export
- [ ] T011 [US1] Add `@compiles(MedianFn, Dialects.Iris)` to `.om/ingestion/src/metadata/profiler/orm/functions/median.py`, in the SPIKE-04 window form (research R6), next to the MySQL one. If the dimensional variant (fourth argument) does not compile on IRIS, raise `NotImplementedError` with the reason, and record it for the matrix. Makes T008 pass
- [ ] T012 [US1] Run T009 on the nine local cells. Record in research.md, section "Implementation measurements":
  - the standard-deviation kind IRIS gives (population or sample), with `expected.py` fixed to match;
  - the metric-task counts;
  - what the profiler does on `AI.Embedding`'s VECTOR columns, with and without the dictionary grant (spec edge case).

## Phase 4: User Story 2 — Built-in data-quality tests give correct verdicts (P1)

**Goal**: every supported table and column test passes and fails as expected on every cell and
login.

**Independent test**: `pytest tests/integration/iris/test_data_quality.py -m iris` on one cell.

- [ ] T013 [P] [US2] Write `.om/ingestion/tests/integration/iris/test_data_quality.py` (marked `iris`), with T007's `test_suite_interface`. For each supported table test, run a passing and a failing case from `expected.py` and assert `Success` and `Failed`. The tests are:
  - row count between and equal;
  - column count between and equal;
  - column name exists;
  - columns match set;
  - custom SQL.
- [ ] T014 [P] [US2] In the same file, the basic supported column tests on non-stream columns of `Clinic.Patient` and `Clinic.Encounter`, each with a passing and a failing case. The tests are:
  - not null;
  - unique;
  - missing count;
  - between, numeric (`Weight`) and timestamp (`StartedAt`);
  - in set and not in set (`FullName`).
- [ ] T015 [US2] Run T013–T014 on the nine local cells, as each login; verdicts identical across logins (US2 scenario 3)
- [ ] T016 [US2] Measure the stream behaviour of not null, missing count and unique on `Clinic.Encounter.Notes` (quickstart matrix rows marked "measured"). Record the verdict or the abort per track in research.md, and fill the two matrix cells. These cases are reported, not asserted to pass
- [ ] T017 [P] [US2] **[CUT]** In `test_data_quality.py`, the advanced column tests: value lengths between (`FullName`), and max, min, mean, median, standard deviation and sum between (`Weight`). Each has a passing and a failing case; median between depends on T011. Run on the nine cells

## Phase 5: User Story 3 — Sample by row count (P2)

**Goal**: row-count sampling works on every table, randomized requests run unrandomized with one
warning, and percentage requests are skipped with one warning.

**Independent test**: `pytest tests/unit/topology/database/test_iris_sampler.py` and
`tests/integration/iris/test_sampling.py -m iris`.

### Tests

- [ ] T018 [P] [US3] Write `.om/ingestion/tests/unit/topology/database/test_iris_sampler.py` (license header), with no IRIS. It compiles with the IRIS dialect, using a stub entity and connection, for each data-model "IRIS sampler" case, and asserts:
  - every CTE name starts with a letter and is not quoted, including for `Patient`, whose digest starts with `0`;
  - randomization off and on give the same SQL: `TOP n`, no `ORDER BY`;
  - no compiled query contains a random function, `%` or `MOD`;
  - percentage below 100 raises `IrisSamplingSkipped` with the contract text;
  - percentage 100 returns the raw table;
  - `is_skippable_sampling_error` is true only for `IrisSamplingSkipped`;
  - with a `StatusWarningHandler` on `ingestion_logger()`, the randomized and percentage warnings appear once for two samplers sharing a client, and again for a new client.

  See it fail
- [ ] T019 [P] [US3] Write `.om/ingestion/tests/integration/iris/test_sampling.py` (marked `iris`). With row count 10, on `Clinic.Patient`, `Clinic.Encounter` and `Types.AllTypes`:
  - randomization off: the metrics saw 10 rows (row count of the sample), and no warning;
  - randomization on: the same 10 rows, and exactly one `IRIS-PROFILER-UNSUPPORTED` randomized warning for the three tables;
  - percentage 50: no metric query (count statements), the sampler raises, and exactly one percentage warning for the three tables;
  - row count 1000: every row, and no warning;
  - the test-suite interface with the same configurations gives the same warnings (US3 scenario 5).

### Implementation

- [ ] T020 [US3] Write `…/iris/sampler.py` (license header): `IrisSampler(SQASampler)`, `IrisSamplingSkipped`, and the per-run record `_REPORTED` (data-model, contract).
  - `get_sampler_table_name()` returns `"s" + super()`.
  - `get_sample_query()` reads the randomization flag through a local copy of `sample_config` with `randomizedSample=False`, so the base code builds the query; if the flag was on, log the randomized warning once.
  - In the constructor, after `super().__init__`, a percentage below 100 logs the percentage warning once and raises; percentage 100 is treated as no sampling.
  - `is_skippable_sampling_error`.

  Register `sampler_class=IrisSampler` in `…/iris/service_spec.py`. Makes T018 pass
- [ ] T021 [US3] Run T019 on the nine local cells and record results in research.md

## Phase 6: User Story 4 — What IRIS cannot do is listed and never breaks the run (P2)

**Goal**: the regex and stream in-set and length tests are `Aborted` with one warning per type;
unreadable tables give one `IRIS-ACCESS` each; the runs complete within the threshold.

**Independent test**: `pytest tests/unit/topology/database/test_iris_test_suite.py` and
`tests/integration/iris/test_data_quality.py -k aborted -m iris`, `test_profiler.py -k "access or threshold" -m iris`.

### Tests

- [ ] T022 [P] [US4] Write `.om/ingestion/tests/unit/topology/database/test_iris_test_suite.py` (license header), with a stub table entity (a `TEXT` column, a `BLOB` column, a `VARCHAR` column) and a stub `super().run_test_case`. Assert:
  - each covered pair of data-model "IRIS test-suite interface" returns `Aborted`, with the contract text and the column, without calling the base;
  - every other pair calls the base once;
  - warnings are logged once per test type and column kind per run.
- [ ] T023 [P] [US4] Add to `test_iris_sampler.py`, with a stub session:
  - a readability check that raises `SQLCODE -99` raises `IrisSamplingSkipped` and logs `IRIS-ACCESS: cannot read profile of <Schema>.<Table>: <first line>` once per table;
  - any other error is re-raised;
  - the check selects the entity's columns, not `*`, and reads no rows (`TOP 0`).
- [ ] T024 [P] [US4] In `test_data_quality.py`, the aborted cases on every cell:
  - **[CUT]** match regex and not match regex on `FullName`;
  - in set, not in set and value lengths between on `Clinic.Encounter.Notes`.

  Each result is `Aborted` with the contract text, never `Success` or `Failed`. The warning count is one per test type. The other tests in the same suite still give their verdicts.
- [ ] T025 [P] [US4] In `test_profiler.py`:
  - **access**: as `reader` and `reader_dict`, profiling `Restricted.Secret` and `Restricted.ColumnGrant` gives one `IRIS-ACCESS` each and no metric query; as `admin`, there is no such warning;
  - **threshold**: through `Step.run` of `ProfilerProcessor` over every fixture table the login can see, the step's success ratio is 90% or more; the stream columns and decimal histograms show as the profiler's own failures. Record the ratio per cell.

### Implementation

- [ ] T026 [US4] Write `…/iris/test_suite_interface.py` (license header): `IrisTestSuiteInterface(SQATestSuiteInterface)`, which overrides only `run_test_case` (research R5). The covered set is a module constant. Register `test_suite_class=IrisTestSuiteInterface` in `…/iris/service_spec.py`. Makes T022 pass (**[CUT]** for the regex rows only: if regex is cut, the interface still covers the stream rows)
- [ ] T027 [US4] Add the readability check to `IrisSampler.__init__` (spec FR-013a, research R3):
  - `select(<entity columns>).limit(0)` through the sampler's session;
  - only a privilege error (`SQLCODE -99`) logs `IRIS-ACCESS` once per table and raises `IrisSamplingSkipped`.

  Makes T023 pass
- [ ] T028 [US4] Run T024–T025 on the nine local cells. If the threshold fails on any cell, apply research R7's fallback (`excludeColumns` for stream columns in the test config, plus a docs line) and record why
- [ ] T029 [US4] Run spec 005's guard test (`test_iris_access_guard.py`) and confirm that `sampler.py` and `test_suite_interface.py` pass it with no allow-list entry

## Phase 7: Polish and cross-cutting

- [ ] T030 Fill the supported-metrics matrix in `quickstart.md` from the results of T012, T016, T021 and T028: the "measured" cells, the dimensional median and the VECTOR behaviour
- [ ] T031 Add the seven entries of data-model "Gap Report entries" to `GAP-REPORT.md`, ids after the last one, each with reproduction, actual result per track, connector behaviour and `Upstream:` line. Link them from the matrix. `pytest fixtures/iris/test_gap_report.py` passes
- [ ] T032 Amend `docs/adr/0016-iris-sampler.md` (spec FR-020):
  - **Decision:** add the test-suite interface (research R5), the warning route through the step's handler (R2), the table skip at construction with one framework failure (R3), and the readability check (FR-013a);
  - **Context:** correct the randomization default (R4);
  - **Validation:** add the aborted tests and the access check;
  - **Status line:** "Accepted, amended 2026-11-…".

  Update `docs/adr/README.md` if the status text changes, and `docs/adr/0010-profiler-registry.md` only if its wording about overrides needs the median pointer
- [ ] T033 Mark spec 005's grants table (`specs/005-least-privilege/quickstart.md`, profiler and data-quality rows) confirmed, pointing at this spec's matrix
- [ ] T034 [P] Prepare the planning-repository contract changes on a local branch `contracts/006-profiler-dq`:
  - `docs/contracts/warnings.md`: the `IRIS-PROFILER-UNSUPPORTED` row as [contracts/profiler-warnings.md](contracts/profiler-warnings.md), and the `IRIS-ACCESS` features `profile` and `sample data`;
  - `docs/contracts/fixtures.md`: catalog v5 and the row counts; the 006 planned-additions row done.

  Push only with the user's go-ahead
- [ ] T035 `make py_format` on the touched OpenMetadata files, then `make om-export` and `make om-check` (no diff; only `overlay/` and the two patches changed). Run ruff on dev-repo files, and `pytest fixtures`
- [ ] T036 Run quickstart Q1–Q7 on the final commit and tick `checklists/requirements.md` with a "Success criteria" section (SC-001..009, with evidence), as spec 001 did

## Dependencies

- T001 → T002 → everything. T002 failing stops the spec.
- T003 → T004 → T005, T006 → T007 → every story.
- **US1:** T008/T009 → T010 → T011 → T012.
- **US2:** T013/T014 → T015 → T016. T017 needs T011.
- **US3:** T018/T019 → T020 → T021.
- **US4:** T022 → T026; T023 → T027 (after T020); T024/T025 → T028 (after T026, T027); T029 after T026, T027.
- T030–T036 last. T034 any time after T004.

## Parallel opportunities

```text
After T007:  T008 ∥ T009 ∥ T013 ∥ T014 ∥ T018 ∥ T019 ∥ T022 (different files or test-only)
After T020:  T023 ∥ T024 ∥ T025
After T028:  T030 ∥ T031 ∥ T032 ∥ T033 ∥ T034
```

## Implementation strategy

- **MVP:** US1 (T001–T012) gives unsampled profiles with every supported metric, median included,
  checked on the matrix.
- **Next:** US2 adds the verdicts.
- **Then:** US3 makes sampling usable, and US4 closes the silent cases.
- Each story ends with a nine-cell run, so the branch is always in a state that could be reviewed.

## Notes

- Built on spec 004, which is built on 005 and 003. When they rebase or merge, rebase this branch. The
  fixture catalog goes v2 (003), v3 (005), v4 (004), v5 (006). The shared file is
  `iris/service_spec.py`, which only gains two arguments.
- The ADR-0016 amendment (T032) needs Henry's review before the PR merges.
- Nothing in this spec is pushed without the user's go-ahead.
