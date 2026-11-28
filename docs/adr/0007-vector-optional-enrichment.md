# ADR-0007 — VECTOR detail is an optional, capability-detected enrichment

- **Status:** Accepted · **Date:** 2026-11-24 · **Revised:** 2026-11-26 (SPIKE-03, spec 004) · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-7 · **Binds:** FR-11 to FR-14 · **Constitution:** IV, V

## Context

Validated on IRIS 2026.1 (`latest-em`) and 2026.3 (`latest-cd`, `latest-preview`):

- `INFORMATION_SCHEMA.COLUMNS` reports every VECTOR column as `varchar`, with a length that depends on the element type and dimension (`VECTOR(DOUBLE, 3)` → 1037, `VECTOR(INT, 4)` → 83, `VECTOR(FLOAT, 2)` → 691). No catalog column tells it from a string (GAP-001).
- The real type lives in the class dictionary. `%Dictionary.PropertyDefinition` gives `Type = %Library.Vector` and `Parameters = DATATYPE,<type>,LEN,<dim>` for each VECTOR property.
- `GRANT SELECT ON %Dictionary.PropertyDefinition TO <user>` is enough to read it (SPIKE-03). It is the same table the dialect reads for full reflection and Test Connection probes (ADR-0015). `%Dictionary.CompiledProperty`, named here before SPIKE-03, is not needed.
- Without the grant, the read fails with `SQLCODE -99` (privilege violation), which is catchable (GAP-002).
- IRIS DDL accepts five element types: `DOUBLE`, `FLOAT`, `DECIMAL`, `INT` (also `INTEGER`) and `STRING`. Others are refused with `SQLCODE -262`.

OpenMetadata has no VECTOR `DataType`:
- the generic parser maps `VECTOR` to `BINARY`;
- Snowflake registers `VECTOR` in `ischema_names`;
- pgvector gives `dataType = NULL`, and MariaDB 11.8's VECTOR breaks the column read (SPIKE-03).

## Decision

- **Never a prerequisite:** core ingestion never requires `%Dictionary` access (constitution IV).
- **One read per run:** the connector reads every VECTOR property of the Namespace in one query, joining `PropertyDefinition` with `INFORMATION_SCHEMA.TABLES` on `CLASSNAME = parent`, so each property maps to its exact `(schema, table)`. The column is `SqlFieldName` when set (the DDL name is not a valid property name, as for `"vec_low"`), else `Name`. The read runs lazily, on the first table with a `varchar` column, and the result is kept for the run.
- **Access from the preset:** when the ADR-0015 preset found the dictionary unreadable, no query runs.
- **The hint:** without access, or when the query fails, the run gets **one** status warning, keyed on the Database FQN: `IRIS-VECTOR-GRANT: if this Namespace has VECTOR columns, GRANT SELECT ON %Dictionary.PropertyDefinition TO <username> to catalog their element type and dimension`. A failed query appends the first line of its error. The text is conditional, because such a login cannot tell whether the Namespace has VECTOR columns (review decision, 2026-11-26). VECTOR columns are then cataloged as their SQL type (`VARCHAR`).
- **Odd parameters:** unusable `DATATYPE` or `LEN` keeps the column `VARCHAR`, and an unknown element type gives `ARRAY` of `UNKNOWN`. Either way the column gets one `IRIS-VECTOR-PARAMS` warning.
- **Native metadata wins:** if a future IRIS release reports VECTOR in `DATA_TYPE`, the column is cataloged as `ARRAY` from that text and the dictionary is not used for it (FR-13).
- **Representation:**
  - `dataType = ARRAY`;
  - `arrayDataType` = the element type: `DOUBLE`, `FLOAT`, `DECIMAL`, `INT` or `STRING`;
  - `dataTypeDisplay = "VECTOR(<TYPE>, <dim>)"`, for example `VECTOR(DOUBLE, 3)`.

  The connector sets the column's SQLAlchemy type to `ARRAY(<element type>)` and its display. The framework's column handler derives `arrayDataType` from the array's item type, as for any other source.
- **Test Connection:** includes the dictionary check as a **non-mandatory** step (`GetClassDictionary`, probing `SELECT TOP 1 Name FROM %Dictionary.PropertyDefinition`). A failure is reported as an optional hint, not a failed connection.

## Consequences

- Tiers 1 and 2 work with a plain SQL login. Tier 3 needs one read-only grant, which the docs list. The grant shows class and property names of the whole Namespace, not data.
- The enrichment lives in `iris/types.py` (element table, parsing, representation, messages) and `iris/metadata.py` (the per-run read, called from the column hook after spec 003's type map). Its query lives in `iris/queries.py`.
- **Limits:**
  - an inherited VECTOR property is not in `PropertyDefinition`, so its column stays `VARCHAR`; tables created with DDL are not affected;
  - a view's VECTOR columns stay `VARCHAR`, because a view's columns have no dictionary property.
- One query per run with the grant: about 400 ms on the fixtures.
- Spec 004 is the first cut inside the MVP if time runs short. Without it, VECTOR columns are still cataloged, as `VARCHAR`.

## Validation

Spec 004, on all three release tracks, with `AI.Embedding.Vec VECTOR(DOUBLE, 3)`, `Vec4 VECTOR(INT, 4)` and `"vec_low" VECTOR(FLOAT, 2)`:

- **With the grant:** as `omd_reader_dict` and `_SYSTEM`, the three columns are `ARRAY` / `DOUBLE`, `INT`, `FLOAT` / `VECTOR(DOUBLE, 3)`, `VECTOR(INT, 4)`, `VECTOR(FLOAT, 2)`, with no hint.
- **Without it:** as `omd_reader`, they are `VARCHAR(1037)`, `VARCHAR(83)` and `VARCHAR(691)`, and a run over every readable fixture has exactly one hint.
- **UI check:** pending. It needs an OpenMetadata server built from the overlay, which does not fit beside the three IRIS containers on the development workstation. It runs with spec 008's demo, and its result is added here.
