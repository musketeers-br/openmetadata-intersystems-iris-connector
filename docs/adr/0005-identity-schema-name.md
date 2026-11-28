# ADR-0005 — Metadata identity is always (schema, name)

- **Status:** Accepted; the inspector vs direct-query split is settled in spec 002 (SPIKE-02) · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-5 · **Binds:** FR-5 to FR-9 · **Constitution:** III

## Context

IRIS allows the same table name in several schemas. The fixture has `Clinic.Patient` and `Billing.Patient`. A catalog query or an in-memory map keyed on `TABLE_NAME` alone merges them: columns, keys and descriptions of one table leak into the other. Earlier IRIS integrations have shipped exactly this bug, so it is a named regression case in the fixtures.

IRIS also keeps mixed-case names (`Clinic.Patient`, `PatientId`). Upper- or lower-casing them breaks FQN matching with dbt and with what users see in IRIS.

## Decision

- Every catalog query and every in-memory map is keyed on `(TABLE_SCHEMA, TABLE_NAME)`, plus `COLUMN_NAME` for columns.
- Joins between `INFORMATION_SCHEMA` views always join on schema **and** name.
- Names are never case-normalized.
- The SQLAlchemy inspector of the official dialect is the default source. Direct `INFORMATION_SCHEMA` or `%Dictionary` SQL lives only in `iris/queries.py`, as named constants with bind parameters.

## Consequences

- Any helper that returns `dict[str, …]` keyed by table name is a review blocker.
- Where the inspector is wrong or incomplete for IRIS (keys, view definitions, descriptions), the fix is a documented direct query in `queries.py` plus a Gap Report entry ([ADR-0013](0013-gap-report.md)). It is never a post-processing patch.

## Outcome (spec 002)

Compared on `latest-em` as `admin`, `omd_reader` and `omd_reader_dict`; the table is in `specs/002-metadata-core/research.md`. The other tracks are checked by the matrix (spec 001).

- **Inspector:** schemas, tables, views, columns (name, nullability, length, precision, scale, description), primary keys, foreign keys (with the referenced schema), table descriptions and view definitions.
- **Direct query in `queries.py`:** unique constraints only (`IRIS_UNIQUE_CONSTRAINTS`, GAP-010), keyed on `(schema, name)`.

## Validation

Fixture regression tests, run on every matrix cell:
- `Clinic.Patient` and `Billing.Patient` are distinct assets with their own columns and keys;
- mixed-case names round-trip unchanged.
