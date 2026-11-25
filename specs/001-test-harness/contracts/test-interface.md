# Contract: test interface

Implements FR-016..FR-022. File: `overlay/ingestion/tests/integration/iris/conftest.py`. Owner: spec 001.
New needs go through the fixture owner.

## Environment (the only interface between CI or Makefile and tests)

| Variable | Example | Meaning |
|---|---|---|
| `IRIS_HOST` | `127.0.0.1` | unset → testcontainers fallback (`latest-em`) |
| `IRIS_PORT` | `1972` | superserver port |
| `IRIS_NAMESPACE` | `USER` | |
| `IRIS_TAG` | `latest-cd` | reporting and tag-specific expectations only; fallback uses it as the image tag (default `latest-em`) |
| `IRIS_LOGIN` | `reader_dict` | `admin` · `reader` · `reader_dict` (default `reader`) |

## Fixtures (all `scope="session"`)

| Fixture | Type | Contract |
|---|---|---|
| `iris_cell` | frozen dataclass `IrisCell(tag, login, host, port, namespace, username, password, is_admin, has_dict_grant)` + property `name` → `iris-<tag>-<login>` | values from env + catalog; invalid login → `pytest.UsageError` |
| `iris_service_connection` | `IrisConnection` (spec 000 model) for the cell's login: `hostPort`, `username`, `authType.password`, `namespace` | skips with "spec 000 connector package not available (<cell>)" when the package is not importable |
| `iris_engine` | SQLAlchemy `Engine` from the connector's `get_connection(iris_service_connection)` | ADR-0015 presets apply because the connector applies them; disposed at session end |
| `iris_admin_engine` | same, for admin | **only** for setup and assertions, never for the behavior under test |
| `seeded` | `None` | CI and Makefile: runs `self_check` as admin and fails the session if it does not pass. Fallback: `load` first. Every integration test depends on it, directly or through the engines |

Private: `_iris_endpoint` yields `(host, port, tag)` and owns the fallback container lifecycle.

## Marker

`@pytest.mark.iris` on every integration test. It is registered by the conftest's `pytest_configure`.
Run selection: `-m iris`.

## Rules for test authors

1. Branch expectations on `iris_cell.has_dict_grant` / `iris_cell.is_admin`, never on `login` strings.
2. A test that does not apply calls `pytest.skip(f"... ({iris_cell.name})")`. Never skip silently,
   never `return` early.
3. Never create IRIS users or datasets. Create objects only in `Scratch`, drop them in a `finally` or
   fixture teardown, and never assert on objects you did not create.
4. Need a new shared case? Add it to the fixture catalog (additive) in your spec's PR; the fixture
   owner reviews it.
5. OpenMetadata's root integration conftest applies unchanged: `xdist_group("iris_suite")` is
   automatic, and image pulls are retried on transient registry errors.

## Placeholder test (`test_harness.py`)

| Test | Assertion | Cells |
|---|---|---|
| `test_select_one` | `SELECT 1` through `iris_engine` returns 1 | all 9 |
| `test_dictionary_toggle` | `SELECT TOP 1 Name FROM %Dictionary.CompiledProperty` succeeds iff `has_dict_grant`; otherwise the error carries `-99` | all 9 |
| `test_cell_identity` | `SELECT $ZVERSION` contains `IRIS`; the value is recorded as a test property for the job summary | all 9 |
