# Contract: profiler and data-quality warnings

This contract replaces the warnings contract's `IRIS-PROFILER-UNSUPPORTED` row. The old row said
"metric `<metric>`" and was keyed on the table FQN. This contract also adds the `profile` and
`sample data` features of spec 005's `IRIS-ACCESS` contract.

## Route

The IRIS sampler (`iris/sampler.py`) and the IRIS test-suite interface
(`iris/test_suite_interface.py`) log each warning at `WARNING` through `ingestion_logger()`. The
step's own `StatusWarningHandler` records it in the step's status, either the profiler step or the
test step (research R2).

- **Key:** the handler's key, which is the module name: `sampler` or `test_suite_interface`.
- **Table name:** the table FQN is in the reason.

## Warnings

| Code | Reason | Emitted | Also |
|---|---|---|---|
| `IRIS-PROFILER-UNSUPPORTED` | `IRIS-PROFILER-UNSUPPORTED: randomized sampling is not supported on IRIS (no random function); the first <n> rows were sampled instead (first seen on <table FQN>)` | once per run | the profile is computed on the sample |
| `IRIS-PROFILER-UNSUPPORTED` | `IRIS-PROFILER-UNSUPPORTED: percentage sampling is not supported on IRIS (no random function); set a row-count sample instead. <table FQN> was not profiled` | once per run, on the first such table | each such table is skipped, and the framework records one failure for it with the same text (R3) |
| `IRIS-PROFILER-UNSUPPORTED` | `IRIS-PROFILER-UNSUPPORTED: test <definition> on <column type> columns is not supported on IRIS: <reason> (first seen on <column FQN>)` | once per test definition and column kind per run | each such test case gets an `Aborted` result, and the framework counts it as one failure |
| `IRIS-ACCESS` | `IRIS-ACCESS: cannot read profile of <Schema>.<Table>: <first line of SQL error>` | once per table per run | the table is skipped, with one framework failure. `sample data` replaces `profile` in the sample-data step, which records no failure |

`<reason>` for tests:

- `IRIS SQL has no regular-expression predicate` (match and not-match regex);
- `IN on a stream column returns no rows` (in set, not in set);
- `length functions are not supported on stream columns` (value lengths between);
- `IRIS does not compare stream values in GROUP BY` (unique);
- `conditions on stream columns are not supported` (missing count).

## Rules

- **Once:** each warning is recorded once, with a per-run record keyed on the run's OpenMetadata
  client. The `IRIS-ACCESS` warning is recorded once per table.
- **No secrets:** no password, no connection URL, no row data. SQL errors are cut to their first
  line, as in spec 005's contract.
- **Tests:** they assert on the code prefix and the FQN in the reason, never on the SQL error text.
- **Guard:** every `except` in `iris/sampler.py` and `iris/test_suite_interface.py` re-raises or logs
  a warning. Spec 005's guard test covers these files with no allow-list entry.
