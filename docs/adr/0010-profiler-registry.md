# ADR-0010 — Profiler and DQ through the dialect registry and `@compiles`

- **Status:** Accepted · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-10 · **Binds:** FR-16, FR-17 · **Constitution:** I, V

## Context

OpenMetadata's profiler and data-quality tests run SQLAlchemy expressions through a dialect registry (`profiler/orm/registry.py`). Where a database's SQL differs, connectors add `@compiles` overrides in `profiler/orm/functions/`, for example for `median`, `random_num` and `length`.

Sampling may rely on functions such as `TABLESAMPLE` or `RANDOM()` that IRIS may not support. Which metrics fail on IRIS is unknown until SPIKE-04.

## Decision

- Add the IRIS dialect to `profiler/orm/registry.py`.
- Add `@compiles(…, "iris")` overrides **only** for functions that fail on IRIS, **each with a test**.
- Metrics and tests that cannot run on IRIS are listed, with the reason, in:
  - the docs' supported-metrics matrix;
  - the Gap Report.

  They are not emulated.
- No custom profiler or sampler unless SPIKE-04 shows sampling cannot work otherwise. That would need a new ADR.

## Consequences

- The overrides live outside `iris/` (in `profiler/orm/functions/`), so spec 006 touches shared OpenMetadata files. Keep each diff minimal and grouped by function.
- If time runs short, the **regex test and advanced data-quality tests** are cut first (cut order: 010 → 004 → advanced DQ in 006 → TLS in CI).

## Validation

Spec 006:
- every supported metric and test passes on the seed tables on all matrix cells;
- each `@compiles` override has a unit test;
- unsupported items appear in the docs matrix and the Gap Report.
