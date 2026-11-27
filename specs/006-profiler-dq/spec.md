# Feature Specification: Profiler and data quality

**Feature Branch**: `006-profiler-dq`

**Created**: 2026-11-27

**Status**: Draft

**Input**: User description: "Run OpenMetadata's profiler and built-in data-quality tests on IRIS tables, with the same kinds of results as on other SQL databases. Table metrics (row count, column count) and column metrics (null count and proportion, distinct and unique counts, min, max, mean, sum, standard deviation, value lengths, histogram) are computed wherever the column type supports them. Sampling by percentage and by row count works. Built-in table and column tests — row count between, column count equal, values not null, values unique, values between, values in set, and values matching a regular expression where IRIS supports it — run and report pass or fail. Any metric or test that cannot run on IRIS is listed with the reason in the documentation and in the gap report, and is reported once per run in the ingestion status; it is not emulated with custom SQL, and it never fails the whole profiler run. The shared sample data gains enough rows for meaningful histograms and sampling. Acceptance: on the shared sample tables, every supported metric and test produces the expected value or pass/fail result on every matrix cell, including with the least-privilege login; each IRIS-specific SQL adjustment has its own test; a supported-metrics matrix (metric/test × supported/unsupported + reason) exists for the documentation. Out of scope: custom metrics; data diff; profiling VECTOR contents; performance tuning."

**Covers**: FR-16, FR-17 · **Architecture**: AD-10, AD-16 · **ADRs**: [0010](../../docs/adr/0010-profiler-registry.md), [0016](../../docs/adr/0016-iris-sampler.md), [0008](../../docs/adr/0008-access-gaps-as-warnings.md) (warnings), [0012](../../docs/adr/0012-shared-fixtures-and-matrix.md) (fixtures), [0013](../../docs/adr/0013-gap-report.md) · **Spike**: SPIKE-04, decisions copied into [research.md](research.md) · **Builds on**: spec 001 (shared fixtures, the matrix, `iris_cell`), spec 003 (the type map, `Types.AllTypes`), spec 005 (least-privilege logins, the access-gap helper)

**Cut priority**: if time runs short, the regex tests and the advanced data-quality tests (median,
quartiles, value lengths, mean, standard deviation and sum between) are cut first. The core metrics and
the basic tests (row count, column count, not null, unique, between, in set) stay.

## Clarifications

### Session 2026-11-27

Decisions taken by both developers after SPIKE-04 (ADR-0016 and its "Related decisions"):

- Q: Custom sampler? → A: Yes. Sampling cannot work through `@compiles`: IRIS rejects every delimited
  CTE name, and IRIS SQL has no random function. An IRIS sampler in the connector package, registered
  as the connector's sampler, fixes the CTE names and changes nothing else (ADR-0016).
- Q: Percentage sampling? → A: Unsupported. The table's sampled metrics are skipped, with one warning
  per run. Nothing is computed on a substitute. A capped full-table read was considered and left out
  of v1, because it would need a new IRIS-only setting.
- Q: Randomized row-count sampling (the default)? → A: Unsupported. It runs as non-randomized
  row-count sampling (the first `n` rows), with one warning per run.
- Q: Where do IRIS SQL overrides go? → A: `@compiles(..., "iris")` in OpenMetadata's profiler
  functions, with the IRIS dialect in the profiler registry (ADR-0010). Only one override is
  needed: median and quartiles. There is no modulo override, because percentage and randomized
  sampling were its only users.
- Q: Histogram? → A: Unsupported in v1. IRIS rejects delimited identifiers that contain `.`, and the
  bin labels come from a shared histogram file outside the profiler functions. That file is not
  patched.
- Q: Stream columns (`LONGVARCHAR` → `TEXT`, `LONGVARBINARY` → `BLOB`)? → A: Documented as not
  profiled. IRIS does not run length, distinct count, min, max or cast on streams. The profiler runs all
  of a column's static metrics in one query, so the column gets none of them, null count included.
- Q: Regex tests? → A: Unsupported. IRIS SQL has no regex predicate. OpenMetadata falls back to
  `LIKE` and returns a wrong verdict without an error. In-set and regex tests on stream columns are
  also unsupported, because `IN` and `LIKE` on a stream return no rows instead of an error.
- Q: Are the tests that give a wrong verdict only documented, or also reported at run time? → A:
  Reported at run time (chosen by Henrique Dias on 2026-11-27).
  - An IRIS test-suite interface is registered as the connector's test-suite class. It recognizes the
    regex tests, and the in-set and regex tests on stream columns.
  - For each of them it gives an `Aborted` result with the reason instead of running the validator.
  - It records one `IRIS-PROFILER-UNSUPPORTED` warning per test type per run.
  - Every other test runs unchanged.

  The histogram and the stream metrics are only documented, because their failures already reach
  the status with the IRIS error. This adds a mechanism, so ADR-0016 is amended in the same change.
- Q: Where are the expected values kept? → A: In one expected-values module in the test package,
  derived from the same row definitions the fixture loader uses.
- Q: Thread count? → A: IRIS Community runs out of licenses under the profiler's default thread
  count. Tests set a thread count of 5. Spec 008's docs explain why.

## User Scenarios & Testing *(mandatory)*

Actors: the **data steward** who profiles IRIS tables and reads their metrics in OpenMetadata; the
**data engineer** who writes data-quality tests on IRIS tables; the **IRIS administrator** who grants
the ingestion login. Profiling and test runs are started from OpenMetadata as for any SQL database.

### User Story 1 - Profile an IRIS table and get its metrics (Priority: P1)

The data steward runs the profiler on an IRIS table. The table and its columns get the same metrics as
on other SQL databases, wherever the column type supports them.

**Why this priority**: profiling is the first data-quality feature users look for, and the PRD's
FR-16 asks for it.

**Independent Test**: profile `Clinic.Patient`, `Clinic.Encounter` and `Types.AllTypes` without
sampling, then compare each metric with the expected-values module.

**Acceptance Scenarios**:

1. **Given** the shared fixtures, **When** the profiler runs on `Clinic.Patient` on any matrix cell,
   **Then** the row count and column count equal the fixture's.
2. **Given** a non-stream column, **When** it is profiled, **Then** the metrics listed as supported in
   the matrix equal the expected values. These are:
   - values count, null count and proportion;
   - distinct, unique and duplicate counts and proportions;
   - min, max, mean, sum, standard deviation;
   - min and max length.
3. **Given** a numeric column with NULLs (`Clinic.Patient.Weight`), **When** it is profiled, **Then**
   median, first quartile and third quartile equal the discrete percentiles computed from its non-NULL
   values, and interquartile range and non-parametric skew follow from them.
4. **Given** the least-privilege login `omd_reader`, **When** it profiles the same tables, **Then** the
   results are the same as the administrator's.

---

### User Story 2 - Run built-in data-quality tests and get correct verdicts (Priority: P1)

The data engineer adds the built-in table and column tests to an IRIS table. Each test runs and
reports the right pass or fail verdict.

**Why this priority**: the PRD's FR-17. A test that reports the wrong verdict is worse than a test
that cannot run, so verdicts are checked, not only that the run completes.

**Independent Test**: run each supported test once with parameters that must pass and once with
parameters that must fail, on the fixture tables, as administrator and as `omd_reader`.

**Acceptance Scenarios**:

1. **Given** the supported table tests, **When** they run with passing and failing parameters,
   **Then** each gives the expected verdict. The tests are row count between and equal, column count
   between and equal, column name exists, and columns match set.
2. **Given** the supported column tests on non-stream columns, **When** they run with passing and
   failing parameters, **Then** each gives the expected verdict. The tests are:
   - not null, unique, missing count;
   - values between (numeric and timestamp), in set, not in set;
   - value lengths between;
   - max, min, mean, median, standard deviation and sum between.
3. **Given** any test, **When** it runs as `omd_reader`, **Then** the verdict is the administrator's.

---

### User Story 3 - Sample large tables by row count (Priority: P2)

The data steward sets a row-count sample on a table, so that the profiler and the tests read only
part of it. On IRIS the sample is the first `n` rows. Sampling modes that IRIS cannot run are
reported, never silently replaced.

**Why this priority**: today every sampled profile on IRIS fails, whatever the mode. Row-count
sampling is what users rely on for large tables.

**Independent Test**: profile a fixture table with a row-count sample, randomized and not; then with
a percentage sample; count the rows the metrics saw and the warnings in the status.

**Acceptance Scenarios**:

1. **Given** a row-count sample of `n` with randomization off, **When** the profiler runs, **Then** the
   metrics are computed on `n` rows and no warning is recorded.
2. **Given** a row-count sample of `n` with randomization on (the default), **When** the profiler runs
   on several tables, **Then** each table's metrics are computed on its first `n` rows, and the
   status holds exactly one `IRIS-PROFILER-UNSUPPORTED` warning for the run. The warning says that
   randomized sampling was asked for and non-randomized sampling ran.
3. **Given** a percentage sample, **When** the profiler runs on several tables, **Then** no sampled
   metric is computed for those tables, no query reads them in full in its place, and the status
   holds exactly one `IRIS-PROFILER-UNSUPPORTED` warning for the run. The warning says that
   percentage sampling is not supported and a row count can be used instead.
4. **Given** a table whose sample name would start with a digit, **When** it is sampled by row count,
   **Then** sampling works as for any other table.
5. **Given** the data-quality tests on a sampled table, **When** they run, **Then** they use the same
   sampler, with the same results and warnings.

---

### User Story 4 - What IRIS cannot do is listed and never breaks the run (Priority: P2)

Some metrics and tests cannot run on IRIS. The user finds each of them, with the reason, in the
supported-metrics matrix and in the Gap Report. A profiler run that meets one still completes.

**Why this priority**: constitution V. Three of the SPIKE-04 findings were silent wrong results.

**Independent Test**: profile every fixture table and run every built-in test on the matrix cells,
then check that the run completes and that every unsupported item is in the matrix and the Gap Report.

**Acceptance Scenarios**:

1. **Given** the fixture tables with stream and decimal columns, **When** the profiler runs on all of
   them, **Then** the run completes on every cell and the workflow meets its default success
   threshold.
2. **Given** the supported-metrics matrix, **When** a reader looks up any built-in metric, sampling
   mode or built-in test, **Then** it shows supported or unsupported, and each unsupported row gives
   the reason and the Gap Report entry.
3. **Given** a regex test on any column, or an in-set test on a stream column, **When** the test run
   meets it, **Then**:
   - its result is `Aborted` with the reason, never pass or fail;
   - the status holds one `IRIS-PROFILER-UNSUPPORTED` warning per test type for the run;
   - the other tests of the suite still run and give their verdicts.
4. **Given** the histogram or a stream column, **When** the profiler meets it, **Then** the profiler's
   own failure entry, with the IRIS error, is the report. The matrix explains it.

### Edge Cases

- **Same table name in two schemas** (`Clinic.Patient` and `Billing.Patient`): median and quartiles
  are computed on the schema-qualified table, never on a table found by name alone (Principle III).
- **A column that is entirely NULL, or an empty table:** metrics are NULL or zero as on other
  databases. The median does not fail.
- **Text columns:** mean, sum and standard deviation are based on value length, as on other
  databases.
- **Integer histograms:** they work on IRIS when every bin bound is an integer. The matrix still lists
  the histogram as unsupported in v1, because the result depends on the column's values.
- **VECTOR columns** (`AI.Embedding`): profiling their contents is out of scope. What the profiler
  does on them, with and without the dictionary grant, is recorded in research. A run that includes
  them completes.
- **The view `Clinic.ActivePatient`:** profiled as a table. Metrics come from the view's rows.
- **IRIS Community licenses:** a thread count above 5 can lose metrics with `Unable to allocate a
  license`. Tests set 5. The docs note is spec 008's.
- **A row-count sample larger than the table:** every row is read, with no warning.
- **Percentage and randomization both set:** one warning, for the percentage. No metric is computed
  on a substitute.

## Requirements *(mandatory)*

### Functional Requirements

**Registry and SQL overrides (ADR-0010)**

- **FR-001**: The IRIS dialect MUST be registered in OpenMetadata's profiler registry. Without that,
  no dialect-specific override applies to IRIS.
- **FR-002**: Median, first quartile and third quartile MUST be computed on IRIS through one
  `@compiles(MedianFn, "iris")` override. Its values MUST be:
  - discrete percentiles, as OpenMetadata's MySQL form gives;
  - computed on the schema-qualified table;
  - computed with NULLs excluded.

  The test "column median between" MUST give the expected verdict.
- **FR-003**: Any further `@compiles` override MUST be backed by a failing supported metric or test.
  Each override MUST have:
  - a unit test of its compiled SQL;
  - an integration test of the value it gives.
- **FR-004**: The only shared OpenMetadata files this spec changes MUST be the profiler registry and
  the median function. Each change is a minimal, grouped patch. The histogram, the base sampler and
  the data-quality validators MUST NOT be patched.

**Sampling (ADR-0016)**

- **FR-005**: An IRIS sampler MUST be registered as the connector's sampler, so that the profiler and
  the data-quality test runner both use it for an IRIS service.
- **FR-006**: Every CTE name the sampler produces MUST be a valid unquoted IRIS identifier. That holds
  whatever the table's name, including when the base digest starts with a digit.
- **FR-007**: Row-count sampling with randomization off MUST return the first `n` rows (`TOP n`). The
  supported metrics MUST run on that sample.
- **FR-008**: Row-count sampling with randomization on MUST run as FR-007. It MUST record one
  `IRIS-PROFILER-UNSUPPORTED` warning per run.
- **FR-009**: Percentage sampling MUST compute no sampled metric and give no test verdict for that
  table. No query MUST read the table in full in its place. It MUST record one
  `IRIS-PROFILER-UNSUPPORTED` warning per run.
- **FR-010**: The sampler MUST add no SQL of its own: no random function, no ordering, no modulo. It
  builds its queries with the base sampler's code, and changes only the CTE names and which branch
  runs.
- **FR-011**: Each `IRIS-PROFILER-UNSUPPORTED` warning MUST meet these rules:
  - It goes into the ingestion status, keyed on the FQN of the first table that asked for the mode.
  - It is recorded once per run for each unsupported mode.
  - Its message names the mode asked for, the reason, and what ran instead.

  The warnings contract MUST be updated to this form. Today it says "metric `<metric>`".

**Unsupported metrics and tests**

- **FR-012**: The following MUST be listed as unsupported in the matrix and the Gap Report, and MUST
  NOT be emulated:
  - the histogram;
  - every static metric of stream columns;
  - the regex tests;
  - in-set and regex tests on stream columns.

  For the histogram and the stream metrics, the profiler's own per-column failure entry with the
  IRIS error is the run-time report. No IRIS profiler interface is added.
- **FR-012a**: An IRIS test-suite interface MUST be registered as the connector's test-suite class.
  For the tests it covers, it MUST give an `Aborted` result whose message names the test, the column
  and the reason, and it MUST NOT run their validator. It MUST record one `IRIS-PROFILER-UNSUPPORTED`
  warning per test type per run, keyed on the FQN of the first table that met it.
  - Covered on any column: "values to match regex" and "values to not match regex".
  - Covered on stream columns only: "values to be in set", "values to be not in set" and "value
    lengths between".
  - Every other test MUST run through the base interface unchanged.
- **FR-012b**: The test-suite interface MUST decide only from the test's definition name and the
  column's type in the table entity. It MUST NOT add SQL, rewrite a test or compute a verdict.
- **FR-013**: No unsupported metric or test may fail the whole run. Over all fixture tables, a
  profiler run and a test run MUST complete on every matrix cell, and the workflow MUST meet its
  default success threshold.

**Fixtures**

- **FR-014**: `Clinic.Patient` and `Clinic.Encounter` MUST hold at least 50 rows each, generated in
  the loader with no randomness. The rows MUST include:
  - NULLs in every nullable column;
  - duplicate values in at least one text column and one numeric column;
  - fractional values in `Weight`, enough for decimal bin bounds;
  - stream values in `Notes`, `checkup` among them.

  The existing rows MUST keep their values. The catalog version MUST go up by one, with a history
  line. The self-check row counts and the fixtures contract MUST be updated. The change is additive:
  no object, column or grant changes.
- **FR-015**: The expected values MUST be kept in one module in the test package, derived from the
  loader's row definitions, not copied by hand. They cover each supported metric of the tested
  columns and each test's passing and failing parameters.

**Tests**

- **FR-016**: Integration tests marked `iris` MUST run on every matrix cell, as each login. They MUST
  check:
  - every supported metric of the matrix on `Clinic.Patient`, `Clinic.Encounter` and
    `Types.AllTypes` (US1);
  - every supported test, with a passing and a failing case (US2);
  - the three sampling modes and their warning counts (US3);
  - the aborted tests of FR-012a and their warning counts, including on `Clinic.Encounter.Notes`
    (US4);
  - that the run completes over all fixture tables (FR-013).

  They MUST set a thread count of 5 and run without an OpenMetadata server, as SPIKE-04 did.
- **FR-017**: Unit tests MUST cover:
  - the compiled SQL of the median override;
  - the sampler's compiled SQL for each case of ADR-0016's table, including a table whose digest
    starts with a digit;
  - that no compiled sample query contains a random function or `%`;
  - that the test-suite interface aborts exactly the tests FR-012a covers and passes every other
    test to the base interface;
  - that each warning is recorded once per run.

**Documentation and records**

- **FR-018**: `quickstart.md` MUST hold the supported-metrics matrix for spec 008. Its rows are:
  - every built-in table and column metric;
  - every sampling mode;
  - every built-in table and column test;
  - stream columns as a row of their own.

  Each row says supported or unsupported. An unsupported row gives the reason and its Gap Report
  entry. The matrix also carries the thread-count note for IRIS Community.
- **FR-019**: `GAP-REPORT.md` MUST gain one entry per IRIS limitation, each with a reproduction and
  per-track results:
  - delimited CTE names are rejected;
  - no random function;
  - no percentile function, handled by the median override;
  - delimited identifiers cannot contain `.` (histogram);
  - length, distinct count, min, max and cast are not supported on streams;
  - `IN` and `LIKE` on a stream return no rows;
  - no regex predicate, which OpenMetadata's `LIKE` fallback turns into wrong verdicts.

  Ids are assigned in order after the last existing entry.
- **FR-020**: ADR-0016 MUST be amended in the same change to add the test-suite interface of FR-012a.
  The amendment covers the decision, its conditions (FR-012b) and its validation. If the
  implementation changes any other decision of ADR-0010 or ADR-0016, that ADR MUST also be updated in
  the same change. ADR-0016's "Validation" section is part of this spec's acceptance.

### Key Entities

- **Supported-metrics matrix**: one row per metric, sampling mode or test, with supported or
  unsupported, the reason and the Gap Report id. Spec 008 publishes it.
- **Expected values**: per table and column, the value of each supported metric, and per test, the
  parameters that pass and those that fail. Derived from the fixture rows.
- **Unsupported-mode warning**: `IRIS-PROFILER-UNSUPPORTED`, at most one per mode per run, keyed on
  a table FQN.
- **IRIS sampler**: the connector's sampler, with the base sampler's queries, unquoted CTE names and
  no randomization.
- **IRIS test-suite interface**: the connector's test-suite class. It aborts the tests IRIS cannot
  evaluate correctly, and passes every other test to the base interface.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all three tracks, as administrator and as `omd_reader`, 100% of the supported metrics
  on the three tested fixture tables equal their expected values.
- **SC-002**: On the same cells, every supported test gives the expected verdict in both its passing
  and its failing case. There are no wrong verdicts among the supported tests.
- **SC-003**: Row-count sampling works on every fixture table, including one whose digest starts with
  a digit. Today it works on no table whose digest starts with a digit.
- **SC-004**: A run over all fixture tables with randomized or percentage sampling records exactly one
  warning per unsupported mode, whatever the number of tables.
- **SC-005**: A profiler run and a test run over all fixture tables complete on every cell, and the
  workflow meets its default success threshold.
- **SC-006**: Every metric, sampling mode and built-in test appears in the matrix. Every unsupported
  row has a Gap Report entry with a reproduction.
- **SC-007**: Each IRIS-specific adjustment has its own unit test: the median override, the sampler
  and the test-suite interface.
- **SC-008**: No test gives a wrong verdict on any cell. The regex tests and the stream in-set tests
  end as `Aborted` with one warning per test type per run.

## Assumptions

- SPIKE-04's results, the same on the three tracks and for both logins, hold for the grown fixtures.
- The profiler and the tests need only `SELECT` on the tables (SPIKE-04). `omd_reader` already has
  it on `Clinic`, `Billing`, `AI` and `Types`. No new grant or login is needed.
- The profiler's default success threshold is OpenMetadata 2.1.1's. Whether the per-column failures
  of stream columns stay under it is checked in the plan's research.
- The tests run the profiler and the test runner in process against IRIS, as SPIKE-04 did, with no
  OpenMetadata server. An end-to-end run through the UI belongs to spec 008's demo.
- Specs 002, 003 and 005 merge first. This branch starts from 004 (fixture catalog v4).

## Out of Scope

- Custom metrics, data diff, system metrics.
- Profiling VECTOR contents.
- Performance tuning, and any thread-count setting beyond what the tests need.
- A deterministic stand-in for random sampling, a capped full-table read for percentages, and a
  histogram patch (ADR-0016).
- The documentation site itself. Spec 008 publishes the matrix and the notes.
