# Specification Quality Checklist: Profiler and data quality

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-27
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Success criteria (T036, final validation)

Quickstart Q1–Q7 ran locally on 2026-11-27 on the branch's final commit. The environment was WSL2
with Docker Engine, fixture catalog v5, on `latest-em` 2026.1 (Build 234U) and on `latest-cd` and
`latest-preview` 2026.3 (Build 212U), each as `admin`, `reader` and `reader_dict`. The pull
request's CI repeats the run.

- [x] **SC-001.** `test_profiler.py` on all nine cells. Every default-profiler metric of the six
  tested columns, plus `duplicateCount`, `minLength` and `maxLength`, equals `expected.py`. That
  includes median, quartiles, IQR and skew.
- [x] **SC-002.** `test_data_quality.py`: 7 table tests, 7 basic column tests and 7 advanced tests,
  each with a passing and a failing case, on all nine cells, with identical verdicts for every login.
- [x] **SC-003.** `test_sampling.py`: row-count sampling returns `n` rows on `Clinic.Patient`, whose
  digest starts with `0`, and on `Clinic.Encounter` and `Types.AllTypes`. Unit tests check that the
  CTE names are unquoted.
- [x] **SC-004.** One `IRIS-PROFILER-UNSUPPORTED` warning per mode for a run over three tables, for
  both randomized and percentage sampling, in the profiler and in the test runner.
- [x] **SC-005.** `test_run_meets_the_success_threshold`: 95.3% as admin and 92.8% as the readers.
  VECTOR columns are excluded when there is no grant (research). A test run of the supported tests
  has no failures.
- [x] **SC-006.** The matrix in `quickstart.md` covers every built-in metric, sampling mode and
  built-in test. Each unsupported row names its Gap Report entry (GAP-013..020, all with
  reproductions rerun on the three tracks).
- [x] **SC-007.** Unit tests: `test_iris_median.py`, `test_iris_sampler.py`, `test_iris_test_suite.py`
  and `test_iris_compiles.py`. All 213 IRIS unit tests pass.
- [x] **SC-008.** `test_aborted_tests`: regex (any column), and in set, not in set, value lengths,
  unique and missing count on `Clinic.Encounter.Notes`, are `Aborted` with one warning per test type.
  No wrong verdict remains.
- [x] **SC-009.** As `reader` and `reader_dict`, `Restricted.Secret` gives one `IRIS-ACCESS`, and
  only the `TOP 0` check touches the table. `Restricted.ColumnGrant` is profiled on `Id`, and its
  row count fails with `-99`.

Q7: `make om-export` and `make om-check` show no diff. Only `overlay/` and the two patches
(registry, median) changed. Ruff is clean, and `pytest fixtures` gives 59 passed.
`tests/integration/iris` gives 77, 77 and 76 passed on every track.

## Notes

- Validation run 1 (2026-11-27): one open item.
  - FR-012 has one [NEEDS CLARIFICATION] marker. The question is whether the histogram, the stream
    metrics and the regex and stream in-set tests are only listed as unsupported, or also reported at
    run time.
    - The demand asks for a report once per run.
    - The decisions taken after SPIKE-04 add no mechanism for these items.
    - A run-time report would need an IRIS profiler interface or test-suite interface, and an
      ADR-0016 amendment.
- Validation run 2 (2026-11-27): all items pass.
  - FR-012 was resolved with option B: an IRIS test-suite interface aborts the tests that give wrong
    verdicts, with one warning per test type per run (FR-012a, FR-012b).
  - The histogram and the stream metrics stay documented only.
  - ADR-0016 is amended in the same change (FR-020).
- Audience and technical terms: like specs 000–005, this spec is read by the two developers and by
  upstream maintainers. Profiler, sampler, CTE, `@compiles` and the warning code are the domain
  vocabulary that ADR-0010 and ADR-0016 already fix, not new implementation choices. File layout,
  modules and the test mechanics go to `/speckit-plan`.
- `/speckit-clarify`: the likely questions were settled with Henry after SPIKE-04 and are recorded
  under Clarifications. Only FR-012 is open.
