# ADR-0007 — VECTOR detail is an optional, capability-detected enrichment

- **Status:** Accepted; the OpenMetadata representation is settled in spec 004 (SPIKE-03) · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-7 · **Binds:** FR-11 to FR-14 · **Constitution:** IV, V

## Context

Validated on IRIS 2026.1 (`latest-em`) on 2026-11-10:

- `INFORMATION_SCHEMA.COLUMNS` reports a `VECTOR(DOUBLE, 3)` column as `varchar`.
- The real type lives in the class dictionary:
  `SELECT Name, Type, Parameters FROM %Dictionary.CompiledProperty WHERE parent = ? AND Name = ?` returns `Type = %Library.Vector` and `Parameters` containing `DATATYPE,DOUBLE` and `LEN,3`.
- `GRANT SELECT ON %Dictionary.CompiledProperty TO <user>` is enough to read it.
- Without the grant, the query fails with `SQLCODE -99` (privilege violation), which is catchable.

OpenMetadata has no VECTOR `DataType`:
- the generic parser maps `VECTOR` to `BINARY`;
- Snowflake registers `VECTOR` in `ischema_names`;
- pgvector and MariaDB 11.8 report `vector(3)` natively.

## Decision

- **Never a prerequisite:** core ingestion never requires `%Dictionary` access (constitution IV).
- **One probe per run:** on the first VECTOR need in a run, the connector probes `%Dictionary.CompiledProperty` once and caches the result for the run.
  - **On `SQLCODE -99`:** log **one** warning naming `GRANT SELECT ON %Dictionary.CompiledProperty TO <user>` ([warnings contract](https://github.com/musketeers-br/is-omd/blob/main/docs/contracts/warnings.md)). VECTOR columns are then cataloged as their SQL type (`VARCHAR`).
  - **With access:** columns whose `Type` is `%Library.Vector` are enriched from `Parameters` (`DATATYPE`, `LEN`).
- **Native metadata wins:** if a future IRIS release reports VECTOR in SQL metadata, that source is used and the dictionary probe is skipped (FR-13).
- **Representation (default, unless SPIKE-03 shows OpenMetadata renders it badly):**
  - `dataType = ARRAY`
  - `arrayDataType = <element type mapped by ADR-0006>`
  - `dataTypeDisplay = "VECTOR(<TYPE>, <dim>)"`, for example `VECTOR(DOUBLE, 3)`
  - **Fallback:** `dataType = BINARY` with the same `dataTypeDisplay`, as Snowflake does.

  The choice and the evidence are recorded in spec 004's `research.md`, and this ADR is updated.
- **Test Connection:** includes the dictionary check as a **non-mandatory** step ([test-connection contract](https://github.com/musketeers-br/is-omd/blob/main/docs/contracts/test-connection.md)).

## Consequences

- Tiers 1 and 2 work with a plain SQL login. Tier 3 needs one read-only grant, which the docs list.
- The enrichment lives in `iris/types.py`, and its query lives in `iris/queries.py`. The rest of the connector only sees the result of the map.
- Spec 004 is the first cut inside the MVP if time runs short. Without it, VECTOR columns are still cataloged, as `VARCHAR`.

## Validation

Spec 004, on all three release tracks:
- `AI.Embedding.Vec` shows `VECTOR(DOUBLE, 3)` as `omd_reader_dict`;
- it shows `VARCHAR` plus exactly one hint as `omd_reader`.

Whether a narrower grant than the whole `CompiledProperty` table exists is also checked there.
