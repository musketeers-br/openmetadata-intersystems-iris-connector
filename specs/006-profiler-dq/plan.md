# Implementation Plan: Profiler and data quality

**Branch**: `006-profiler-dq` (built on spec 004. Agreed order 000 → 001 → 002 → 003 → 005 → 004 →
006) | **Date**: 2026-11-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-profiler-dq/spec.md`

## Summary

Run OpenMetadata's profiler and built-in data-quality tests on IRIS, with every supported metric
and verdict checked against the fixture data. Every limitation is reported or aborted, never
silent.

- **Registry and median** (two patches, ADR-0010):
  - `Iris = "iris"` in `PythonDialects`;
  - one `@compiles(MedianFn, Dialects.Iris)` in SPIKE-04's window form (research R6).
- **`iris/sampler.py`**: `IrisSampler(SQASampler)`, registered as `sampler_class` (ADR-0016).
  - It prefixes CTE names with a letter.
  - Randomized row-count sampling runs unrandomized, with one warning per run.
  - Percentage sampling below 100 skips the table at construction, with one warning per run and one
    framework failure per table (R3).
  - A readability check skips unreadable tables with one `IRIS-ACCESS` each (spec FR-013a).
  - Warnings go through the step's own warning handler (R2).
- **`iris/test_suite_interface.py`**: `IrisTestSuiteInterface(SQATestSuiteInterface)`, registered as
  `test_suite_class` (spec FR-012a, R5). It aborts the regex tests and the stream in-set and length
  tests, with one warning per test type per run.
- **Fixtures**:
  - catalog v5: `Clinic.Patient` and `Clinic.Encounter` grow to 60 deterministic rows (R8);
  - `expected.py` derives the expected values from the same generator.
- **Tests**:
  - unit tests for the compiled SQL and the per-run reporting;
  - integration tests of metrics, verdicts, sampling, access and the threshold on all cells, in
    process with no OpenMetadata server (R9).
- **Docs**:
  - the supported-metrics matrix ([quickstart.md](quickstart.md));
  - seven Gap Report entries;
  - the ADR-0016 amendment;
  - the warnings and fixtures contracts in the planning repository.

## Technical Context

**Language/Version**: Python 3.11 (OpenMetadata 2.1.1 ingestion).

**Primary Dependencies**:

- **OpenMetadata 2.1.1, profiler and sampling:** `SQASampler`, `SQAProfilerInterface`,
  `SQATestSuiteInterface`.
- **OpenMetadata 2.1.1, framework:** the profiler registry and `MedianFn`, `StatusWarningHandler`
  and `ingestion_logger()`, the `ServiceSpec` fields `sampler_class` and `test_suite_class`.
- **SQLAlchemy 2.0** (`@compiles`, `select().limit(0)`).
- **The official dialect** `sqlalchemy-intersystems-iris` 1.0.2, through the `iris` extra.

**Storage**: none. Tests run against IRIS Community containers.

**Testing**: pytest.

- **Unit tests**, no IRIS, in `overlay/ingestion/tests/unit/topology/database/`:
  `test_iris_sampler.py`, `test_iris_test_suite.py`, `test_iris_median.py`.
- **Integration tests**, marked `iris`, in `overlay/ingestion/tests/integration/iris/`:
  `test_profiler.py`, `test_data_quality.py`, `test_sampling.py`.
  - They build the interfaces in process with a stub client (R9).
  - They set `threadCount` to 5.
  - They run in every CI cell.
- **Fixture tests:** `pytest fixtures`.

**Target Platform**: spec 001's CI matrix (9 cells) and local cells.

**Project Type**: connector code in the overlay plus two shared-file patches (ADR-0014), with
fixture and docs changes.

**Performance Goals**: none beyond the framework (constitution: performance needs a measured
problem). The readability check is one statement per table that reads no rows.

**Constraints**:

- **No emulation and no SQL rewriting** (ADR-0010, ADR-0016). The sampler and the interface add no
  SQL of their own.
- **Shared files:** only the registry and `median.py`, each a minimal patch.
- **Warnings** go into the ingestion status, never only into logs (V, ADR-0008).
- **Fixtures:** additive change (ADR-0012). `threadCount ≤ 5` on Community.

**Scale/Scope**:

- 2 patches and 2 new connector modules;
- about 30 metrics, 20 test definitions and 6 sampling modes in the matrix;
- 7 Gap Report entries;
- 60 + 60 fixture rows.

## Constitution Check

| Gate | Plan | Status |
|---|---|---|
| I. Framework First | `ServiceSpec` hooks that OpenMetadata already defines (`sampler_class`, `test_suite_class`), the registry and `@compiles` (ADR-0010); the framework's own warning handler and `Aborted` results | ✅ |
| II. Official Driver Only | Everything runs through the connector's engine | ✅ |
| III. IRIS Fidelity | Median on the schema-qualified table; same table names in two schemas tested | ✅ |
| IV. Least Privilege | `SELECT` only. Unreadable tables are reported, not required | ✅ |
| V. Nothing Silent | One warning per unsupported mode and test type; `IRIS-ACCESS` per unreadable table; the wrong verdicts become `Aborted`; every limitation is in the Gap Report with a reproduction | ✅ |
| VI. Tested on the Matrix | Metrics, verdicts, sampling and access on all 9 cells, against values derived from the shared fixtures | ✅ |
| VII. Upstream-Ready | Code in `.om/`, `make py_format`, license headers; the patches are minimal and grouped | ✅ |
| VIII. English Artifacts | ✅ | ✅ |
| Workflow: spike reviewed first | SPIKE-04 reviewed and decided on 2026-11-27 (ADR-0016) | ✅ |

**Post-design re-check**: unchanged. The ADR-0016 amendment (test-suite interface, warning route,
table skip, randomization default) goes in this spec's PR (FR-020) and needs Henry's review.

## Project Structure

### Documentation (this feature)

```text
specs/006-profiler-dq/
├── plan.md               # this file
├── research.md           # SPIKE-04 (R1), warning route (R2), table skip (R3), defaults (R4),
│                         #   test-suite interface (R5), median (R6), threshold (R7), fixtures (R8), tests (R9)
├── data-model.md         # sampler cases, interface table, report record, patches, catalog v5, GAP entries
├── quickstart.md         # how to check it; the supported-metrics matrix for spec 008
├── contracts/
│   └── profiler-warnings.md   # IRIS-PROFILER-UNSUPPORTED, IRIS-ACCESS profile/sample data
├── checklists/requirements.md
└── tasks.md              # /speckit-tasks
```

### Source code

```text
# OpenMetadata tree (edited in .om/, Collate Community License header)
patches/ingestion__src__metadata__profiler__orm__registry.py.patch               # Iris dialect
patches/ingestion__src__metadata__profiler__orm__functions__median.py.patch      # @compiles(MedianFn, Iris)
overlay/ingestion/src/metadata/ingestion/source/database/iris/
├── service_spec.py            # + sampler_class, test_suite_class
├── sampler.py                 # new: IrisSampler, IrisSamplingSkipped, per-run report record
└── test_suite_interface.py    # new: IrisTestSuiteInterface
overlay/ingestion/tests/unit/topology/database/
├── test_iris_sampler.py       # new
├── test_iris_test_suite.py    # new
└── test_iris_median.py        # new
overlay/ingestion/tests/integration/iris/
├── data/seed.py               # catalog v5
├── data/expected.py           # new: expected values from the row generator
├── conftest.py                # + a profiler/test-suite fixture with the stub client and the warning handler
├── test_profiler.py           # new
├── test_data_quality.py       # new
└── test_sampling.py           # new

# Dev-repo files
fixtures/iris/test_seed.py     # v5 row counts, expected.py check
GAP-REPORT.md                  # seven entries
docs/adr/0016-iris-sampler.md  # amendment
docs/adr/0010-profiler-registry.md   # pointer to the median override, if wording needs it
```

**Structure Decision**:

- **One module per framework hook:** `sampler.py` for the sampler and `test_suite_interface.py` for
  the test-suite interface. The per-run record sits in `sampler.py`, and the interface imports it.
- **Shared-file edits:** only the two patches that ADR-0010 allows.
- **No `queries.py` entry:** the readability check is a SQLAlchemy `select` on the table ORM, not a
  raw SQL string.

## Build order

1. **T-probe** (research R2, R3): on `latest-em`, a throwaway subclass that logs through
   `ingestion_logger()` and raises from the constructor, run through `ProfilerProcessor` and
   `TestCaseRunner` with a stub record. Record the status it produces in research. If either finding
   does not hold, stop and revise the plan.
2. **Fixtures:** catalog v5 and `expected.py`, with the self-check.
3. **Registry patch and median override**, with unit tests (seen failing).
4. **`IrisSampler`**, with unit tests, then the `service_spec` line.
5. **`IrisTestSuiteInterface`**, with unit tests, then the `service_spec` line.
6. **Integration tests:** profiler, data quality, sampling, access and threshold, on nine local
   cells.
7. **Records and docs:** the matrix filled from the results, the GAP entries, the ADR-0016
   amendment and the contracts.

## Dependencies

- **Spec 001:** the matrix, `iris_cell`, `make test-cell`.
- **Spec 003:** the type map (`TEXT` and `BLOB` for streams) and `Types.AllTypes`.
- **Spec 005:** the `IRIS-ACCESS` form, the guard test and the `Restricted` tables.
- **Spec 004:** catalog v4, so this spec takes v5.
- **Spec 008** publishes the matrix and the notes (`threadCount`, stream columns, regex).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| A connector sampler and a test-suite interface (ADR-0010 prefers `@compiles` only) | IRIS rejects delimited CTE names and has no random function. Two tests give wrong verdicts without an error | `@compiles` cannot rename CTEs or stop the regex fallback, and patching the shared sampler or validators touches files every database uses (ADR-0016, R5) |
| A table is skipped by raising from the sampler's constructor | It is the only point where 2.1.1 lets a sampler skip a table without a substitute result (R3) | Raising later fails every metric task, and an empty sample publishes zeros |
| Built on unmerged specs (002–005, 004) | The fixtures, access contract and type map come from them | Branching from main would duplicate them |
