# ADR-0006 — One type-mapping table owned by `iris/`

- **Status:** Accepted; revised 2026-11-26 by spec 003 (the observed table, how the map reaches the framework) · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-6 · **Binds:** FR-7, FR-11, FR-12 · **Constitution:** III

## Context

Metadata ingestion, the profiler, tests and documentation all need the IRIS → OpenMetadata type mapping. If each of them maps types on its own, they drift apart, and the docs table stops matching what ingestion produces. OpenMetadata connectors register dialect-specific types into the dialect's `ischema_names` and rely on `ColumnTypeParser`. Snowflake's `VECTOR` handling is the closest precedent.

## Decision

- A single module, `iris/types.py`, holds the IRIS SQL type → OpenMetadata `DataType` table, keyed on `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE`.
- The type of each column comes from its own raw catalog row (`DATA_TYPE`, length, precision, scale), not from the type the dialect reflects. The connector hands the framework a SQLAlchemy type that `ColumnTypeParser` maps to the row's `DataType`, plus the IRIS display string (`system_data_type`); the framework builds the column as for any connector. Registering into the dialect's `ischema_names` was the first idea, but it cannot work here: the dialect turns `VARCHAR(1)` into `CHAR` and sets lengths by class identity, so a registered subclass loses its length, and for a type missing from `ischema_names` the dialect returns `NULLTYPE`, which loses the name the unknown-type warning must show.
- Unknown types map to `UNKNOWN`, with **one warning per type per run** (status warning `IRIS-UNKNOWN-TYPE: IRIS type '<type>' is not mapped; cataloged as UNKNOWN (first seen on <Schema>.<Table>.<Column>)`). They never fail the run.
- Both of these are generated from or asserted against this module:
  - the docs type table (spec 008);
  - the type tests (spec 003).

The table (spec 003, observed on `latest-em`, `latest-cd` and `latest-preview`): the catalog reports 15 values, and every DDL type and synonym collapses onto one of them. `bigint`→`BIGINT`, `bit`→`BOOLEAN`, `date`→`DATE`, `double`→`DOUBLE` (also `FLOAT`, `REAL`), `guid`→`UUID` (`UNIQUEIDENTIFIER`), `integer`→`INT`, `longvarbinary`→`BLOB`, `longvarchar`→`TEXT`, `numeric`→`NUMERIC` with precision and scale (also `DECIMAL`, `MONEY`), `smallint`→`SMALLINT`, `time`→`TIME`, `timestamp`→`TIMESTAMP` (also `DATETIME`, `POSIXTIME`), `tinyint`→`TINYINT`, `varbinary`→`VARBINARY` with length, `varchar`→`VARCHAR` with length (also `CHAR`, VECTOR columns and `%List` projections); anything else → `UNKNOWN`. The generated table is in [specs/003-type-mapping/contracts/type-mapping.md](../../specs/003-type-mapping/contracts/type-mapping.md). Why the raw catalog (GAP-008): the dialect reflects `VARCHAR(1)` as `CHAR`, and OpenMetadata's generic `ColumnTypeParser` maps the dialect's (correct) `LONGVARCHAR` to `VARCHAR` with no length, which the column handler turns into `VARCHAR(1)`.

## Consequences

- Spec 002 consumes the map and does not define types. Spec 004 extends the map's VECTOR entry only through the enrichment hook ([ADR-0007](0007-vector-optional-enrichment.md)).
- Adding a type means one table row and one test. The docs follow automatically.

## Validation

Spec 003:
- every `DATA_TYPE` reported by `INFORMATION_SCHEMA.COLUMNS` on the three release tracks has a row and a test;
- the seed produces zero unknown-type warnings;
- an artificial unknown type produces exactly one warning.
