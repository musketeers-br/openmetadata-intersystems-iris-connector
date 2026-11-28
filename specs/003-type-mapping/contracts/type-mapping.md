# Contract: IRIS → OpenMetadata type mapping

Implements FR-001..FR-006 and FR-014 (ADR-0006). Source of truth: `IRIS_TYPES` in
`overlay/ingestion/src/metadata/ingestion/source/database/iris/types.py`. The table between the
markers is generated; do not edit it by hand. Regenerate it from `.om/ingestion` with:

```bash
../env/bin/python -c 'from metadata.ingestion.source.database.iris.types import render_markdown_table; print(render_markdown_table())'
```

`test_iris_types.py` fails when the committed table differs from a fresh rendering.

## Rules

- The key is `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE`, matched case-insensitively. The IRIS SQL catalog
  reports these 15 values on `latest-em`, `latest-cd` and `latest-preview` (research R1); every DDL
  type and synonym collapses onto one of them.
- The type is resolved from the catalog row of the same `(schema, table, column)`, not from the
  dialect's reflected type (GAP-008).
- `dataTypeDisplay` is the upper-case `DATA_TYPE`, with `(n)` when the length is kept and `(p,s)` when
  precision and scale are kept.
- VECTOR columns are reported as `varchar` and cataloged as `VARCHAR` here; spec 004 enriches them.
- Any other value: `UNKNOWN` plus one warning per type per run
  ([unknown-type-warning.md](unknown-type-warning.md)).

## Table

<!-- BEGIN GENERATED: render_markdown_table() -->
| IRIS `DATA_TYPE` | OpenMetadata type | Kept | IRIS DDL reported as it | Note |
|---|---|---|---|---|
| `bigint` | `BIGINT` | — | BIGINT, SERIAL, ROWVERSION |  |
| `bit` | `BOOLEAN` | — | BIT, %Library.Boolean | IRIS has no BOOLEAN DDL type |
| `date` | `DATE` | — | DATE |  |
| `double` | `DOUBLE` | — | DOUBLE, DOUBLE PRECISION, FLOAT, REAL |  |
| `guid` | `UUID` | — | UNIQUEIDENTIFIER |  |
| `integer` | `INT` | — | INT, INTEGER, MEDIUMINT |  |
| `longvarbinary` | `BLOB` | — | LONGVARBINARY, BLOB, IMAGE, LONG RAW | binary stream |
| `longvarchar` | `TEXT` | — | LONGVARCHAR, TEXT, CLOB, LONG VARCHAR | character stream |
| `numeric` | `NUMERIC` | precision, scale | NUMERIC(p,s), DECIMAL(p,s), NUMBER, MONEY |  |
| `smallint` | `SMALLINT` | — | SMALLINT |  |
| `time` | `TIME` | — | TIME |  |
| `timestamp` | `TIMESTAMP` | — | TIMESTAMP, DATETIME, SMALLDATETIME, POSIXTIME |  |
| `tinyint` | `TINYINT` | — | TINYINT |  |
| `varbinary` | `VARBINARY` | length | VARBINARY(n), BINARY(n), RAW(n) |  |
| `varchar` | `VARCHAR` | length | VARCHAR(n), CHAR(n), NVARCHAR(n), %Library.String | also VECTOR columns (enriched by spec 004) and %List projections |
<!-- END GENERATED -->
