# ADR-0016 — An IRIS sampler: unquoted CTE names, no percentage or randomized sampling

- **Status:** Accepted · **Date:** 2026-11-27 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-16 (new) · **Binds:** FR-16, FR-17 · **Constitution:** I, V
- **Refines:** [ADR-0010](0010-profiler-registry.md) (the "new ADR" it requires for a sampler) · **Evidence:** SPIKE-04

## Context

SPIKE-04 ran OpenMetadata 2.1.1's profiler and SQL data-quality tests in process against IRIS Community 2026.1 and 2026.3 (all three matrix tracks), as `_SYSTEM` and as the least-privilege login, with `sqlalchemy-intersystems-iris` 1.0.2.

Without sampling, the profiler and most tests work through the dialect registry, as [ADR-0010](0010-profiler-registry.md) planned. **Every sampled profile fails**, for two reasons that `@compiles` cannot fix:

- **IRIS rejects every delimited CTE name.** `WITH "abc" AS (…)` fails with `SQLCODE -400`, even for `"ABC"`; `WITH abc AS (…)` works.
  - `SQASampler` names all its CTEs (`_rnd`, `_sample`, `_partitioned`, `_user_sampled`) after `get_sampler_table_name()`, an MD5 hex digest of the table name.
  - A digest that starts with a digit is always quoted, so whether sampling works depends on the table's name.
  - The name is chosen by the sampler class, not by a SQL function, so there is nothing to `@compiles`.
- **IRIS SQL has no random function.** `RAND`, `RANDOM`, `NEWID`, `{fn RAND()}` and `$RANDOM` are all refused, and extrinsic functions are disabled.
  - Percentage sampling and randomized row sampling are both built on `ModuloFn(RandomNumFn(), …)`.
  - Randomized row sampling is the default (`randomizedSample: true`).
  - There is no IRIS function to compile `RandomNumFn` to. A deterministic stand-in (for example a hash of `%ID`) would be emulation, which [ADR-0010](0010-profiler-registry.md) and [ADR-0013](0013-gap-report.md) rule out.

When SPIKE-04 prefixed the digest with a letter, row-count sampling with `randomizedSample: false` returned 10 of 100 rows and every metric ran.

OpenMetadata already ships per-database samplers that subclass `SQASampler` and are registered through the connector's `service_spec` (`sampler_class`), for example MSSQL, Oracle and Trino.

## Decision

`iris/` gets an `IrisSampler(SQASampler)` (`sampler.py`), registered as `sampler_class` in the connector's `service_spec.py`. It changes exactly two things:

| Behaviour | Base `SQASampler` | `IrisSampler` |
|---|---|---|
| CTE names | MD5 hex digest, quoted when it starts with a digit | The same digest behind a fixed letter prefix, so the name is a valid unquoted identifier (no other change to its length or uniqueness) |
| Row-count sampling, `randomizedSample: false` | `TOP n` of the table | Unchanged |
| Row-count sampling, `randomizedSample: true` (default) | Orders by `ModuloFn(RandomNumFn(), n)` | **Unsupported:** runs as `randomizedSample: false` (`TOP n`, no ordering) |
| Percentage sampling | Filters on `ModuloFn(RandomNumFn(), 100)` | **Unsupported:** the table's sampled metrics are skipped; nothing is computed on a substitute |

- Each unsupported request is reported **once per run** as an `IRIS-PROFILER-UNSUPPORTED` warning in the ingestion status ([ADR-0008](0008-access-gaps-as-warnings.md)). The warning says what was asked and what ran instead.
- **No SQL rewriting and no emulation.** The sampler builds its queries with the base class's code. It only changes the name and which branch runs. It does not add a random function, an ordering or a modulo of its own.
- **One place:** `iris/sampler.py`, with a unit test of the compiled SQL for each row of the table above. The integration tests run sampled profiles on every matrix cell, as the least-privilege login too.
- Percentage sampling has no substitute:
  - A row count computed from `COUNT(*)` would label a deterministic first-N% as a percentage sample.
  - Reading the whole table instead was considered. It is safe only with a row cap above which the metrics are skipped, and that cap would be a new IRIS-only setting. It is left out of v1.

  A user who needs a sample sets a row count.

### Related SPIKE-04 decisions (under ADR-0010's rules, no new mechanism)

- **Median and quartiles:** one `@compiles(MedianFn, "iris")` override in the window form SPIKE-04 prototyped, with its own test. No `ModuloFn` override: percentage and randomized sampling were its only users, and both are unsupported here.
- **Histogram:** unsupported in v1. IRIS rejects delimited identifiers that contain `.`, and bin labels such as `"61.500 to 71.750"` come from `Histogram._format_bin_labels`, which is outside `profiler/orm/`. It is listed in the docs matrix and the Gap Report. `histogram.py` is not patched.
- **Stream columns** (`LONGVARCHAR` → `TEXT`, `LONGVARBINARY` → `BLOB`, [ADR-0006](0006-single-type-map.md)): documented as not profiled. IRIS does not support `LEN`, `COUNT(DISTINCT …)`, `MIN`, `MAX` or `CAST` on streams. The profiler runs a column's static metrics in one query, so the column gets none, including null count. In-set and regex tests on streams are listed as unsupported, because `IN` and `LIKE` on a stream return no rows instead of an error.
- **Spec 008's docs** carry the remaining findings:
  - regex tests are unsupported (OpenMetadata falls back to `LIKE` and gives wrong verdicts without an error);
  - the stream `IN`/`LIKE` behaviour;
  - `threadCount` of 5 or less on IRIS Community, whose license runs out under the default thread count.

## Consequences

- Sampled profiles work on every table, whatever its name. Row-count samples are the first `n` rows in IRIS's order, not a random sample. The docs say so.
- A table configured for percentage sampling gets no sampled metrics on IRIS until its configuration changes to a row count. The warning says so.
- The connector adds one file in `iris/` and one line in `service_spec.py`. No shared OpenMetadata sampler file changes. Spec 006 touches shared files only for the registry entry and the `MedianFn` override ([ADR-0010](0010-profiler-registry.md)).
- Gap Report candidates, with ids assigned in spec 006:
  - delimited CTE names;
  - no random function;
  - no percentile function;
  - `.` in delimited identifiers;
  - stream `IN`/`LIKE`;
  - no regex predicate.
- **Removable:** if a later IRIS accepts delimited CTE names, the name override goes. If IRIS gains a random function, a `@compiles(RandomNumFn, "iris")` replaces the two unsupported branches, and ADR-0010's rules then cover it.

## Validation

Spec 006, on all matrix cells, as the least-privilege login too:

- `IrisSampler` is the sampler the profiler and the test-suite runner use for an IRIS service.
- Row-count sampling, randomized or not, returns `n` rows, and the supported metrics run on the sample. The randomized request raises exactly one `IRIS-PROFILER-UNSUPPORTED` warning per run.
- Percentage sampling computes no sampled metric and raises exactly one warning per run. No query reads the whole table in its place.
- Unit tests check that no compiled CTE name is quoted, including for a table whose digest starts with a digit, and that no compiled sample query contains a random function or `%`.
