# Gap Report

Limitations of IRIS, its official driver and dialect, or OpenMetadata that the connector works around or
documents (constitution, Principle V; ADR-0013). Every entry has a reproduction against the shared
fixtures. Spec 001 completes the seed entries; each spec appends its own. Ids are never reused, and a
spec takes the next free id (`fixtures/iris/test_gap_report.py` checks the format and the numbering).

Reproductions run in the seeded `USER` Namespace (`python fixtures/iris/seed.py`) on port 1972, with
`sqlalchemy-intersystems-iris` 1.0.2 and `intersystems-irispython` 5.4.1 (`.om/env/bin/python`). Each
one names its login: `omd_reader` has `SELECT` only, `omd_reader_dict` adds the dictionary grants, and
`_SYSTEM` is the administrator. Locally, use the host port of the container (11972 by default).

`IRIS tracks` were checked on 2026-11-25: `latest-em` was 2026.1 (Build 234U); `latest-cd` and
`latest-preview` were the same image, 2026.3 (Build 212U). The matrix in spec 001 reruns the fixture
checks on every pull request; the reproductions are rerun by hand when a tag moves.

### GAP-001 — VECTOR columns reported as `varchar` in `INFORMATION_SCHEMA.COLUMNS`

- **Component:** IRIS SQL catalog
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** SPIKE-01 (seed entry, ADR-0007)
- **Reproduction:** as `omd_reader`

  ```sql
  SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = 'AI' AND TABLE_NAME = 'Embedding' AND COLUMN_NAME = 'Vec'
  ```

- **Expected:** a type that says VECTOR, with its element type and dimension (`VECTOR(DOUBLE, 3)`).
- **Actual:** `varchar`, length 1037, for every login that can read the table.
- **Connector behavior:** enriches the column from the class dictionary when the login can read it
  (ADR-0007, spec 004); otherwise the column is cataloged as `VARCHAR` (GAP-002).
- **User workaround:** `GRANT SELECT ON %Dictionary.CompiledProperty TO <user>` (see GAP-002).
- **Upstream:** not raised yet.

### GAP-002 — VECTOR element type and dimension need `SELECT` on `%Dictionary.CompiledProperty`

- **Component:** class dictionary
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 001-test-harness (seed entry, ADR-0007)
- **Reproduction:** as `omd_reader`, then as `omd_reader_dict`

  ```sql
  SELECT Type, Parameters FROM %Dictionary.CompiledProperty
  WHERE parent = 'AI.Embedding' AND Name = 'Vec'
  ```

- **Expected:** a login that can read `AI.Embedding` can also read its column's VECTOR parameters.
- **Actual:** `omd_reader` gets `[SQLCODE: <-99>:<Privilege violation>]`. `omd_reader_dict` gets
  `%Library.Vector` and parameters that include `DATATYPE,DOUBLE` and `LEN,3`.
- **Connector behavior:** one `IRIS-VECTOR-GRANT` warning per run; the column is cataloged as
  `VARCHAR` (ADR-0007, spec 004).
- **User workaround:** `GRANT SELECT ON %Dictionary.CompiledProperty TO <user>`.
- **Upstream:** not raised yet.

### GAP-003 — Objects invisible to a login cannot be detected by that login

- **Component:** IRIS SQL catalog
- **IRIS tracks:** latest-em not tested; latest-cd not tested; latest-preview not tested
- **Found in spec:** 001-test-harness (seed entry, ADR-0008)
- **Reproduction:** pending SPIKE-03 (spec 005), which also adds the fixture object it needs
  (`Restricted.Secret`).
- **Expected:** the connector can tell the user which objects its login cannot read.
- **Actual:** to be confirmed by SPIKE-03. ADR-0008 assumes that the catalog lists only objects the
  login holds a privilege on, so an object the login cannot see leaves no trace.
- **Connector behavior:** documented limitation (ADR-0008); spec 005 reports what it can detect.
- **User workaround:** run ingestion with a login that has `SELECT` on every schema to catalog.
- **Upstream:** not raised yet.

### GAP-004 — Dialect reads the server version through the Native API

- **Component:** official dialect
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 000-connector-foundation
- **Reproduction:**

  ```python
  from sqlalchemy import create_engine
  create_engine("iris://omd_reader:Reader123@127.0.0.1:1972/USER").connect()
  ```

- **Expected:** a login with `SELECT` only can connect.
- **Actual:** `RuntimeError: <PROTECT> *Resource %Native_ClassExecution required`. The dialect's
  `on_connect` calls `iris.createIRIS(conn).classMethodString("%SYSTEM.Version", "GetNumber")`.
- **Connector behavior:** `preset_dialect_state` in `iris/connection.py` sets
  `dialect.server_version_info` from `SELECT $ZVERSION` before the first pooled connection (ADR-0015).
  Removed when the dialect is fixed.
- **User workaround:** none needed.
- **Upstream:** not raised yet. TODO(upstream): open an issue with the dialect maintainers and link it
  here (constitution: Principle V requires it).

### GAP-005 — Dialect's dictionary-access probe is true for every login

- **Component:** official dialect
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 000-connector-foundation
- **Reproduction:**

  ```python
  from sqlalchemy import create_engine, inspect
  engine = create_engine("iris://omd_reader:Reader123@127.0.0.1:1972/USER")
  engine.dialect.server_version_info = (2026, 1, 0)  # skip GAP-004
  inspect(engine).get_columns("Patient", "Clinic")
  ```

- **Expected:** columns are reflected without the optional dictionary grant, as the dialect's own
  warning text promises.
- **Actual:** `OperationalError ... [SQLCODE: <-99>:<Privilege violation>]`. `_check_dictionary_access`
  treats `cursor.execute("%CHECKPRIV SELECT ON %Dictionary.PropertyDefinition") == 0` as access, but
  the driver returns `0` for every login, so the dialect always joins `%Dictionary.PropertyDefinition`.
- **Connector behavior:** `preset_dialect_state` sets `dialect._dictionary_access` from a real
  `SELECT TOP 1 Name FROM %Dictionary.PropertyDefinition` (ADR-0015). Removed when the dialect is fixed.
- **User workaround:** none needed; `GRANT SELECT ON %Dictionary.PropertyDefinition TO <user>` enables
  full reflection (calculated columns, index details).
- **Upstream:** not raised yet. TODO(upstream): open an issue with the dialect maintainers and link it
  here.

### GAP-006 — Stray `print` in `get_multi_columns` writes one stdout line per reflected column

- **Component:** official dialect
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** SPIKE-01
- **Reproduction:** as `_SYSTEM`, so that GAP-004 and GAP-005 do not interfere

  ```python
  from sqlalchemy import create_engine, inspect
  engine = create_engine("iris://_SYSTEM:SYS@127.0.0.1:1972/USER")
  inspect(engine).get_columns("Patient", "Billing")
  ```

- **Expected:** reflection writes nothing to stdout.
- **Actual:** stdout gets `Code: VARCHAR (20)` and `Balance: DOUBLE (None)`, one line per column, from
  `print(f"{name}: {type_} ({charlen})")` in the dialect's `get_multi_columns`.
- **Connector behavior:** none; reported, not patched (ADR-0015). Ingestion output gets one extra line
  per column.
- **User workaround:** none.
- **Upstream:** not raised yet.

### GAP-007 — Primary key of a class-defined table reflected with its column repeated

- **Component:** official dialect
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** SPIKE-01
- **Reproduction:** as `_SYSTEM`, on a system table that every interoperability-enabled `USER`
  Namespace has (no fixture object is class-defined)

  ```python
  from sqlalchemy import create_engine, inspect
  engine = create_engine("iris://_SYSTEM:SYS@127.0.0.1:1972/USER")
  inspect(engine).get_pk_constraint("LookupTable", "Ens_Util")["constrained_columns"]
  ```

- **Expected:** `['ID']`: `INFORMATION_SCHEMA.KEY_COLUMN_USAGE` has the primary key
  `RowIDField_As_PKey` on `ID` only.
- **Actual:** `['ID', 'ID', 'ID', 'ID', 'ID', 'ID', 'ID', 'ID']`. A primary key declared in DDL,
  composite or not, is reflected correctly, as `_SYSTEM` and as both readers, with or without
  dictionary access.
- **Connector behavior:** none yet; reported, not patched (ADR-0015). The default filters exclude
  `^Ens` (ADR-0009), so the connector does not meet the system tables unless a user includes them.
- **User workaround:** none.
- **Upstream:** not raised yet.

### GAP-008 — `VARCHAR(1)` reflected as `CHAR`; `LONGVARCHAR` cataloged as `VARCHAR(1)`

- **Component:** official dialect
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** SPIKE-01
- **Reproduction:** as `_SYSTEM`, with `.om/env/bin/python`

  ```python
  from sqlalchemy import create_engine, inspect, text
  from metadata.ingestion.source.database.column_type_parser import ColumnTypeParser
  engine = create_engine("iris://_SYSTEM:SYS@127.0.0.1:1972/USER")
  with engine.begin() as conn:
      conn.execute(text("CREATE TABLE Scratch.Gap008 (Flag VARCHAR(1))"))
  print(inspect(engine).get_columns("Gap008", "Scratch")[0]["type"])
  notes = next(c["type"] for c in inspect(engine).get_columns("Encounter", "Clinic") if c["name"] == "Notes")
  print(notes, ColumnTypeParser.get_column_type(notes))
  with engine.begin() as conn:
      conn.execute(text("DROP TABLE Scratch.Gap008"))
  ```

- **Expected:** `VARCHAR(1)` and `LONGVARCHAR` keep their types in the catalog.
- **Actual:** the dialect reflects `VARCHAR(1)` as `CHAR`. It reflects `LONGVARCHAR` correctly, but
  OpenMetadata's generic `ColumnTypeParser` maps `LONGVARCHAR` to `VARCHAR` with no length, so the
  column is cataloged as `VARCHAR(1)` (seen end to end in SPIKE-01). The second half is OpenMetadata's,
  not the dialect's.
- **Connector behavior:** the connector's type map reads the raw `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE`
  (ADR-0006, spec 003), which says `varchar` with length 1 and `longvarchar`.
- **User workaround:** none.
- **Upstream:** not raised yet.

### GAP-009 — A schema without tables is not listed in `INFORMATION_SCHEMA.SCHEMATA`

- **Component:** IRIS SQL catalog
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 001-test-harness
- **Reproduction:** as `_SYSTEM`

  ```sql
  CREATE TABLE Gap009.T (Id INT);
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = 'Gap009';  -- 1
  DROP TABLE Gap009.T;
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = 'Gap009';  -- 0
  ```

- **Expected:** a schema stays listed until it is dropped.
- **Actual:** a schema is listed only while it has a table. `CREATE SCHEMA` alone does not list it,
  and it disappears with its last table.
- **Connector behavior:** none in the connector. The fixtures keep the empty sentinel table
  `Scratch.Keep`, so `Scratch` stays listed while tests create and drop tables there. Input for spec
  002: a schema whose last table is dropped disappears from the catalog.
- **User workaround:** none.
- **Upstream:** not raised yet.
