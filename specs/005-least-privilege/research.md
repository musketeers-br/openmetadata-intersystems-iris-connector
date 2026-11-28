# Research: Least privilege and access-gap reporting

Evidence for [plan.md](plan.md). Sources:

- **SPIKE-03** (VECTOR and least privilege, 2026-11-26, the three tracks), run in the planning
  repository before this spec. Its results and the decisions both developers took on 2026-11-26 are
  copied below (R1); the experiment is not redone.
- **Probes of 2026-11-26** for this plan, on `latest-em` 2026.1 (Build 234U) and `latest-cd` 2026.3
  (Build 212U), as `omd_reader`, `omd_reader_dict` and `_SYSTEM`, against the fixtures (catalog v2)
  plus temporary `Restricted` tables: a throwaway integration test that drove `IrisSource` as the
  framework does per table (R2, R4).
- **Code reading** of OpenMetadata 2.1.1 (`common_db_source.py`, `workflow/base.py`) and of the
  connector's `iris/` package as of spec 003 (R3, R5).

No `NEEDS CLARIFICATION` remained in the Technical Context.

## R1 — What SPIKE-03 settled

Identical on the three tracks:

| Privileges of the login on `Restricted.Secret` | Listed in `TABLES` | Columns in `COLUMNS` | `SELECT COUNT(*)` |
|---|---|---|---|
| none | no | none | -99 |
| `SELECT` on the schema | yes | all | ok |
| `SELECT` on the schema, then `REVOKE SELECT ON Restricted.Secret` | yes | all | **ok: the revoke has no effect** |
| `SELECT` on the table, then `REVOKE` | no | none | -99 |
| `SELECT (Id)` only | yes | `Id` only | -99 (`SELECT Id` works) |
| `INSERT`, `UPDATE` or `REFERENCES` only | yes | all | -99 |

- A table the login holds no privilege on is **invisible**. `INFORMATION_SCHEMA.TABLE_PRIVILEGES`
  and `COLUMN_PRIVILEGES` do not exist (`SQLCODE -30`).
- Invisible tables can be listed only with `SELECT` on `%Dictionary.CompiledClass` (a third optional
  grant), comparing its SQL names with `INFORMATION_SCHEMA.TABLES` outside the system schemas.
- `%Dictionary.PropertyDefinition` alone gives VECTOR element type and dimension, and it is the table
  the dialect and Test Connection already probe.

**Decisions (both developers, 2026-11-26)**:

- **ADR-0007**: one optional grant, `GRANT SELECT ON %Dictionary.PropertyDefinition`; spec 004
  implements VECTOR detail on it.
- **ADR-0008**: invisible objects stay a documented limitation. Detection through
  `%Dictionary.CompiledClass` is a possible later extra in this spec only if time allows; it is out
  of scope here.
- **Fixture**: `Restricted.Secret` granted to the readers with `GRANT REFERENCES`, in a schema with
  no schema-level grant. This spec updates ADR-0008's validation text and the fixtures contract.

## R2 — A visible-but-unreadable table produces no warning today

- **Method**: create `Restricted.Secret` (`GRANT REFERENCES` to both readers), `Restricted.ColumnOnly`
  (`GRANT SELECT (Id)`) and `Restricted.Hidden` (no grant). As each reader, list schema `Restricted`
  and run `get_columns_and_constraints` and `get_table_description` on each listed table, as the
  framework does; then read the status.
- **Result** (same for both readers, both tracks):
  - `Restricted` is listed; `get_table_names("Restricted")` returns `ColumnOnly`, `Secret` (not
    `Hidden`).
  - `Secret`: all 3 columns with types, PK and NOT NULL; description read (none set).
    `ColumnOnly`: only `Id`.
  - `status.warnings == []`. Every catalog read succeeds, because they all read
    `INFORMATION_SCHEMA`, which shows a table to any login holding any privilege on it.
  - Any read of the rows fails: `SELECT TOP 0 * FROM "Restricted"."Secret"` → `SQLCODE -99`;
    the same for `ColumnOnly` (its hidden column) and `Hidden`.
- **Decision**: add a readability check (spec FR-005). Once per cataloged table and view, run
  `SELECT TOP 0 * FROM "<schema>"."<table>"` through the helper; feature name `data`.
- **Rationale**: it is the only thing that tells the steward the table is cataloged but not readable,
  and that a column-level grant may have hidden columns. It reads no rows.
- **Alternatives considered**:
  - Leave the warning to the profiler (spec 006): the metadata run, which every user runs, would stay
    silent, and the demand's acceptance ("exactly one warning, run completes") could not hold for a
    metadata ingestion.
  - Compare the column count with the dictionary: needs a dictionary grant (constitution IV).
  - `SELECT COUNT(*)`: reads the table; `TOP 0` only prepares the statement.

## R3 — Where the framework is silent today

Read in OpenMetadata 2.1.1:

- `CommonDbSourceService.get_tables_name_and_type` wraps `query_table_names_and_types(schema)` and
  `query_view_names_and_types(schema)` in `except Exception` with `logger.warning` and `logger.debug`
  only. A schema whose table or view list fails disappears from the catalog with no status entry.
- `get_schema_definition`'s default logs at debug; spec 002 already overrides it through the helper.
- `get_table_description`'s default logs a warning; spec 002 already overrides it.
- `raise_from_status()` raises only on failures (and on warnings only with `raise_warnings=True`), so
  access warnings never fail a test workflow that does not ask for it.

**Decision**: override `query_table_names_and_types` and `query_view_names_and_types` in `IrisSource`
to call the framework's own method inside `report_access_gap`, keyed on the schema FQN, features
`tables` and `views`, returning an empty list on failure (spec FR-004). The framework's `except` then
never fires for a database error.

## R4 — The readability check in practice

| Object, as `omd_reader` | `SELECT TOP 0 * FROM "<schema>"."<table>"` | Time |
|---|---|---|
| `Clinic.ActivePatient` (view) | ok | 30–80 ms (first prepare) |
| `Clinic.Patient`, `Types.AllTypes` | ok | 3–23 ms |
| `Restricted.Secret`, `Restricted.ColumnOnly` | `SQLCODE -99` | 4–5 ms |
| `Restricted.Hidden` (not listed) | `SQLCODE -99` (not -30) | 4 ms |

- After each failure, the next read on the same SQLAlchemy connection works; no rollback is needed
  (autocommit, as spec 002's helper already assumes).
- As `_SYSTEM`, every object reads.
- Identifiers are quoted with the dialect's own `identifier_preparer.quote_identifier`, so mixed case
  and names with unusual characters are read exactly (Principle III).
- `Hidden` answers -99, not "table not found": a login that knows a name can tell the table exists.
  The connector never guesses names, so this does not change the limitation; it is noted for the docs.

**Decision**: the probe text is a template in `queries.py`
(`IRIS_READ_PROBE = 'SELECT TOP 0 * FROM {schema}.{table}'`), filled with quoted identifiers and run
with `exec_driver_sql`, because `text()` would read a colon in a quoted name as a bind parameter. It
runs from an override of the framework's `get_columns_and_constraints`, which the framework calls
once per cataloged table and view, after the framework's own reads. The cost, one prepare per
object, needs no batching (constitution: measure first).

**Revised during implementation**: the plan put the call in spec 002's `_get_columns_internal`, next
to spec 003's. The override keeps spec 002's code and unit tests unchanged: their connection stub
has no dialect to quote with, and the tests call `_get_columns_internal` directly. It also leaves
`_get_columns_internal` to specs 003 and 004.

## R5 — Error handlers in `iris/` today

| File | Handler | Verdict |
|---|---|---|
| `metadata.py` `report_access_gap` | `except SQLAlchemyError` → `self.status.warning` | the helper itself |
| `connection.py` dialect-state preset (ADR-0015) | `except dialect.dbapi.Error` → `_dictionary_access = False` | not an access gap of an object: it decides how the dialect reflects. Allow-listed with that reason |
| `connection.py` `_get_client` | `except ImportError` → re-raise as `MissingPluginException` | re-raises |

**Decision** for the guard test (spec FR-011): parse every `.py` file of `iris/` with `ast`. Each
`except` handler must re-raise, call `status.warning(...)`, or appear in an allow list keyed on
`(file, function)` with a reason. `contextlib.suppress(...)` counts as a handler. The test prints the
file and line of each offender. Test Connection steps (`connection.py`) raise to the framework, which
records the step result, so they need no entry.

## R6 — Minimal grants (for `quickstart.md`)

- **Metadata**: `CREATE USER <login> IDENTIFIED BY <password>` plus `GRANT SELECT ON SCHEMA <schema>
  TO <login>` for each schema is what the fixtures' `omd_reader` has; the whole suite passes with it
  (spec 001 and 002 matrices). No role, no `%Native_ClassExecution` (ADR-0015 presets), no
  password-unexpire step for a login created by SQL.
- **View definitions**: the same `SELECT` (spec 002's view tests pass as `omd_reader`).
- **VECTOR detail**: `GRANT SELECT ON %Dictionary.PropertyDefinition TO <login>`, optional (R1).
  The dictionary grants show class and property names of the whole Namespace, not data (SPIKE-03).
- **Profiler, data quality**: `SELECT` expected; spec 006 confirms. A column-level `SELECT` breaks
  `COUNT(*)` (R1), so the profiler's row count fails on such tables.
- **dbt lineage**: no IRIS grant expected (dbt artifacts are read outside IRIS); spec 007 confirms.
- **A table-level `REVOKE` does not override a schema-level `GRANT`** (R1): to keep one table out,
  grant table by table, or put it in a schema the login has no grant on.

## Implementation measurements (2026-11-26)

Local cells: `latest-em` 2026.1 (Build 234U), `latest-cd` and `latest-preview` 2026.3 (Build 212U),
fixtures at catalog v3.

- **Fixtures**: the loader ran twice on each track, `FIXTURES OK v3` each time. C12 adds 16 passes
  (2 readers × 8). `pytest fixtures`: 57 passed on each track, after the rebase onto spec 002
  `854c532`, which carries spec 001's `not applicable` value. Before it, `test_gap_report.py` failed
  on GAP-011 and GAP-012.
- **Unit tests** (no IRIS): 122 passed. That is specs 002 and 003 (94, unchanged) plus
  `test_iris_access.py` (21) and `test_iris_access_guard.py` (7).
- **Guard, by hand** (quickstart step 3): a `try/except Exception: pass` appended to `types.py` failed
  the guard with `types.py:176`; removed, it passed again.
- **Integration**, `pytest tests/integration/iris -m iris` per cell. The skips are the server-bound
  Part B tests and the tests that branch on the login.

  | Track | `admin` | `reader` | `reader_dict` |
  |---|---|---|---|
  | `latest-em` | 30 passed, 11 skipped | 31 passed, 10 skipped | 30 passed, 11 skipped |
  | `latest-cd` | 30 passed, 11 skipped | 31 passed, 10 skipped | 30 passed, 11 skipped |
  | `latest-preview` | 30 passed, 11 skipped | 31 passed, 10 skipped | 30 passed, 11 skipped |

- **`test_access.py`**: for each reader on every track, exactly two `data` warnings
  (`Restricted.Secret`, `Restricted.ColumnGrant`). `Secret` is cataloged with 3 columns and
  `ColumnGrant` with `Id` only. `Hidden` is not listed. As `admin`, no warning, 3 tables, and
  `ColumnGrant` has 2 columns. Reading all of `READER_SCHEMAS` gives no access warning for any login.
- **Filters** (review decision, 2026-11-26: probe only what passes the filters):
  - In the framework's topology, `get_tables_name_and_type` produces the tables and views, and
    `yield_table`, which calls `get_columns_and_constraints` and so the probe, processes only what it
    yields.
  - The producer drops tables cut by `tableFilterPattern`, and schemas cut by `schemaFilterPattern`
    are never listed.
  - `test_a_filtered_out_table_is_not_probed` excludes `^Secret$`: `Secret` is not listed and gets
    no warning, and the readers get only the `ColumnGrant` warning.
- **One dictionary grant** (review note, 2026-11-26): `omd_reader_dict` no longer holds
  `%Dictionary.CompiledProperty`.
  - The dialect reads only `%Dictionary.PropertyDefinition` and `%Dictionary.IndexDefinition`
    (`sqlalchemy-intersystems-iris` 1.0.2 source).
  - Spec 004 reads `PropertyDefinition`.
  - With the reduced grant, every cell above passes, and so do `test_cell_login.py` and
    `test_harness.py`'s dictionary checks, which now probe `PropertyDefinition`.
- **Probe cost**: `check_readable` was timed per object on a warm connection on `latest-em` and
  `latest-cd`.
  - Most objects, refusals included: 2.6–5.0 ms.
  - First prepare of `Scratch.Keep` as `_SYSTEM`: about 20 ms.
  - The test that reads every readable fixture (7 objects) takes about 0.5 s as `admin` and 2.0 s as
    a reader. The probe accounts for at most about 35 ms of either.
- **US1 (same results as `admin` for an ordinary login)**: the whole suite passes as `reader` and
  `reader_dict` on the three tracks. For `READER_SCHEMAS` they get the same expectations as `admin`.
  Spec 004 has not landed, so `AI.Embedding.Vec` is `VARCHAR(1037)` for every login.
- **Grants table** (T017): a throwaway login and schemas on `latest-em`, removed afterwards.
  - `CREATE USER … IDENTIFIED BY "Pw-1x"` sets the password `Pw-1x`; the quotes only delimit it.
  - The login connects with no unexpire step.
  - After `GRANT SELECT ON SCHEMA` and `REVOKE SELECT ON <schema>.Payroll`, the login still lists and
    reads `Payroll`.
  - With `GRANT SELECT ON <schema>.Orders` only, the login lists `Orders` and not the schema's other
    table.
