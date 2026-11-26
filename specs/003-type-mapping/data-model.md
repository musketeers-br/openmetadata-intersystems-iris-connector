# Data model: Type mapping

## Type row (`IRIS_TYPES` in `iris/types.py`)

One per `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE` value (research R1, R4). Keyed on the lower-case
`DATA_TYPE`; lookups lower-case the raw value first.

| Field | Meaning | Rule |
|---|---|---|
| `data_type` | OpenMetadata `DataType` | must exist in the 2.1.1 enumeration |
| `keeps` | `length`, `precision` (precision and scale) or nothing | only `varchar`, `varbinary` keep length; only `numeric` keeps precision and scale |
| `ddl` | IRIS DDL that the catalog reports as this value | examples for the docs, from research R1 |
| `note` | one short sentence for the docs | |

Invariant (unit-tested): for every row, `ColumnTypeParser.get_column_type(sqlalchemy type built for
the row) == data_type.value`.

## Column facts

Per `(TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME)`, from `IRIS_COLUMN_TYPES` (bound on schema and table):
`DATA_TYPE`, `CHARACTER_MAXIMUM_LENGTH`, `NUMERIC_PRECISION`, `NUMERIC_SCALE`. Absent values are
`None`.

## Resolved type

`resolve(facts)` returns:

| Field | Mapped row | Unmapped |
|---|---|---|
| `sqlalchemy_type` | instance that `ColumnTypeParser` maps to the row (`VARCHAR(n)`, `VARBINARY(n)`, `NUMERIC(p,s)`, `TEXT`, `BLOB`, `BOOLEAN`, `UUID`, …) | `IrisUnmappedType`, which the parser maps to `UNKNOWN` |
| `display` | upper-case `DATA_TYPE`, plus `(n)` for length rows and `(p,s)` for precision rows | upper-case raw `DATA_TYPE` |
| `known` | `True` | `False` |

Set on the column dict: `type` ← `sqlalchemy_type`, `system_data_type` ← `display`. Nothing else on the
dict changes.

## Unknown-type record (per `IrisSource` instance = per run)

`UnknownTypes.first(raw_type, where) -> bool`: `True` only the first time a lower-cased `raw_type` is
seen; remembers `where` (`Schema.Table.Column`). One status warning per `True`
([contracts/unknown-type-warning.md](contracts/unknown-type-warning.md)).

## Fixture catalog v2 (`Types.AllTypes`)

| Column | DDL | Expected `DATA_TYPE` | Expected cataloged type |
|---|---|---|---|
| `Id` | `INT PRIMARY KEY` | `integer` | `INT` |
| `BigIntCol` | `BIGINT` | `bigint` | `BIGINT` |
| `BitCol` | `BIT` | `bit` | `BOOLEAN` |
| `DateCol` | `DATE` | `date` | `DATE` |
| `DoubleCol` | `DOUBLE` | `double` | `DOUBLE` |
| `GuidCol` | `UNIQUEIDENTIFIER` | `guid` | `UUID` |
| `LongVarBinaryCol` | `LONGVARBINARY` | `longvarbinary` | `BLOB` |
| `LongVarCharCol` | `LONGVARCHAR` | `longvarchar` | `TEXT` |
| `NumericCol` | `NUMERIC(7,3)` | `numeric` | `NUMERIC` (7, 3) |
| `SmallIntCol` | `SMALLINT` | `smallint` | `SMALLINT` |
| `TimeCol` | `TIME` | `time` | `TIME` |
| `TimestampCol` | `TIMESTAMP` | `timestamp` | `TIMESTAMP` |
| `TinyIntCol` | `TINYINT` | `tinyint` | `TINYINT` |
| `VarBinaryCol` | `VARBINARY(16)` | `varbinary` | `VARBINARY` (16) |
| `VarCharCol` | `VARCHAR(40)` | `varchar` | `VARCHAR` (40) |
| `VarChar1Col` | `VARCHAR(1)` | `varchar` | `VARCHAR` (1), not `CHAR` (GAP-008) |

One row, every column set. Both readers: `GRANT SELECT ON SCHEMA Types`. The self-check verifies the
columns and their `DATA_TYPE` (C2), the primary key (C3), the row (C5) and reader access (C8–C9), like
the other fixture tables. `CATALOG_VERSION` 2, history line "spec 003: Types.AllTypes".
