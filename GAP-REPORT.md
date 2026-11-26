# Gap Report

Limitations of IRIS, its official driver and dialect, or OpenMetadata that the connector works around or
documents (constitution, Principle V; ADR-0013). Every entry has a reproduction against the shared
fixtures. Spec 001 completes the seed entries; each spec appends its own.

Reproductions below use the seeded `USER` Namespace, login `omd_reader` (`SELECT` only), on IRIS
`latest-em` (2026.1), `sqlalchemy-intersystems-iris` 1.0.2, `intersystems-irispython` 5.4.1. Tracks
`latest-cd` and `latest-preview` are checked by the matrix in spec 001.

### GAP-004 — Dialect reads the server version through the Native API

- **Component:** official dialect
- **IRIS tracks:** latest-em (reproduced); latest-cd, latest-preview pending spec 001
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
- **IRIS tracks:** latest-em (reproduced); latest-cd, latest-preview pending spec 001
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
