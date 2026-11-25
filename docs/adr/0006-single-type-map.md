# ADR-0006 — One type-mapping table owned by `iris/`

- **Status:** Accepted · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-6 · **Binds:** FR-7, FR-11, FR-12 · **Constitution:** III

## Context

Metadata ingestion, the profiler, tests and documentation all need the IRIS → OpenMetadata type mapping. If each of them maps types on its own, they drift apart, and the docs table stops matching what ingestion produces. OpenMetadata connectors register dialect-specific types into the dialect's `ischema_names` and rely on `ColumnTypeParser`. Snowflake's `VECTOR` handling is the closest precedent.

## Decision

- A single module, `iris/types.py`, holds the IRIS SQL type → OpenMetadata `DataType` table. It registers the types into the dialect's `ischema_names` / `ColumnTypeParser` the way other connectors do.
- Unknown types map to `UNKNOWN`, with **one warning per type per run** ([warnings contract](https://github.com/musketeers-br/is-omd/blob/main/docs/contracts/warnings.md)). They never fail the run.
- Both of these are generated from or asserted against this module:
  - the docs type table (spec 008);
  - the type tests (spec 003).

The draft table is in the [type-mapping contract](https://github.com/musketeers-br/is-omd/blob/main/docs/contracts/type-mapping.md).

## Consequences

- Spec 002 consumes the map and does not define types. Spec 004 extends the map's VECTOR entry only through the enrichment hook ([ADR-0007](0007-vector-optional-enrichment.md)).
- Adding a type means one table row and one test. The docs follow automatically.

## Validation

Spec 003:
- every `DATA_TYPE` reported by `INFORMATION_SCHEMA.COLUMNS` on the three release tracks has a row and a test;
- the seed produces zero unknown-type warnings;
- an artificial unknown type produces exactly one warning.
