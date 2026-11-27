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

`Upstream` is an issue link, "not raised yet", or "not applicable" for a limitation the connector
handles itself with nothing to report. An issue is opened only after both developers agree.

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
  The same holds for `Vec4 VECTOR(INT, 4)` (length 83) and `"vec_low" VECTOR(FLOAT, 2)` (length 691),
  checked on 2026-11-26 on the three tracks.
- **Connector behavior:** with `SELECT` on `%Dictionary.PropertyDefinition`, the column is cataloged as
  `ARRAY` of its element type, shown as `VECTOR(DOUBLE, 3)` (ADR-0007, spec 004). Otherwise it is
  cataloged as `VARCHAR` (GAP-002).
- **User workaround:** `GRANT SELECT ON %Dictionary.PropertyDefinition TO <user>` (see GAP-002).
- **Upstream:** not raised yet.

### GAP-002 — VECTOR element type and dimension need `SELECT` on `%Dictionary.PropertyDefinition`

- **Component:** class dictionary
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced (2026-11-26)
- **Found in spec:** 001-test-harness (seed entry, ADR-0007); grant settled by SPIKE-03
- **Reproduction:** as `omd_reader`, then as `omd_reader_dict`

  ```sql
  SELECT Type, Parameters FROM %Dictionary.PropertyDefinition
  WHERE parent = 'AI.Embedding' AND Name = 'Vec'
  ```

- **Expected:** a login that can read `AI.Embedding` can also read its column's VECTOR parameters.
- **Actual:** `omd_reader` gets `[SQLCODE: <-99>:<Privilege violation>]`. `omd_reader_dict` gets
  `%Library.Vector` and `DATATYPE,DOUBLE,LEN,3`. `%Dictionary.CompiledProperty`, named here before
  SPIKE-03, gives the same and is not needed.
- **Connector behavior:** without the grant, no dictionary query runs (the ADR-0015 preset already
  knows), the column is cataloged as `VARCHAR`, and the run gets one `IRIS-VECTOR-GRANT` warning
  naming the grant (ADR-0007, spec 004).
- **User workaround:** `GRANT SELECT ON %Dictionary.PropertyDefinition TO <user>`. It also gives the
  dialect its full reflection (GAP-005).
- **Upstream:** not raised yet.

### GAP-003 — Objects invisible to a login cannot be detected by that login

- **Component:** IRIS SQL catalog
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced (2026-11-26)
- **Found in spec:** 001-test-harness (seed entry, ADR-0008); confirmed by SPIKE-03 and spec 005
- **Reproduction:** as `omd_reader`. Schema `Restricted` holds `Secret` (granted `REFERENCES`),
  `ColumnGrant` (granted `SELECT (Id)`) and `Hidden` (no grant).

  ```sql
  SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'Restricted'
  ```

- **Expected:** the connector can tell the user which objects its login cannot read.
- **Actual:**
  - The query lists `ColumnGrant` and `Secret`, never `Hidden`: IRIS lists a table only to a login
    that holds some privilege on it.
  - `INFORMATION_SCHEMA.TABLE_PRIVILEGES` and `COLUMN_PRIVILEGES` do not exist (`SQLCODE -30`).
  - Only `SELECT` on `%Dictionary.CompiledClass`, a further dictionary grant, would list the missing
    tables, by comparing its SQL names with `INFORMATION_SCHEMA.TABLES`.
  - `SELECT TOP 1 * FROM Restricted.Hidden` answers `SQLCODE -99`, not -30, so a login that already
    knows a name can tell the table exists.
- **Connector behavior:** invisible objects stay a documented limitation (ADR-0008); the connector
  does not guess names. A visible object the login cannot read (`REFERENCES`, `INSERT` or `UPDATE`
  only, or a column-level `SELECT`) is cataloged with what the catalog shows, plus one
  `IRIS-ACCESS: cannot read data of <Schema>.<Table>: …` warning (spec 005).
- **User workaround:** run ingestion with a login that has `SELECT` on every schema to catalog. To
  find what a login misses, compare the query above, run as an administrator, with the catalog.
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

### GAP-010 — Unique-constraint reflection needs `%Dictionary.IndexDefinition` when dictionary access is on

- **Component:** official dialect
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 002-metadata-core
- **Reproduction:** as `omd_reader_dict` (SELECT on the schemas, plus `%Dictionary.PropertyDefinition`;
  until fixture catalog v3 also `%Dictionary.CompiledProperty`), with `.om/env/bin/python`

  ```python
  from sqlalchemy import create_engine, event, inspect
  from metadata.ingestion.source.database.iris.connection import preset_dialect_state
  engine = create_engine("iris://omd_reader_dict:Reader123@127.0.0.1:1972/USER")
  event.listen(engine, "do_connect", lambda d, r, a, k: preset_dialect_state(d, a, k))
  inspect(engine).get_unique_constraints("Patient", "Billing")
  ```

- **Expected:** `[{"name": "UqBillingCode", "column_names": ["Code"], ...}]`, as for `omd_reader` and `_SYSTEM`.
- **Actual:** `SQLCODE -99 Privilege violation`: with dictionary access the dialect's query joins
  `%Dictionary.IndexDefinition`, which the documented dictionary grants do not cover. Primary and foreign keys
  are not affected.
- **Connector behavior:** unique constraints come from `IRIS_UNIQUE_CONSTRAINTS` (`INFORMATION_SCHEMA.TABLE_CONSTRAINTS`
  joined to `KEY_COLUMN_USAGE` on schema and name), which works for every login.
- **User workaround:** none needed (granting `%Dictionary.IndexDefinition` would also work).
- **Upstream:** not raised yet.

### GAP-011 — View definitions are returned in IRIS's stored form

- **Component:** IRIS SQL catalog
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 002-metadata-core
- **Reproduction:** as `omd_reader`, with `.om/env/bin/python`

  ```python
  from sqlalchemy import create_engine, event, inspect
  from metadata.ingestion.source.database.iris.connection import preset_dialect_state
  engine = create_engine("iris://omd_reader:Reader123@127.0.0.1:1972/USER")
  event.listen(engine, "do_connect", lambda d, r, a, k: preset_dialect_state(d, a, k))
  print(repr(inspect(engine).get_view_definition("ActivePatient", "Clinic")))
  ```

  `SELECT VIEW_DEFINITION FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_NAME = 'ActivePatient'` returns the same text.
- **Expected:** the `SELECT` statement of the view.
- **Actual:** the text starts with the column list (`(PatientId,FullName)` plus a line break) and ends with a
  `/*#OPTIONS {...} */` comment; both sources return the identical text.
- **Connector behavior:** none. The text is stored as IRIS returns it; OpenMetadata's lineage parser reads it
  correctly (tables `Clinic.Patient` and `Clinic.Encounter` found; test `test_view_lineage`). No post-processing.
- **User workaround:** none.
- **Upstream:** not applicable: the connector handles it.

### GAP-012 — The connection's default filter patterns are not applied by ingestion workflows

- **Component:** OpenMetadata
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 002-metadata-core
- **Reproduction:** the framework filters with the pipeline's `schemaFilterPattern` only, so with none every schema
  the login can see is kept; as `omd_reader`, with `.om/env/bin/python`

  ```python
  from sqlalchemy import create_engine, event, inspect
  from metadata.ingestion.source.database.iris.connection import preset_dialect_state
  from metadata.utils.filters import filter_by_schema
  engine = create_engine("iris://omd_reader:Reader123@127.0.0.1:1972/USER")
  event.listen(engine, "do_connect", lambda d, r, a, k: preset_dialect_state(d, a, k))
  names = inspect(engine).get_schema_names()
  print([n for n in names if not filter_by_schema(None, n) and n.startswith(("%", "Ens"))][:3])
  ```

- **Expected:** the defaults of `irisConnection.json` (`^%`, `^INFORMATION_SCHEMA$`, `^Ens`) exclude system schemas.
- **Actual:** with no pipeline pattern the framework keeps every schema, system ones included (221 on the fixture
  Namespace of `latest-em`).
- **Connector behavior:** `apply_default_schema_filter` (`iris/metadata.py`, also used by `iris/lineage.py`) uses
  the connection's pattern when the pipeline has none; a pipeline pattern replaces it completely (ADR-0009). It only
  chooses between two user-visible configuration values.
- **User workaround:** none needed.
- **Upstream:** not applicable: the connector handles it.

### GAP-013 — Delimited CTE names are rejected

- **Component:** IRIS SQL
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 006-profiler-dq
- **Reproduction:** as `omd_reader`, with `.om/env/bin/python`

  ```python
  import iris
  cur = iris.connect("127.0.0.1", 1972, "USER", "omd_reader", "Reader123").cursor()
  cur.execute('WITH abc AS (SELECT 1 AS x) SELECT x FROM abc')       # works
  cur.execute('WITH "abc" AS (SELECT 1 AS x) SELECT x FROM "abc"')   # SQLCODE -400
  ```

- **Expected:** a delimited identifier is valid as a CTE name, as everywhere else.
- **Actual:** `SQLCODE -400` "Fatal error occurred" for every delimited CTE name, even `"ABC"`. OpenMetadata's
  sampler names its CTEs after an MD5 digest, which is quoted when it starts with a digit, so every sampled profile
  of such a table failed (SPIKE-04).
- **Connector behavior:** `IrisSampler` (`iris/sampler.py`, ADR-0016) puts a letter before the digest, so the name
  is a valid unquoted identifier. Nothing else in the query changes.
- **User workaround:** none needed.
- **Upstream:** not raised yet.

### GAP-014 — No random function in IRIS SQL

- **Component:** IRIS SQL
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 006-profiler-dq
- **Reproduction:** as `omd_reader`

  ```python
  import iris
  cur = iris.connect("127.0.0.1", 1972, "USER", "omd_reader", "Reader123").cursor()
  for sql in ("SELECT RAND()", "SELECT RANDOM()", "SELECT NEWID()", "SELECT {fn RAND()}"):
      try:
          cur.execute(sql)
      except Exception as exc:
          print(sql, str(exc).splitlines()[0])
  ```

- **Expected:** a random-number function, which OpenMetadata compiles from `RandomNumFn` for percentage and
  randomized sampling.
- **Actual:** `SQLCODE -359` for `RAND`, `RANDOM` and `NEWID`, and `SQLCODE -40` for `{fn RAND()}`. Extrinsic
  functions are disabled.
- **Connector behavior:** randomized row-count sampling runs unrandomized (the first `n` rows). Percentage sampling
  below 100% skips the table. Each gives one `IRIS-PROFILER-UNSUPPORTED` warning per run (ADR-0016). Nothing is
  emulated.
- **User workaround:** use a row-count sample.
- **Upstream:** not raised yet.

### GAP-015 — No percentile function in IRIS SQL

- **Component:** IRIS SQL
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 006-profiler-dq
- **Reproduction:** as `omd_reader`

  ```python
  import iris
  cur = iris.connect("127.0.0.1", 1972, "USER", "omd_reader", "Reader123").cursor()
  cur.execute("SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY Weight) FROM Clinic.Patient")  # SQLCODE -359
  ```

- **Expected:** `percentile_cont … WITHIN GROUP`, `MEDIAN` or `PERCENTILE`, which OpenMetadata's generic median uses.
- **Actual:** `SQLCODE -359` for each. Before spec 006, median, quartiles, interquartile range and
  non-parametric skew were silently missing from IRIS profiles, and the "median between" test aborted.
- **Connector behavior:** one `@compiles(MedianFn, "iris")` override
  (`patches/ingestion__src__metadata__profiler__orm__functions__median.py.patch`) computes a discrete percentile with
  a window over the schema-qualified table or the sample (ADR-0010). The per-dimension median is not supported.
- **User workaround:** none needed. The median is the discrete percentile, not an interpolated one.
- **Upstream:** not raised yet.

### GAP-016 — A delimited identifier cannot contain `.`

- **Component:** IRIS SQL
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 006-profiler-dq
- **Reproduction:** as `omd_reader`

  ```python
  import iris
  cur = iris.connect("127.0.0.1", 1972, "USER", "omd_reader", "Reader123").cursor()
  cur.execute('SELECT 1 AS "1.5 to 2.5"')  # SQLCODE -1
  ```

- **Expected:** any character is valid inside a delimited identifier.
- **Actual:** `SQLCODE -1` "Invalid SQL statement". OpenMetadata labels histogram bins `AS "61.500 to 71.750"`,
  so the histogram fails on every numeric column whose bin bounds have decimals.
- **Connector behavior:** the histogram is listed as unsupported in v1. The profiler's own failure for the column is
  in the status. The shared histogram file is not patched (ADR-0016).
- **User workaround:** none. Integer-only bins may work.
- **Upstream:** not raised yet.

### GAP-017 — Aggregate and scalar functions are not supported on stream columns

- **Component:** IRIS SQL
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 006-profiler-dq
- **Reproduction:** as `omd_reader`. `Clinic.Encounter.Notes` is `LONGVARCHAR`

  ```python
  import iris
  cur = iris.connect("127.0.0.1", 1972, "USER", "omd_reader", "Reader123").cursor()
  for sql in ("SELECT MIN(Notes) FROM Clinic.Encounter", "SELECT LEN(Notes) FROM Clinic.Encounter",
              "SELECT COUNT(DISTINCT Notes) FROM Clinic.Encounter"):
      try:
          cur.execute(sql)
      except Exception as exc:
          print(sql, str(exc).splitlines()[0])
  ```

- **Expected:** `MIN`, `MAX`, `LEN`, `COUNT(DISTINCT …)` and `CAST` on text and binary columns, as on other databases.
- **Actual:** `SQLCODE -37` "SQL scalar/aggregate/unary function not supported for stream fields". The profiler
  computes a column's static metrics in one query, so a stream column gets none of them, null count included.
  "Missing count" on a stream ends with `SQLCODE -313`.
- **Connector behavior:** stream columns (`LONGVARCHAR` → `TEXT`, `LONGVARBINARY` → `BLOB`) are documented as not
  profiled, and the profiler's failure is in the status. The IRIS test-suite interface aborts "value lengths between"
  and "missing count" on streams with the reason (spec 006 FR-012a).
- **User workaround:** exclude stream columns in the table's profiler settings.
- **Upstream:** not raised yet.

### GAP-018 — `IN`, `LIKE` and `GROUP BY` ignore the content of stream values

- **Component:** IRIS SQL
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 006-profiler-dq
- **Reproduction:** as `omd_reader`. 19 rows of `Clinic.Encounter.Notes` hold `checkup`, and the 53 non-NULL rows
  hold 3 distinct texts

  ```python
  import iris
  cur = iris.connect("127.0.0.1", 1972, "USER", "omd_reader", "Reader123").cursor()
  cur.execute("SELECT COUNT(*) FROM Clinic.Encounter WHERE Notes IN ('checkup')"); print(cur.fetchall())   # 0
  cur.execute("SELECT COUNT(*) FROM Clinic.Encounter WHERE Notes LIKE '%check%'"); print(cur.fetchall())   # 0
  cur.execute("SELECT COUNT(*) FROM Clinic.Encounter WHERE SUBSTRING(Notes, 1, 50) = 'checkup'"); print(cur.fetchall())  # 19
  cur.execute("SELECT COUNT(*) FROM (SELECT Notes FROM Clinic.Encounter WHERE Notes IS NOT NULL GROUP BY Notes)")
  print(cur.fetchall())  # 53
  ```

- **Expected:** 19, 19, 19 and 3, or an error.
- **Actual:** 0, 0, 19 and 53, with no error. OpenMetadata's "in set", "not in set" and "unique" tests on a stream
  column give wrong verdicts without any error.
- **Connector behavior:** the IRIS test-suite interface aborts "in set", "not in set" and "unique" on stream columns,
  with the reason and one `IRIS-PROFILER-UNSUPPORTED` warning per test type per run (spec 006 FR-012a).
- **User workaround:** none for these tests on stream columns.
- **Upstream:** not raised yet.

### GAP-019 — No regular-expression predicate in IRIS SQL

- **Component:** IRIS SQL
- **IRIS tracks:** latest-em reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 006-profiler-dq
- **Reproduction:** as `omd_reader`

  ```python
  import iris
  cur = iris.connect("127.0.0.1", 1972, "USER", "omd_reader", "Reader123").cursor()
  for sql in ("SELECT COUNT(*) FROM Clinic.Patient WHERE FullName REGEXP '^A'",
              "SELECT COUNT(*) FROM Clinic.Patient WHERE REGEXP_LIKE(FullName, '^A')"):
      try:
          cur.execute(sql)
      except Exception as exc:
          print(sql, str(exc).splitlines()[0])
  ```

- **Expected:** a regular-expression predicate, which OpenMetadata's regex tests use.
- **Actual:** `SQLCODE -14` for `REGEXP` and `SQLCODE -359` for `REGEXP_LIKE`. `%MATCHES` (glob) and `%PATTERN`
  (ObjectScript patterns) are not regular expressions. OpenMetadata catches the error and falls back to `LIKE` with
  the regex text as the pattern, so its regex tests give wrong verdicts without any error (SPIKE-04).
- **Connector behavior:** the IRIS test-suite interface aborts "values to match regex" and "values to not match
  regex" with the reason, and gives one warning per test type per run (spec 006 FR-012a).
- **User workaround:** none.
- **Upstream:** not raised yet.

### GAP-020 — IRIS 2026.3 refuses `COALESCE` with an untyped bound parameter

- **Component:** IRIS SQL
- **IRIS tracks:** latest-em not reproduced; latest-cd reproduced; latest-preview reproduced
- **Found in spec:** 006-profiler-dq
- **Reproduction:** as `omd_reader`

  ```python
  import iris
  cur = iris.connect("127.0.0.1", 1972, "USER", "omd_reader", "Reader123").cursor()
  cur.execute("SELECT COALESCE(SUM(PatientId), 0) FROM Clinic.Patient")       # works
  cur.execute("SELECT COALESCE(SUM(PatientId), ?) FROM Clinic.Patient", (0,))  # SQLCODE -378 on 2026.3
  ```

- **Expected:** a bound parameter takes the type of the other `COALESCE` arguments, as on 2026.1.
- **Actual:** `SQLCODE -378` "Datatype mismatch, explicit CAST is required" on 2026.3 (Build 212U). OpenMetadata's
  null count is `coalesce(SUM(…), 0)` with the 0 bound, and the profiler runs a column's static metrics in one query,
  so every static metric of every column failed on 2026.3. The between-bounds checker of the data-quality tests has
  the same form.
- **Connector behavior:** `iris/compiles.py` compiles `COALESCE` for the IRIS dialect with its bound values written as
  literals (`COALESCE(…, 0)`): the same SQL, with a constant in place of `?`. It is removable when IRIS accepts the
  parameter again.
- **User workaround:** none needed.
- **Upstream:** not raised yet.
