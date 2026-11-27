# Data model: Profiler and data quality

## IRIS sampler

`IrisSampler(SQASampler)`, in `iris/sampler.py` and registered as `sampler_class` (ADR-0016).

| Case | Base `SQASampler` | `IrisSampler` |
|---|---|---|
| CTE names (`_rnd`, `_sample`, `_partitioned`, `_user_sampled`) | `get_sampler_table_name()` = MD5 hex digest | `"s" + digest`, a valid unquoted identifier |
| No sample configured | the whole table | unchanged |
| Row count `n`, randomization off | `TOP n` | unchanged |
| Row count `n`, randomization on | orders by `ModuloFn(RandomNumFn(), count)` | runs as randomization off, plus one warning per run |
| Percentage 100 | the whole table (randomized: random order) | the whole table, plus the randomization warning if randomization is on |
| Percentage < 100 | filters on `ModuloFn(RandomNumFn(), 100)` | raises `IrisSamplingSkipped` in the constructor, plus one warning per run (research R3) |
| User sample query | `_rdn_sample_from_user_query` | unchanged except the CTE name |
| Login cannot read the cataloged columns | every metric task fails | raises `IrisSamplingSkipped`, plus one `IRIS-ACCESS` per table |

`is_skippable_sampling_error(exc)` is true for `IrisSamplingSkipped`. The randomization flag is
read from `self.sample_config.randomizedSample`. The constructor runs the base constructor first,
then the readability check, then the percentage check.

## IRIS test-suite interface

`IrisTestSuiteInterface(SQATestSuiteInterface)`, in `iris/test_suite_interface.py` and registered as
`test_suite_class`.

| Test definition | Column `dataType` | Result |
|---|---|---|
| `columnValuesToMatchRegex`, `columnValuesToNotMatchRegex` | any | `Aborted`, reason "no regular-expression predicate" |
| `columnValuesToBeInSet`, `columnValuesToBeNotInSet` | `TEXT`, `BLOB` | `Aborted`, reason "IN on a stream column returns no rows" |
| `columnValueLengthsToBeBetween` | `TEXT`, `BLOB` | `Aborted`, reason "length functions are not supported on stream columns" |
| anything else | any | the base `run_test_case` |

## Per-run report record

`_REPORTED: WeakKeyDictionary[OpenMetadata, set[str]]`, in `iris/sampler.py`. It is shared by the
sampler and the interface.

| Report key | Warning |
|---|---|
| `randomized` | the randomized-sampling warning |
| `percentage` | the percentage-sampling warning |
| `test:<definition>:<column kind>` | the warning for one aborted test type |
| `access:<table FQN>` | `IRIS-ACCESS` for one table |

## Shared OpenMetadata changes (patches)

| File | Change |
|---|---|
| `profiler/orm/registry.py` | `Iris = "iris"` in `PythonDialects` |
| `profiler/orm/functions/median.py` | `@compiles(MedianFn, Dialects.Iris)`, the SPIKE-04 window form (research R6) |

## Connector changes (overlay)

| File | Change |
|---|---|
| `iris/service_spec.py` | `sampler_class=IrisSampler`, `test_suite_class=IrisTestSuiteInterface` |
| `iris/sampler.py` | new |
| `iris/test_suite_interface.py` | new |
| `iris/compiles.py` | new (T012): `@compiles(coalesce, "iris")`, bound values as literals (IRIS 2026.3, `SQLCODE -378`); imported by `service_spec.py` |

## Fixture catalog v5

| Table | Rows | Generated values |
|---|---|---|
| `Clinic.Patient` | 60 (ids 1–60; 1 and 2 unchanged) | `FullName`: 12 names, cycled. `BirthDate`: NULL when `i % 10 == 0`. `Weight`: `40.00 + (i * 7.25) % 80`, NULL when `i % 7 == 0` |
| `Clinic.Encounter` | 60 (ids 10–69; 10 unchanged) | `PatientId`: `1 + (i % 60)`. `StartedAt`: one hour apart, NULL when `i % 9 == 0`. `Notes`: `checkup`, `follow-up`, `lab results`, cycled, NULL when `i % 8 == 0`. `Active`: `i % 2` |

The exact formulas are settled in the loader. `expected.py` derives everything from the same
generator. `VERSION_HISTORY[5] = "spec 006: Clinic.Patient and Clinic.Encounter grown to 60
deterministic rows (NULLs, duplicates, fractional Weight, stream Notes)"`.

## Expected values (`tests/integration/iris/data/expected.py`)

For each tested column, `{metric name: value}` for every supported metric of the matrix. For each
test case of the integration tests, `(definition, column, passing params, failing params)`.
Standard deviation is computed the way OpenMetadata computes it for the dialect (population or
sample, as `StdDev` compiles on IRIS). The first integration run confirms which.

## Gap Report entries (ids after the last one at merge time)

| Entry | Reproduction |
|---|---|
| Delimited CTE names rejected | `WITH "abc" AS (SELECT 1 AS x) SELECT x FROM "abc"` → `SQLCODE -400` |
| No random function | `SELECT RAND()`, `RANDOM()`, `NEWID()`, `{fn RAND()}` → refused |
| No percentile function | `percentile_cont(0.5) WITHIN GROUP (ORDER BY x)` → `-359`. Handled by the median override |
| `.` in a delimited identifier | `SELECT 1 AS "1.5 to 2.5"` → `SQLCODE -1` (histogram) |
| Aggregates on streams | `SELECT MIN(Notes) FROM Clinic.Encounter` → `-37`. The same for `LEN`, `COUNT(DISTINCT …)`, `MAX`, `CAST` |
| `IN`/`LIKE` on streams | `SELECT COUNT(*) FROM Clinic.Encounter WHERE Notes IN ('checkup')` → 0 |
| No regex predicate | `REGEXP`, `REGEXP_LIKE` refused. OpenMetadata's `LIKE` fallback gives wrong verdicts |
| `COALESCE` with a bound parameter refused (2026.3) | `SELECT COALESCE(SUM(PatientId), ?) FROM Clinic.Patient` with `(0,)` → `SQLCODE -378` on 2026.3, works on 2026.1. Handled by `iris/compiles.py` |
