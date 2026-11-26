# Research: Type mapping

Evidence for [plan.md](plan.md). Sources:

- **Type discovery** on 2026-11-26 against the three tracks, loaded by `fixtures/iris/seed.py`:
  `latest-em` 2026.1 (Build 234U); `latest-cd` and `latest-preview` 2026.3 (Build 212U), the same
  image. Script: `fixtures/iris/discover_types.py` (rerun it when a tag moves).
- **Code reading** of OpenMetadata 2.1.1 (`sql_column_handler.py`, `column_type_parser.py`), of the
  official dialect `sqlalchemy-intersystems-iris` 1.0.2 (`base.py`, `get_multi_columns`) and of spec
  002's `IrisSource`.

No `NEEDS CLARIFICATION` remained in the Technical Context.

## R1 — What `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE` reports

- **Method**: create one table per candidate DDL type in `Scratch` (110 candidates: every DDL type
  and synonym in the IRIS SQL reference, the `%Library` data type classes, VECTOR with five element
  types), read its `DATA_TYPE`, `CHARACTER_MAXIMUM_LENGTH`, `NUMERIC_PRECISION` and `NUMERIC_SCALE`,
  drop it. Then read every column of the whole `USER` Namespace (about 8,500 columns, system
  schemas included) and collect the distinct `DATA_TYPE` values.
- **Result**: identical on all three tracks. The catalog reports **15 values**; every accepted DDL
  type collapses onto one of them.

| `DATA_TYPE` | DDL that reports it (examples) | Length / precision reported | In system tables |
|---|---|---|---|
| `bigint` | `BIGINT`, `SERIAL`, `ROWVERSION`, `%Library.BigInt` | precision 19, scale 0 | yes |
| `bit` | `BIT`, `%Library.Boolean` | — | yes |
| `date` | `DATE`, `%Library.Date`, `%Library.FilemanDate` | — | yes |
| `double` | `DOUBLE`, `DOUBLE PRECISION`, `FLOAT`, `FLOAT(n)`, `REAL`, `%Library.Double` | precision 15 | yes |
| `guid` | `UNIQUEIDENTIFIER`, `%Library.UniqueIdentifier` | — | no |
| `integer` | `INT`, `INTEGER`, `MEDIUMINT`, `%Library.Integer` | precision 10 (7 for `MEDIUMINT`), scale 0 | yes |
| `longvarbinary` | `LONGVARBINARY`, `BLOB`, `IMAGE`, `LONG BINARY`, `LONG RAW`, `%Stream.GlobalBinary` | length 2147483647 | yes |
| `longvarchar` | `LONGVARCHAR`, `LONG VARCHAR`, `LONG`, `TEXT`, `CLOB`, `NTEXT`, `LONGTEXT`, `MEDIUMTEXT`, `%Stream.GlobalCharacter` | length 2147483647 | yes |
| `numeric` | `NUMERIC(p,s)`, `DECIMAL(p,s)`, `DEC(p,s)`, `NUMBER(p,s)`, `MONEY`, `SMALLMONEY`, `%Library.Numeric`, `%Library.Currency` | precision, scale (`NUMERIC` alone: 15, 0; `MONEY`: 15, 4) | yes |
| `smallint` | `SMALLINT`, `%Library.SmallInt` | precision 5, scale 0 | yes |
| `time` | `TIME`, `TIME(p)`, `%Library.Time` | — | yes |
| `timestamp` | `TIMESTAMP`, `TIMESTAMP2`, `DATETIME`, `DATETIME2`, `SMALLDATETIME`, `POSIXTIME`, `%Library.PosixTime`, `%Library.DateTime` | — | yes |
| `tinyint` | `TINYINT`, `%Library.TinyInt` | precision 3, scale 0 | yes |
| `varbinary` | `VARBINARY(n)`, `BINARY(n)`, `BINARY VARYING(n)`, `RAW(n)`, `%Library.Binary` | length (`VARBINARY` alone: 1) | yes |
| `varchar` | `VARCHAR(n)`, `CHAR(n)`, `NCHAR(n)`, `NVARCHAR(n)`, `VARCHAR2(n)`, `SYSNAME`, `%Library.String`, `%Library.List` (32749), `%Library.ListOfDataTypes` (4096), every `VECTOR(...)` | length (`VARCHAR` and `CHAR` alone: 1) | yes |

- **Not accepted** as DDL on these versions: `BOOLEAN`, `JSON` (`SQLCODE -400`, no such class).
- **Not separate values**: `char`, `decimal`, `float`, `real`, `money`, `binary`, `posixtime` (the
  draft in ADR-0006 listed some of them); `guid` was missing from the draft.
- **VECTOR**: always `varchar`, with a length that depends on element type and dimension (`DOUBLE, 3`:
  1037; `INT, 4`: 83; `STRING, 2`: 3641144).
- **`%List` projections**: `varchar` with length 32749 (`%Library.List`) or 4096
  (`%Library.ListOfDataTypes`). The SQL catalog does not say that they are lists, so they cannot be
  told apart from character columns without reading the class dictionary.

## R2 — The map reads the raw catalog, not the dialect's reflected type

- **Decision**: resolve every column from the `INFORMATION_SCHEMA.COLUMNS` row of the same
  `(schema, table, column)`, read with one bound query per table (`IRIS_COLUMN_TYPES` in
  `queries.py`). The dialect's reflected type is replaced.
- **Rationale**:
  - `get_multi_columns` maps by class identity: `coltype is VARCHAR and charlen == 1` turns
    `VARCHAR(1)` into the bare `CHAR` class (GAP-008).
  - For a type missing from its `ischema_names`, the dialect returns `NULLTYPE` and the raw name is
    lost, so the unknown-type warning (FR-008) could not name the type.
  - OpenMetadata's generic `ColumnTypeParser` maps the dialect's `LONGVARCHAR` to `VARCHAR`, and the
    column handler then defaults the length to 1: that is where `VARCHAR(1)` for `LONGVARCHAR` comes
    from (GAP-008, second half).
  - Registering into the dialect's `ischema_names` (the ADR-0006 wording) cannot fix the first two
    points: the `CHAR` rule and the length keyword use `is` and `in (VARCHAR, ...)` on classes, so a
    subclass would lose the length, and an unknown type would still lose its name.
- **Alternatives**: patching the dialect's `ischema_names` per engine — rejected, above; overriding
  the dialect's reflection — forbidden (constitution V, ADR-0015).

## R3 — How the mapped type reaches the OpenMetadata column

- **Facts** (OpenMetadata 2.1.1, `SqlColumnHandlerMixin.get_columns_and_constraints`):
  - `dataType` is `ColumnTypeParser.get_column_type(column["type"])`, which looks the SQLAlchemy type
    object up by class, then by `str(type)`, then by the name before `(`, and falls back to `UNKNOWN`;
  - `dataLength` comes from `column["type"].length` for `CHAR`, `VARCHAR`, `BINARY`, `VARBINARY`,
    otherwise 1;
  - `precision` and `scale` come from the `(p,s)` in `str(column["type"])` for numeric types;
  - `dataTypeDisplay` is `column["system_data_type"]` when present.
- **Decision**: for each column, set `column["type"]` to a SQLAlchemy type instance that
  `ColumnTypeParser` maps to the row's OpenMetadata type (`VARCHAR(n)`, `VARBINARY(n)`,
  `NUMERIC(p,s)`, `TEXT`, `BLOB`, `BOOLEAN`, `UUID`, …) and `column["system_data_type"]` to the IRIS
  display (`VARCHAR(120)`, `NUMERIC(5,2)`, `LONGVARCHAR`). The framework then builds the column as for
  any connector (constitution I).
- **Guard**: a unit test asserts, for every row, that `ColumnTypeParser.get_column_type` of the row's
  SQLAlchemy type equals the row's `DataType`, so the indirection cannot drift.
- **Unknown types**: `NullType()` maps to `NULL`, not `UNKNOWN`. Unmapped types get a small
  `TypeEngine` whose name matches nothing in `ColumnTypeParser`, so the framework's own fallback gives
  `UNKNOWN`; `system_data_type` keeps the raw IRIS name.
- **Checked** on OpenMetadata 2.1.1: `VARCHAR(10)`→`VARCHAR`, `NUMERIC(7,3)`→`NUMERIC` (7, 3),
  `TEXT()`→`TEXT`, `BLOB()`→`BLOB`, `BOOLEAN()`→`BOOLEAN`, `UUID()`→`UUID`, `VARBINARY(8)`→`VARBINARY`,
  `BIGINT`, `INTEGER`→`INT`, `SMALLINT`, `TINYINT`, `DATE`, `TIME`, `TIMESTAMP`, `DOUBLE`. All targets
  exist in the 2.1.1 `DataType` enumeration.

## R4 — The table

| `DATA_TYPE` | OpenMetadata `DataType` | Kept | Display |
|---|---|---|---|
| `bigint` | `BIGINT` | — | `BIGINT` |
| `bit` | `BOOLEAN` | — | `BIT` |
| `date` | `DATE` | — | `DATE` |
| `double` | `DOUBLE` | — | `DOUBLE` |
| `guid` | `UUID` | — | `GUID` |
| `integer` | `INT` | — | `INTEGER` |
| `longvarbinary` | `BLOB` | — | `LONGVARBINARY` |
| `longvarchar` | `TEXT` | — | `LONGVARCHAR` |
| `numeric` | `NUMERIC` | precision, scale | `NUMERIC(p,s)` |
| `smallint` | `SMALLINT` | — | `SMALLINT` |
| `time` | `TIME` | — | `TIME` |
| `timestamp` | `TIMESTAMP` | — | `TIMESTAMP` |
| `tinyint` | `TINYINT` | — | `TINYINT` |
| `varbinary` | `VARBINARY` | length | `VARBINARY(n)` |
| `varchar` | `VARCHAR` | length | `VARCHAR(n)` |

- **Rationale**: one row per reported value (FR-002). `bit`, `longvarchar`, `longvarbinary` follow the
  decisions in the spec's clarifications. `numeric` keeps `NUMERIC`, because `DECIMAL` is reported as
  `numeric` too. Integer precisions (10, 19, …) and the double's 15 are implied by the type and are not
  kept. Stream lengths (2147483647) are not kept: `TEXT` and `BLOB` carry no length.
- **`%List`**: cataloged as `VARCHAR(32749)` like any `varchar` (R1); telling lists apart needs the
  class dictionary, which is out of scope (spec 004 reads it for VECTOR only). The spec's FR-003 is
  read this way: the element type is not knowable from the catalog, and the catalog does not even
  mark the column as a list, so no row can say `ARRAY`.

## R5 — Unknown types: once per type per run

- **Decision**: `IrisSource` keeps a per-instance record of unmapped types already reported (one
  instance per ingestion run). The first time a type is met, one status warning is added:
  key = Database FQN (`<service>.<Namespace>`), message from ADR-0006. Later columns with the same
  type add nothing.
- **Rationale**: same pattern as spec 002's `IRIS-ACCESS` de-duplication; the status object is the
  one the UI shows.
- **Note**: today no reported type is unmapped (R1), so the path is proven by a unit test that drops a
  row and by an integration test that removes a row from the table at runtime.

## R6 — Where the mapping is applied

- **Decision**: spec 002's `IrisSource._get_columns_internal` reads a table's columns (tables and
  views) and merges descriptions. Spec 003 adds one call at its end,
  `self.map_column_types(schema_name, table_name, columns)`, defined in a new section
  `# --- 003: type map ---` of `metadata.py`. All type logic is in `types.py`; the SQL is in
  `queries.py`.
- **Failure**: the type query runs inside 002's `report_access_gap(..., "columns", ...)`, so an
  unreadable catalog row is the same `IRIS-ACCESS` warning the column read gives (de-duplicated), and
  the columns keep the dialect's types.
- **Coordination**: this is the "single call site" in 002's method that the type-map plan anticipated.
  Until 002 merges, 003 is built on a local copy of 002 applied on 001.

## R7 — Fixture `Types.AllTypes`

- **Decision**: catalog v2 adds schema `Types` and table `Types.AllTypes`: `Id INT PRIMARY KEY` and one
  column per reported value except `integer` (covered by `Id`), with parameters that show what is
  kept, plus `VARCHAR(1)` for GAP-008. One row with a value in every column. Both readers get
  `SELECT ON SCHEMA Types`. The self-check verifies columns, `DATA_TYPE`, the row and reader access.
- **Rationale**: FR-010; one column per family is enough because every synonym reports the same
  value (R1). The VECTOR column already exists (`AI.Embedding.Vec`).

## R8 — Docs table

- **Decision**: `render_markdown_table()` in `types.py` returns the Markdown table (IRIS `DATA_TYPE`,
  OpenMetadata type, kept, example DDL, note). `contracts/type-mapping.md` holds the rendered table
  between markers; a unit test compares it with a fresh rendering and prints the
  command that regenerates it. No `__main__` in `types.py`: section 004 may add code after section 003.

## Implementation measurements

2026-11-26, WSL2, containers loaded with catalog v2 (`FIXTURES OK v2` twice on each track, 49 checks):

- `discover_types.py --check`: 15 `DATA_TYPE` values, all mapped, on `latest-em`, `latest-cd`,
  `latest-preview`.
- Unit tests: `test_iris_types.py` 41 passed; with spec 002's `test_iris.py`, 95 passed.
- Integration tests on every local cell (3 tracks × 3 logins): `test_types.py` 5 passed, with specs
  001 and 002 (Part A) 27 passed for `admin` and `reader_dict`, 28 for `reader` (Part B and
  `test_workflow.py` skip without an OpenMetadata server).
- `pytest fixtures`: 54 tests, 52 passed. The two failures come from spec 002's content on this base,
  not from 003: GAP-010..013 are not in the format `test_gap_report.py` checks, and
  `test_metadata_core.py` creates and drops `Scratch.Keep`. Spec 002 fixes both when it rebases on 001.
- `make om-check` twice: no diff.
- Spec 002's unit-test stubs answer every query with their description rows, so the new type query
  in `_get_columns_internal` reads those rows too; the tests still pass. A stub that answers per
  statement would make them exact (for spec 002's owner).
