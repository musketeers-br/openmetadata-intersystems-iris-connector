# Research: Profiler and data quality

Evidence for [plan.md](plan.md). Sources:

- **SPIKE-04**, run in the planning repository before this spec on 2026-11-26. It covered the three
  tracks, as `_SYSTEM` and `omd_reader`, with `sqlalchemy-intersystems-iris` 1.0.2 and OpenMetadata
  2.1.1. R1 copies its results and decisions. The experiment is not redone.
- **Code reading** of OpenMetadata 2.1.1's ingestion tree (`.om/`, 2026-11-27):
  - the sampler (`sampler/sqlalchemy/sampler.py`, `sampler/sampler_interface.py`,
    `sampler/processor.py`);
  - the profiler (`profiler/processor/processor.py`, `profiler/interface/`,
    `profiler/source/database/base/profiler_source.py`);
  - data quality (`data_quality/interface/test_suite_interface.py`,
    `data_quality/processor/test_case_runner.py`, `data_quality/runner/base_test_suite_source.py`);
  - the step framework (`ingestion/api/step.py`, `utils/logger.py`, `workflow/base.py`);
  - the pipeline and entity schemas.

  These sections are R2–R7.
- **The connector as of spec 004**: the `iris/` package, the fixture loader (catalog v4), and spec
  005's access-gap contract and guard test.

No `NEEDS CLARIFICATION` remained in the Technical Context. Two facts rest on code reading only, and
the first implementation task (T-probe in `tasks.md`) checks them on `latest-em` before any feature
code:

- the step warning handler of R2;
- the per-table failure of R3.

## R1 — What SPIKE-04 settled

**What works unchanged**, on every track and for both logins:

- **Table metrics:** row count (through `COUNT(*)`, since there is no IRIS table-metric computer),
  column count and column names.
- **Column metrics on every non-stream type:**
  - values count, null count and proportion;
  - distinct, unique and duplicate counts and proportions;
  - min, max, mean, sum, standard deviation;
  - min and max length, cardinality distribution.

  Strings get length-based mean, sum and standard deviation.
- **Table tests:** row count between and equal, column count between and equal, column name exists,
  columns match set, custom SQL.
- **Column tests:** not null, unique, between (numeric and timestamp), in set, not in set, value
  lengths between, max, min, mean, standard deviation and sum between, missing count.
- **Privileges:** `omd_reader` gets the same results as `_SYSTEM`. `SELECT` on the tables is enough,
  and nothing in `%Dictionary` is read.

**What fails:**

| Item | Behaviour on IRIS | Cause |
|---|---|---|
| Median, quartiles, IQR, non-parametric skew | Silently missing | No `percentile_cont … WITHIN GROUP`, `MEDIAN` or `PERCENTILE` (`SQLCODE -359`) |
| Test "median between" | Aborted, `-359` | Same |
| Histogram | Failure logged, for numeric columns with decimal bin bounds | Labels such as `AS "61.500 to 71.750"`: IRIS rejects `.` in a delimited identifier (`SQLCODE -1`). Integer-only labels work |
| Every sampled profile | Every column metric fails, `-400` | Every delimited CTE name is rejected. CTE names are an MD5 digest, quoted when it starts with a digit |
| Percentage sampling; randomized row sampling | `-359` even once the name is fixed | No random function (`RAND`, `RANDOM`, `NEWID`, `{fn RAND()}`, `$RANDOM` are refused) |
| Regex tests | **Wrong verdict, no error** | No regex predicate. OpenMetadata catches the `REGEXP` error and falls back to `LIKE` with the regex as the pattern |
| Static metrics of stream columns | All fail, null count included (`-37`) | `LEN`, `COUNT(DISTINCT …)`, `MIN`, `MAX`, `CAST` are not supported on streams, and the metrics share one query |
| In-set and regex tests on streams | **Wrong verdict, no error** | `Notes IN ('checkup')` and `Notes LIKE '%check%'` return no rows on a row whose value is `checkup` |

**Prototypes:**

- **Median:** a window form like OpenMetadata's MySQL form gives median 73.50 and quartiles 37.50
  and 112.50 on 100 rows with 10 NULLs, as computed in Python. It needs four changes for IRIS:
  - `ROUND(x, 0)`, because `ROUND` needs two arguments;
  - the schema-qualified table, taken from the enclosing `FROM`;
  - an alias for the inner value, because a bare column inside the scalar subquery binds to the
    outer row;
  - NULLs filtered out.
- **Sampler name:** with a letter before the digest, row-count sampling with randomization off
  returns 10 of 100 rows and every metric runs.

**Licenses:** without `threadCount`, the profiler sizes its pool from the task count (5–20 threads).
On `Types.AllTypes`, 16 threads lost four column batches to `Unable to allocate a license`. With 5,
no license error occurred.

**Decisions (both developers, 2026-11-27, ADR-0016):**

- an IRIS sampler, `iris/sampler.py`, registered as `sampler_class`, with unquoted CTE names;
- randomized row sampling runs unrandomized, and percentage sampling is unsupported, each with one
  warning per run;
- no `ModuloFn` override;
- one `@compiles(MedianFn, "iris")` override;
- histogram unsupported in v1;
- stream columns documented as not profiled;
- the regex, stream `IN`/`LIKE` and `threadCount` findings go to spec 008's docs.

**Spec decision (2026-11-27):** the regex tests and the stream in-set tests are also aborted at run
time by an IRIS test-suite interface (spec FR-012a). This amends ADR-0016.

## R2 — How a sampler or a test-suite interface reaches the ingestion status

**Finding:**

- **No status in the interfaces' route.** A sampler holds no `Status`. The profiler interface has
  one (`ProfilerProcessorStatus`), but the profiler step copies only its `records` and `failures`
  (`profiler/processor/processor.py`, `_run`). Warnings recorded there are lost. The test-suite
  interface has no status at all. The test step (`TestCaseRunner`) owns it.
- **The step's warning handler is the route.** Every `Step` builds a `StatusWarningHandler` on its
  own `Status`, and attaches it to the `metadata.Ingestion` logger for the duration of `run()`
  (`ingestion/api/step.py`, `_activate_handler`).
  - Each `WARNING` record on that logger becomes `status.warning(key=record.module,
    reason=record.getMessage())`.
  - Records from the modules `status` and `step` are skipped.
- **The calls run inside the step.** Both run inside the step's `run()`:
  - the sampler, built in `create_profiler_interface` from the profiler step's `_run`, and in
    `create_data_quality_interface` from the test step's `_run`;
  - the test-suite interface.

  A `logger.warning` from `iris/` through `ingestion_logger()` (as `lineage.py` already does)
  therefore lands in that step's status.
- **The handler is attached to one logger.** The sampler's own `metadata.Sampler` logger is a
  sibling of `metadata.Ingestion`, not a child, so its warnings do not reach the handler.

**Decision:** the IRIS sampler and the test-suite interface log their `IRIS-PROFILER-UNSUPPORTED` and
`IRIS-ACCESS` warnings at `WARNING` through `ingestion_logger()`.

- **Key and message:** the status key is the handler's, the module name (`sampler`,
  `test_suite_interface`). The message starts with the code and names the table FQN.
- **Once per run:** the record of what was already reported lives in `iris/sampler.py`. It is a
  `WeakKeyDictionary` keyed on the run's OpenMetadata client, which every sampler and interface of a
  workflow shares. A new workflow gets a new client and so a fresh record.

**Rationale:** it is the framework's own warning path. No shared file changes, and no profiler
interface is added.

**Alternatives considered:**

- **Patch `profiler/processor/processor.py`** to copy the interface's warnings. Rejected: it is a
  shared file, the sampler still has no status to write to, and it would not help the test step.
- **`profiler_class` and `test_suite_class` holding the status.** Rejected: it adds a class only to
  report, and it still meets the processor's dropped warnings.
- **Keying on the table FQN** (the warnings contract's current form). It cannot be done through the
  handler, so the FQN goes into the message, and the contract changes
  ([contracts/profiler-warnings.md](contracts/profiler-warnings.md)).

## R3 — Skipping a table: percentage sampling and unreadable tables

**Finding:** a sampler can skip a table at only one point in 2.1.1 without leaving a substitute
result, and that is when it is built.

- **The profiler step.** `get_profiler_runner` → `create_profiler_interface` → `sampler_class.create`
  runs in `ProfilerProcessor._run` before its `try`. An exception there reaches `Step.run`, which
  records one failure, `Unhandled exception during workflow processing: [<message>]`, and the next
  table goes on. No metric query runs for that table.
- **The test step.** The sampler is built in `create_data_quality_interface`, inside
  `TestCaseRunner._run`. The same exception gives one failure for the table, and its tests are not
  run.
- **The sample-data step** (`sampler/processor.py`, auto-classification) asks
  `sampler_class.is_skippable_sampling_error(exc)`. When the answer is true, it records one status
  warning (`Skipping sample collection for [<fqn>]: <exc>`) and goes on, with no failure.

**Decision:** the IRIS sampler raises one exception type, `IrisSamplingSkipped`, from its
constructor in two cases:

- **(a)** percentage sampling below 100% is configured;
- **(b)** the readability check fails (spec FR-013a).

The exception message is the warning text. In case (a), the sampler also logs the once-per-run
`IRIS-PROFILER-UNSUPPORTED` warning (R2). In case (b), it logs the `IRIS-ACCESS` warning, once per
table. `is_skippable_sampling_error` returns true for `IrisSamplingSkipped`.

- **The readability check:** `select(<the table entity's columns>).limit(0)` through the sampler's
  own session, built with SQLAlchemy and not as raw SQL. It reads no rows.
  - It uses the cataloged columns, not `*`, so a login with a column-level grant
    (`Restricted.ColumnGrant`: `SELECT (Id)`) is checked on the columns it was cataloged with.
  - Only a refused privilege (`SQLCODE -99`) skips the table. Any other error is re-raised.

**Rationale:** it is the only skip with no substitute result. It gives one failure and one warning
per table, instead of one failure per metric task. A percentage of 100 is the whole table, and the
base sampler already treats it as no sampling unless randomization is on (`applies_sampling`). The
IRIS sampler gives it the whole table in both cases: only the order of sample rows would differ, and
the randomization warning still applies.

**Alternatives considered:**

- **Raise from `get_dataset`.** Rejected: it fails every metric task, with one failure each, and
  pushes a reader run over the fixtures toward the success threshold.
- **Return an empty CTE.** Rejected: the metrics would be published as zeros, a wrong result.
- **Read the whole table.** Rejected by ADR-0016.

## R4 — Randomization defaults in 2.1.1

**Finding:** ADR-0016 calls randomized sampling "the default". That holds only for test runs.

- `DatabaseServiceProfilerPipeline.randomizedSample` defaults to `false`, and the profiler source
  passes it on (`_build_default_sample_config`).
- The test step builds `SampleConfig(profileSampleConfig=…)` and so keeps the model's default,
  `randomizedSample = True` (`sampler/models.py`).
- Table, schema and database profiler configs default to `false`.

Sampling applies at all only when a profile sample is configured. With none, the whole table is read
and the sampler changes nothing.

**Decision:** the spec says "the default for data-quality tests". The ADR-0016 amendment corrects its
Context line.

## R5 — The test-suite interface

**Finding:** `TestSuiteInterface.run_test_case(test_case)` runs one test case and returns a
`TestCaseResultResponse`. Its own error path builds an `Aborted` result through
`validator.get_test_case_result_object(…, TestCaseStatus.Aborted, message, …)`. The test step
counts every `Aborted` result as one failure (`_record_if_aborted`), as it already does for
incompatible columns (`filter_incompatible_test_cases`).

**Decision:** `IrisTestSuiteInterface(SQATestSuiteInterface)` lives in `iris/test_suite_interface.py`
and is registered as `test_suite_class`.

- **`run_test_case`:**
  - it reads the definition name from `test_case.testDefinition.fullyQualifiedName`;
  - it reads the column, when there is one, from the test's entity link resolved on
    `self.table_entity`, as the framework's `resolve_column_path` does.
- **Covered:**
  - `columnValuesToMatchRegex` and `columnValuesToNotMatchRegex` on any column;
  - `columnValuesToBeInSet`, `columnValuesToBeNotInSet` and `columnValueLengthsToBeBetween` on a
    column whose `dataType` is `TEXT` or `BLOB`. Those are the stream types of spec 003's map
    (`longvarchar`, `longvarbinary`).
- **For a covered test**, the interface returns a `TestCaseResultResponse` with an `Aborted` result.
  - The result text is `IRIS-PROFILER-UNSUPPORTED: <test> on <column> is not supported on IRIS:
    <reason>`.
  - The validator's own result object builds the result, so the shape matches the framework's.
  - It logs the warning once per test type per run (R2).
- **Any other test** goes to `super().run_test_case`.

**Rationale:**

- One method is overridden, and no SQL is added.
- Aborting is how the framework already reports a test it cannot evaluate.
- "Value lengths between" on streams already aborts with `SQLCODE -37`. It is covered so that the
  reason is IRIS's limitation and not a raw SQL error.

**Alternatives considered:**

- **`@compiles(RegexpMatchFn, "iris")` raising.** Rejected: the validator catches `CompileError` and
  falls back to `LIKE`.
- **Patch the regex validators.** Rejected: they are shared files.

## R6 — Median on IRIS

**Finding:** `MedianFn(col, table_name, percentile[, dimension])`.

- The generic form is `percentile_cont(p) WITHIN GROUP (ORDER BY col)`, which IRIS refuses.
- OpenMetadata's MySQL form (`median.py`, `Dialects.MySQL`) uses a window over a derived table.
  SPIKE-04 adapted it for IRIS (R1).
- `table_name` is `self.col.table.name`, the bare name, so the override takes the qualified table
  from the compiler's current `FROM`.

**Decision:** one `@compiles(MedianFn, Dialects.Iris)` in
`patches/ingestion__src__metadata__profiler__orm__functions__median.py.patch`, in the SPIKE-04 form.

- **Units under test:**
  - median and both quartiles on `Clinic.Patient.Weight` (NULLs present);
  - an all-NULL column;
  - the same table name in two schemas (`Clinic.Patient`, `Billing.Patient`);
  - the compiled SQL, which must contain no `percentile_cont`.
- **Percentile kind:** a discrete percentile, as MySQL's form gives. The docs say so.
- **Dimensional form:** the dimensional variant (the fourth argument, used by dimensional test
  results) follows MySQL's correlation if it compiles on IRIS. Otherwise it is listed unsupported in
  the matrix.

**Registry:** `Iris = "iris"` in `PythonDialects` (`profiler/orm/registry.py`). `Dialects.Iris` then
resolves, and the `EnumAdapter` lookups by dialect name work.

## R7 — Success threshold and the expected failures

**Finding:**

- `successThreshold` defaults to 90. A step meets it if it has no failures, or if
  `records / (records + failures) ≥ 90%` (`workflow/base.py`, `_step_meets_success_threshold`).
- **Profiler step.** A record is one metric task scanned. A failure is one metric task failed, or one
  table skipped (R3).
- **Test step.** A record is one test case evaluated. A failure is one test case aborted, or one
  incompatible case.

**Expected over all fixture tables:**

- **As `_SYSTEM`:**
  - failed static-metric tasks on 3 stream columns (`Clinic.Encounter.Notes`,
    `Types.AllTypes.LongVarCharCol`, `LongVarBinaryCol`);
  - failed histogram tasks on the decimal numeric columns.

  That is under 10% of the metric tasks.
- **As `omd_reader`:** add one failure per unreadable `Restricted` table. Two tables, `Secret` and
  `ColumnGrant`; `Hidden` is not visible.

The ratio is measured by the integration tests (spec FR-013). If it fails, the plan's fallback is the
documented `excludeColumns` for stream columns in the test configuration, and the docs say so. It is
not a code change.

## R8 — Fixture growth (catalog v5)

**Decision:** the loader generates the rows from a pure function of the row index. There is no
`random`.

- **`Clinic.Patient`:** 60 rows.
  - Rows 1 and 2 keep their values, and the other rows are generated.
  - `FullName` cycles through 12 names, which gives duplicates.
  - `BirthDate` is NULL every 10th row.
  - `Weight` is `40.00 + (i * 7.25) mod 80`, with two decimals, and NULL every 7th row.
- **`Clinic.Encounter`:** 60 rows.
  - Row 10 keeps its values.
  - `PatientId` cycles over the patients.
  - `StartedAt` is spaced one hour apart, and NULL every 9th row.
  - `Notes` cycles through `checkup`, `follow-up`, `lab results`, and is NULL every 8th row.
  - `Active` alternates.
- **Bookkeeping:** `EXPECTED["rows"]` becomes 60 and 60, the history line reads
  `5: spec 006: …` (v5), and the fixtures contract row changes.
- **Expected values:** a new module, `overlay/ingestion/tests/integration/iris/data/expected.py`,
  computes them from the same generator: counts, NULLs, distinct values, min and max, mean, sum,
  population standard deviation as OpenMetadata computes it, lengths, and discrete percentiles. They
  are not typed in by hand. The test of the module checks it against a hand count for three values.
- **Unchanged:** `Clinic.ActivePatient` keeps its definition. Its row count follows the data, and
  no test pins it.

## R9 — How the tests drive the profiler and the tests without a server

**Decision:** as SPIKE-04's probes and OpenMetadata's own unit tests do.

- **Interfaces:** the tests build `SQAProfilerInterface` and `SQATestSuiteInterface` in process
  through the connector's `ServiceSpec` classes, so the IRIS sampler and the test-suite interface
  are what runs.
- **Client:** a stub OpenMetadata client answers the database and schema names and the test
  definitions.
- **Status:** a test fixture attaches a `StatusWarningHandler` to `ingestion_logger()` around each
  run, exactly as `Step.run` does, and the assertions read its `Status`.
- **Table skips:** step-level behaviour (R3) is checked by calling `ProfilerProcessor._run` and
  `TestCaseRunner._run` through `Step.run` with a stub record, once per cell.
- **Threads:** `threadCount` is 5 in every profiler config of the tests (R1).
