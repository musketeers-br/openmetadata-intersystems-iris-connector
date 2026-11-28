# Data model: VECTOR enrichment

## VECTOR property (one dictionary read per run)

| Field | Source |
|---|---|
| `schema`, `table` | `INFORMATION_SCHEMA.TABLES.TABLE_SCHEMA`, `TABLE_NAME`, joined on `CLASSNAME = PropertyDefinition.parent` |
| `column` | `PropertyDefinition.SqlFieldName` if not `NULL`, else `PropertyDefinition.Name` |
| `parameters` | `PropertyDefinition.Parameters`, raw text (`DATATYPE,DOUBLE,LEN,3`) |

Cache on the source, per run: `{(schema, table, column): parameters}`, or "unavailable" with the
reason when there is no access or the query fails.

## VECTOR facts

Parsed from `parameters`, a comma-separated list of key/value pairs, keys matched case-insensitively.

| Field | Rule |
|---|---|
| `element` | value of `DATATYPE`, upper-cased; required |
| `dimension` | value of `LEN`, a positive integer; required |

Anything missing or unusable → no facts; the column stays as spec 003 cataloged it, plus one
`IRIS-VECTOR-PARAMS`.

## Element types

| `DATATYPE` | OpenMetadata `arrayDataType` | SQLAlchemy element type |
|---|---|---|
| `DOUBLE` | `DOUBLE` | `DOUBLE` |
| `FLOAT` | `FLOAT` | `FLOAT` |
| `DECIMAL` | `DECIMAL` | `DECIMAL` |
| `INT`, `INTEGER` | `INT` | `INTEGER` |
| `STRING` | `STRING` | `String` |
| anything else | `UNKNOWN` (+ one `IRIS-VECTOR-PARAMS`) | the unmapped type of spec 003 |

The cataloged column: `dataType = ARRAY`, `arrayDataType` from the table, and
`dataTypeDisplay = VECTOR(<element>, <dimension>)`, for example `VECTOR(DOUBLE, 3)`.

## Grant hint

One per run, keyed on the Database FQN (`<service>.<Namespace>`), recorded on the first `varchar`
column read when the cache is "unavailable". See [contracts/vector-warnings.md](contracts/vector-warnings.md).

## Fixture catalog v4

`AI.Embedding` (additive):

| Column | DDL | `DATA_TYPE` / length | Row value | With the grant |
|---|---|---|---|---|
| `Vec` (v1) | `VECTOR(DOUBLE, 3)` | `varchar` / 1037 | `TO_VECTOR('0.1,0.2,0.3', DOUBLE)` (v1) | `ARRAY` / `DOUBLE` / `VECTOR(DOUBLE, 3)` |
| `Vec4` | `VECTOR(INT, 4)` | `varchar` / 83 | `TO_VECTOR('1,2,3,4', INT)` | `ARRAY` / `INT` / `VECTOR(INT, 4)` |
| `vec_low` | `"vec_low" VECTOR(FLOAT, 2)` | `varchar` / 691 | `TO_VECTOR('0.5,0.25', FLOAT)` | `ARRAY` / `FLOAT` / `VECTOR(FLOAT, 2)` |

Without the grant, all three are `VARCHAR` with the lengths above.

Version history line: `4: "spec 004: AI.Embedding.Vec4 VECTOR(INT, 4) and AI.Embedding.vec_low VECTOR(FLOAT, 2)"`.
The self-check's columns for `AI.Embedding` gain the two columns (`varchar`). `EXPECTED` gains
`"vectors"`: `{(schema, table, column): (element, dimension)}`, which the integration tests use.
