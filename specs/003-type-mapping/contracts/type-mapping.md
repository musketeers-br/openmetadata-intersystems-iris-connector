# Contract: IRIS → OpenMetadata type mapping

Implements FR-001..FR-006 and FR-014 (ADR-0006). Source of truth: `IRIS_TYPES` in
`overlay/ingestion/src/metadata/ingestion/source/database/iris/types.py`. The table between the
markers is generated; do not edit it by hand. Regenerate it from `.om/ingestion` with:

```bash
../env/bin/python -m metadata.ingestion.source.database.iris.types
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
<!-- END GENERATED -->
