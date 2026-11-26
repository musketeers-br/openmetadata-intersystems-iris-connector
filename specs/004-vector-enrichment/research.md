# Research: VECTOR enrichment

Evidence for [plan.md](plan.md). Sources:

- **SPIKE-03** (VECTOR and least privilege, 2026-11-26, the three tracks), run in the planning
  repository before this spec; results and decisions copied in R1, the experiment not redone.
- **Probes of 2026-11-26** for this plan, on `latest-em` 2026.1 (Build 234U), `latest-cd` and
  `latest-preview` 2026.3 (Build 212U), as `_SYSTEM`, `omd_reader_dict` and `omd_reader`, with
  temporary tables (R2, R3).
- **Code reading** of the connector as of spec 005 (`connection.py` preset, `metadata.py` column
  hook) and of OpenMetadata 2.1.1's column handler (R4).

No `NEEDS CLARIFICATION` remained in the Technical Context.

## R1 — What SPIKE-03 settled

- `INFORMATION_SCHEMA.COLUMNS` reports every VECTOR as `varchar`, with a length that depends on the
  element type and dimension (`VECTOR(DOUBLE, 3)` → 1037, `VECTOR(INT, 4)` → 83, `VECTOR(FLOAT, 2)` →
  691). No column tells it from a string, on any track (GAP-001).
- `%Dictionary.PropertyDefinition` gives `Type = %Library.Vector` and
  `Parameters = DATATYPE,<type>,LEN,<dim>`; `GRANT SELECT ON %Dictionary.PropertyDefinition` is
  enough. Without it: `SQLCODE -99`, catchable.
- `PropertyDefinition` is also what the dialect joins for reflection and what Test Connection probes
  (ADR-0015, spec 000).
- `PropertyDefinition` holds only properties a class defines. An inherited VECTOR property would
  need `CompiledProperty`. DDL tables define every column themselves.
- Representation, checked through the OpenMetadata 2.1.1 framework: a column dict with
  `type = sqlalchemy.ARRAY(<element type>)` and `system_data_type = "VECTOR(DOUBLE, 3)"` is cataloged
  as `ARRAY` / `DOUBLE` / `VECTOR(DOUBLE, 3)`, and likewise for `INT`, `DECIMAL`, `FLOAT`, `STRING`.
  pgvector gives `dataType = NULL`; MariaDB 11.8's VECTOR breaks the column read.

**Decisions (both developers, 2026-11-26)**: one optional grant, `%Dictionary.PropertyDefinition`;
representation `ARRAY` + `arrayDataType` + `VECTOR(<TYPE>, <dim>)`; spec 004 implements both and
checks the UI.

## R2 — From a dictionary property to a SQL column, in one query

| Question | Finding (identical on the tracks probed) |
|---|---|
| Class of a table | `INFORMATION_SCHEMA.TABLES.CLASSNAME`, readable by any login that sees the table: `AI.Embedding` → `AI.Embedding`, `Sql_Name.Odd_Vec` → `Sql.Name.OddVec` (the class name is not the SQL name) |
| Column of a property | `SqlFieldName` when the DDL name is not a valid property name (`"vec_low"` → property `veclow`, `SqlFieldName = vec_low`), else `NULL` and the column is `Name` |
| All VECTORs at once | `WHERE Type = '%Library.Vector'` on `PropertyDefinition` |
| One query | `SELECT t.TABLE_SCHEMA, t.TABLE_NAME, p.SqlFieldName, p.Name, p.Parameters FROM %Dictionary.PropertyDefinition p JOIN INFORMATION_SCHEMA.TABLES t ON t.CLASSNAME = p.parent WHERE p.Type = '%Library.Vector'` works as `omd_reader_dict` and `_SYSTEM`; 120–620 ms on the fixtures, run once |
| Without the grant | the same query: `SQLCODE -99` |
| Tables the login cannot see | left out by the join (`INFORMATION_SCHEMA.TABLES` shows only visible tables) |

**Decision**: one query per run (`IRIS_VECTOR_COLUMNS` in `queries.py`), read lazily on the first
table whose columns are read, cached on the source as `{(schema, table, column): parameters}`.
- **Rationale**: one round trip whatever the number of tables; exact identity from the join
  (Principle III).
- **Alternatives considered**:
  - one query per table: N round trips, and every table must be asked, because a VECTOR cannot be
    told from a `varchar`;
  - matching `parent` to `schema.table` by text: wrong for names with `_` and other characters.

## R3 — Element types

DDL accepts exactly `DOUBLE`, `FLOAT`, `DECIMAL`, `INT` (also spelled `INTEGER`) and `STRING`.
`TIME`, `TIMESTAMP`, `BIGINT`, `SMALLINT` and `TINYINT` are refused with `SQLCODE -262` ("Invalid
VECTOR field definition") on 2026.1 and 2026.3.

**Decision**: element table `DOUBLE`→`DOUBLE`, `FLOAT`→`FLOAT`, `DECIMAL`→`DECIMAL`, `INT` and
`INTEGER`→`INT`, `STRING`→`STRING`. Any other value (only a hand-written class or a later release can
produce one) → `UNKNOWN` plus one `IRIS-VECTOR-PARAMS` warning.

## R4 — Where the enrichment runs

- Access is known before any table is read: the ADR-0015 preset sets `engine.dialect._dictionary_access`
  from a real read of `%Dictionary.PropertyDefinition`, once per engine.
- **Decision**:
  - When `_dictionary_access is False`, the connector records the hint on the first column read and
    runs no query.
  - When it is `True`, it runs the query once. A database error from it (any `SQLAlchemyError`) gives
    the hint with the first line of the error, and enrichment is off for the run.
  - The hint is a `status.warning` keyed on the Database FQN, so spec 005's guard test accepts the
    handler.
  - The enrichment is a separate method in `metadata.py` section `--- 004 ---`, called in
    `_get_columns_internal` after spec 003's `map_column_types`. It changes only the columns the
    cache names: it sets `type` to `sqlalchemy.ARRAY(<element SQLAlchemy type>)` and
    `system_data_type` to the display.
  - `arrayDataType` comes from the framework's column handler. It reads the element type of an
    `ARRAY` (`ColumnTypeParser` on `item_type`), which is how SPIKE-03's check produced
    `arrayDataType`.
- **Native metadata (FR-009)**: spec 003's map reads the raw `DATA_TYPE`. If a release reports a
  `DATA_TYPE` that names VECTOR, section 004 of `types.py` resolves it before spec 003's table
  lookup:
  - `ARRAY`, with element type and dimension parsed from the catalog text when present, else
    `UNKNOWN`;
  - the display is the catalog's text;
  - no `IRIS-UNKNOWN-TYPE` warning.

  The enrichment skips columns that are already `ARRAY`, and the hint is recorded only when a column
  needed the dictionary. No IRIS release does this yet, so unit tests with a mocked catalog row cover
  it. Spec 003's table keeps its 15 rows.

## R5 — UI check

The UI shows a column's `dataTypeDisplay` in the schema tab; whether an `ARRAY` column with
`arrayDataType` renders well needs an OpenMetadata server built from the overlay (`make om-image`).
This workstation's WSL has 7 GB, which is not enough to run the server stack beside three IRIS
containers (SPIKE-04 was deferred for the same reason). **Decision**: the ingestion-level evidence
(R1) is the acceptance on the matrix. The UI check is a task that runs once a server is available,
either here with the IRIS containers stopped, or with spec 008's demo. Its result goes into ADR-0007.
