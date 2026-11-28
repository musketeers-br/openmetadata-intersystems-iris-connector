# Quickstart: Profiler and data quality

How to check this feature, and the supported-metrics matrix for spec 008's docs.

## Check it

**Prerequisites:**

- WSL2 or Linux with Docker Engine;
- `make om-import`;
- an IRIS cell started and seeded (`make iris-up TAG=latest-em`, catalog v5).

**Steps:**

| # | Run | Expected |
|---|---|---|
| Q1 | `pytest fixtures` | The self-check passes with `FIXTURES OK v5`. `expected.py` matches its hand-counted values |
| Q2 | the unit tests (`.om/ingestion`): `pytest tests/unit/topology/database/test_iris_sampler.py test_iris_test_suite.py test_iris_median.py` | Compiled SQL: no quoted CTE name (`Patient`, whose digest starts with `0`, included), no random function, no `%`. Median: no `percentile_cont`. Interface: aborts exactly the covered tests. Warnings: once per run |
| Q3 | `make test-cell TAG=latest-em LOGIN=admin` | `test_profiler.py`: every supported metric equals `expected.py`. `test_data_quality.py`: every supported test passes and fails as expected. `test_sampling.py`: row count works, and the warning counts are 1 |
| Q4 | `make test-cell TAG=latest-em LOGIN=reader` | Same results as Q3. On top of that, one `IRIS-ACCESS: cannot read profile of Restricted.Secret` and one for `Restricted.ColumnGrant`, and no metric query on them |
| Q5 | the same on `latest-cd` and `latest-preview`, and as `reader_dict` | Same results |
| Q6 | A profiler run over all fixture tables (`test_profiler.py::test_run_meets_threshold`) | Completes. The step's success ratio is 90% or more. Stream columns and decimal histograms show the profiler's own failures |
| Q7 | `make om-export && make om-check` | No diff. Only `overlay/` and the two patches changed |

## Supported-metrics matrix (for spec 008)

These are the results on IRIS Community 2026.1 and 2026.3, as administrator and as a `SELECT`-only
login. GAP ids point to `GAP-REPORT.md`.

### Table metrics

| Metric | IRIS | Note |
|---|---|---|
| Row count | supported | `COUNT(*)` |
| Column count, column names | supported | |
| System metrics (DML counts) | not supported | IRIS has no DML statistics view the framework reads. Out of scope |

### Column metrics (non-stream columns)

| Metric | IRIS | Note |
|---|---|---|
| Values count, null count, null proportion | supported | On IRIS 2026.3 the connector writes COALESCE's constant as a literal, because 2026.3 refuses an untyped parameter there. GAP-020 |
| Distinct, unique and duplicate counts and proportions | supported | |
| Min, max | supported | |
| Mean, sum, standard deviation | supported | For text columns these are based on value length, as on other databases. The sum is OpenMetadata's `SUM(CAST(x AS BIGINT))`: IRIS truncates each value to an integer first. Standard deviation is the population one |
| Min length, max length | supported | |
| Median, first quartile, third quartile | supported | Discrete percentile (the IRIS override). Computed on the sample when the profile is sampled. The per-dimension median (dimensional test results) is not supported. GAP-015 |
| Interquartile range, non-parametric skew | supported | Derived from the above |
| Cardinality distribution | supported | |
| Histogram | **not supported in v1** | IRIS rejects `.` in the bin labels the profiler builds. Integer-only bins may work, but this is not guaranteed. GAP-016 |
| Custom metrics | not tested | Out of scope |

### Stream columns (`LONGVARCHAR`/`TEXT`/`CLOB`, `LONGVARBINARY`/`BLOB`/`IMAGE`)

| Metric | IRIS | Note |
|---|---|---|
| Every static metric, null count included | **not supported** | IRIS does not run `LEN`, `COUNT(DISTINCT …)`, `MIN`, `MAX` or `CAST` on streams. The profiler computes a column's static metrics in one query, so all of them fail, and the status shows the profiler's failure for the column. Workaround: exclude stream columns in the table's profiler settings. GAP-017 |
| Median and quartiles of a text stream | **not supported** | The same limitation: one more profiler failure for the column |

### VECTOR columns

| Login | IRIS | Note |
|---|---|---|
| With the dictionary grant (catalogued as `ARRAY`) | not profiled | The profiler skips array columns. There is no failure |
| Without it (catalogued as `VARCHAR`) | **not supported**: exclude them | Their static metrics fail (`SQLCODE -400`, `-255` "A value of SQL type Vector is not allowed"), and the median of their length comes back as a meaningless number. Exclude VECTOR columns in the table's profiler settings |

### Sampling

| Mode | IRIS | Note |
|---|---|---|
| None (whole table) | supported | |
| Row count, not randomized | supported | The first `n` rows in IRIS's order |
| Row count, randomized | **not randomized** | The first `n` rows, with one warning per run. Randomized is the default for data-quality test runs in OpenMetadata 2.1.1. GAP-014 |
| Percentage below 100 | **not supported** | The table is not profiled. You get one warning per run and one failure per table. Set a row count instead. GAP-014 |
| Percentage 100 | supported | The whole table |
| Custom sample query | supported | |
| Any sampled profile, by table name | supported | IRIS rejects delimited CTE names, and the IRIS sampler avoids them. GAP-013 |

### Table tests

| Test | IRIS |
|---|---|
| Row count between, row count equal | supported |
| Column count between, column count equal | supported |
| Column name exists, columns match set | supported |
| Custom SQL | supported |
| Row inserted count between | not tested (needs a partition column) |
| Table diff | out of scope |

### Column tests

| Test | Non-stream columns | Stream columns |
|---|---|---|
| Not null | supported | supported (`IS NULL` works on streams) |
| Missing count | supported | **aborted**: conditions on stream columns are not supported (IRIS gives `SQLCODE -313`) |
| Unique | supported | **aborted**: IRIS does not compare stream values in `GROUP BY`, so OpenMetadata would report no duplicates. GAP-018 |
| Between (numeric, timestamp) | supported | not applicable |
| In set, not in set | supported | **aborted**: `IN` on a stream returns no rows. GAP-018 |
| Value lengths between | supported | **aborted**: no length function on streams |
| Max, min, mean, median, standard deviation, sum between | supported | not applicable |
| Match regex, not match regex | **aborted**: no regex predicate. OpenMetadata would fall back to `LIKE` and give wrong verdicts. GAP-019 | **aborted** |

"Aborted" means the test ends with an `Aborted` result and the reason, never with a pass or fail
verdict. The run records one warning per test type.

### Connections on IRIS Community

Set the profiler's `threadCount` to 5 or less. Without it, the profiler opens up to 20 sessions and
IRIS Community runs out of licenses (`Unable to allocate a license`), which loses metrics.

### Grants

`SELECT` on the tables is enough for profiling and tests. A table the login can list but not read
gets one `IRIS-ACCESS: cannot read profile of <Schema>.<Table>` warning and is not profiled.

With a column-level grant (`GRANT SELECT (col) ON …`), the table is profiled on the columns the
login can read. Its row count fails with the IRIS error, because IRIS refuses `COUNT(*)` without a
table-level `SELECT`.
