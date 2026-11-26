# Data model: Least privilege and access-gap reporting

## Access gap

One failed read of one object's feature in one run.

| Field | Value |
|---|---|
| `fqn` | the object's FQN: table or view `<service>.<Namespace>.<Schema>.<Table>`, schema `<service>.<Namespace>.<Schema>` |
| `feature` | one of the features below |
| `schema`, `name` | the exact IRIS names, used in the message (`<Schema>.<Name>`; a schema gap uses the schema alone) |
| `reason` | the first line of the database error (`str(exc.orig)`), or the exception class name if empty |

Status entry: `self.status.warning(fqn, "IRIS-ACCESS: cannot read <feature> of <Schema>.<Name>: <reason>")`.
De-duplication: one entry per `(fqn, feature)` per run (the set `_access_gaps_reported` on the
source). The helper catches `SQLAlchemyError` only; any other exception is a bug and stops the run.

## Features

| Feature | Object | Read | Wrapped in | Spec |
|---|---|---|---|---|
| `tables` | schema | `inspector.get_table_names(schema)` | `query_table_names_and_types` | 005 |
| `views` | schema | `inspector.get_view_names(schema)` | `query_view_names_and_types` | 005 |
| `columns` | table, view | `inspector.get_columns`; `IRIS_COLUMN_TYPES` | `_get_columns_internal`, `map_column_types` | 002, 003 |
| `keys` | table | PK, `IRIS_UNIQUE_CONSTRAINTS`, FKs (three reads, one feature) | `_get_columns_with_constraints` | 002 |
| `description` | table, view | `inspector.get_table_comment` | `get_table_description` | 002 |
| `view definition` | view | `inspector.get_view_definition` | `get_schema_definition` | 002 |
| `data` | table, view | `IRIS_READ_PROBE` (`SELECT TOP 0 *`) | `check_readable` | 005 |
| `sample data`, `profile` | table | profiler reads | the profiler's IRIS hooks | 006 |

## Restricted fixtures (catalog v3)

Schema `Restricted`. The readers have no schema-level grant on it.

| Object | DDL | Reader privilege | Reader sees | Reader reads |
|---|---|---|---|---|
| `Restricted.Secret` | `Id INT PRIMARY KEY, Code VARCHAR(10) NOT NULL, Note VARCHAR(50)` | `GRANT REFERENCES ON Restricted.Secret` | listed, 3 columns | refused (-99) |
| `Restricted.ColumnGrant` | `Id INT PRIMARY KEY, Hidden VARCHAR(10)` | `GRANT SELECT (Id) ON Restricted.ColumnGrant` | listed, column `Id` only | `SELECT Id` ok; `SELECT *` refused (-99) |
| `Restricted.Hidden` | `Id INT PRIMARY KEY` | none | not listed | refused (-99) |

One row in each (`Id = 1`). The administrator sees and reads all three.

Self-check additions:
- C1–C3 and C5 for the three tables, as the administrator.
- C11 per reader:
  - the tables listed in `Restricted` are `["ColumnGrant", "Secret"]`;
  - `SELECT TOP 1 * FROM` each of the three is refused with -99;
  - `SELECT TOP 1 Id FROM Restricted.ColumnGrant` reads.

`EXPECTED` gains:
- the objects, columns, constraints and rows above;
- `"restricted"`: `{table: (listed, columns_seen)}` per reader, used by the self-check and the
  integration tests.

`READER_SCHEMAS` is unchanged, and the readers' reads of `Restricted` go in their own check. Tests
that iterate `EXPECTED["columns"]` to read as any login keep to `READER_SCHEMAS`.

Version history line: `3: "spec 005: Restricted.Secret (REFERENCES), Restricted.ColumnGrant (one-column SELECT), Restricted.Hidden (no grant)"`.

## Expected warnings per cell

| Login | `Restricted.Secret` | `Restricted.ColumnGrant` | `Restricted.Hidden` | readable fixtures |
|---|---|---|---|---|
| `admin` | none | none | none (cataloged) | none |
| `reader` | 1 × `data` | 1 × `data` | not listed, none | none |
| `reader_dict` | 1 × `data` | 1 × `data` | not listed, none | none |

## Guard allow list

Each entry is `(file, enclosing function) → reason`. Every other `except` handler in `iris/` must
re-raise or call `status.warning`.

| File | Function | Reason |
|---|---|---|
| `connection.py` | the ADR-0015 preset function | Decides `_dictionary_access` for the dialect; no object is read, and the optional Test Connection step reports the missing grant |
