# Implementation Plan: Least privilege and access-gap reporting

**Branch**: `005-least-privilege` (built on spec 003; agreed order 000 → 001 → 002 → 003, then 005) |
**Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-least-privilege/spec.md`

## Summary

Make a plain `SELECT` login enough, and leave no access problem silent:

- `metadata.py` gets a section `--- 005: access gaps ---`:
  - `check_readable(schema, table)` runs a no-row read of each cataloged table and view through the
    helper (feature `data`), because every catalog read succeeds on a visible-but-unreadable table
    (research R2);
  - `query_table_names_and_types` and `query_view_names_and_types` call the framework's methods inside
    the helper, keyed on the schema FQN (features `tables`, `views`), because the framework only logs
    a failed listing (R3).
- `queries.py` gets the probe template `IRIS_READ_PROBE`.
- The fixtures gain schema `Restricted` with `Secret` (`GRANT REFERENCES`), `ColumnGrant` (one-column
  `SELECT`) and `Hidden` (no grant), as catalog v3.
- Tests:
  - unit tests make each read raise and assert the status warning;
  - an AST guard test fails on any error handler in `iris/` that neither warns nor re-raises (R5);
  - integration tests on every cell count the warnings for `Restricted`.
- Docs:
  - the minimal grants table in `quickstart.md` (R6);
  - ADR-0008 and GAP-003 updated;
  - the warnings and fixtures contracts updated in the planning repository.

## Technical Context

**Language/Version**: Python 3.11 (OpenMetadata 2.1.1 ingestion).

**Primary Dependencies**:
- OpenMetadata 2.1.1: `CommonDbSourceService.query_table_names_and_types` and
  `query_view_names_and_types`, `Status`, `fqn.build`.
- SQLAlchemy 2.0: `identifier_preparer.quote_identifier`, `SQLAlchemyError`.
- Spec 002: `report_access_gap`, `_table_fqn`. Spec 003: the column-read hook. Spec 001: fixtures and
  conftest.

**Storage**: none; IRIS Community containers for tests.

**Testing**: pytest.
- Unit tests, no IRIS: `test_iris_access.py` (each read raises → status warning) and
  `test_iris_access_guard.py` (AST over `iris/`), in `overlay/ingestion/tests/unit/topology/database/`.
- Integration tests, marked `iris`: `overlay/ingestion/tests/integration/iris/test_access.py`. They
  drive `IrisSource` as spec 002's Part A does, with no OpenMetadata server, so they run in every CI
  cell.
- Fixture tests (`pytest fixtures`) cover the loader change.

**Target Platform**: the CI matrix of spec 001 (9 cells) and local cells (`make test-cell`).

**Project Type**: connector code in the overlay (ADR-0014), plus fixture and docs changes.

**Performance Goals**: one no-row prepare per cataloged table and view, measured at 3–80 ms (R4); no
batching without a measured problem.

**Constraints**:

- **One mechanism:** `report_access_gap` stays the only place that turns read failures into warnings
  (ADR-0008). It is hardened, not duplicated.
- **Direct SQL only in `queries.py`**; identifiers quoted by the dialect (Principle III).
- **Other specs' code:** spec 002 code is changed only to add one call next to spec 003's in
  `_get_columns_internal`. The `--- 004 ---` sections stay free.
- **Warnings, not logs:** warnings go in the ingestion status, never only in logs (Principle V), with
  no credentials or row data.
- **Fixtures:** changes are additive (ADR-0012).
- **No new grant:** no dictionary or write privilege is needed for any core feature (Principle IV).

**Scale/Scope**: 3 fixture tables; 2 overridden framework methods; 1 new per-object read; about 10
error paths under unit test.

## Constitution Check

| Gate | Plan | Status |
|---|---|---|
| I. Framework First | The listing overrides call the framework's own methods; tables are still built by `CommonDbSourceService` | ✅ |
| II. Official Driver Only | All reads through the connector's engine | ✅ |
| III. IRIS Fidelity | The probe quotes the exact schema and table name; the warning key is the exact FQN | ✅ |
| IV. Least Privilege | The feature itself: a `SELECT`-only login is the target; no new grant for core features | ✅ |
| V. Nothing Silent | Readability check, listing overrides, guard test, one warning per object and feature | ✅ |
| VI. Tested on the Matrix | `Restricted` in the shared fixtures; integration tests on every cell | ✅ |
| VII. Upstream-Ready | Code inside `.om/`, `make py_format` on touched files, license headers | ✅ |
| VIII. English Artifacts | ✅ | ✅ |
| Workflow: spikes reviewed first | SPIKE-03 reviewed and its decisions agreed on 2026-11-26 | ✅ |

**Post-design re-check**: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/005-least-privilege/
├── plan.md               # this file
├── research.md           # SPIKE-03 decisions (R1), probes R2–R4, handler audit R5, grants R6
├── data-model.md         # access gap, features, Restricted fixtures (catalog v3), guard allow list
├── quickstart.md         # the minimal grants table (for spec 008) and how to check the feature
├── contracts/
│   └── access-gap-warning.md   # keys, features, text, de-duplication, where each read is wrapped
├── checklists/requirements.md
└── tasks.md              # /speckit-tasks
```

### Source code

```text
# OpenMetadata tree (overlay/, edited in .om/, Collate Community License header)
overlay/ingestion/src/metadata/ingestion/source/database/iris/
├── queries.py       # + section 005: IRIS_READ_PROBE
└── metadata.py      # + section "--- 005: access gaps ---": check_readable(), _schema_fqn(),
                     #   query_table_names_and_types(), query_view_names_and_types();
                     #   one call in 002's _get_columns_internal, after 003's
overlay/ingestion/tests/unit/topology/database/test_iris_access.py          # new
overlay/ingestion/tests/unit/topology/database/test_iris_access_guard.py    # new
overlay/ingestion/tests/integration/iris/test_access.py                     # new
overlay/ingestion/tests/integration/iris/data/seed.py                       # catalog v3: Restricted
overlay/ingestion/tests/integration/iris/test_types.py                      # skip schemas the readers
                                                                            #   have no SELECT grant on

# Dev-repo files
fixtures/iris/test_seed.py           # catalog v3 assertions
GAP-REPORT.md                        # GAP-003 reproduction and actual behavior
docs/adr/0008-access-gaps-as-warnings.md   # updated (FR-013)
```

**Structure Decision**: everything new lives in the `--- 005 ---` sections. Spec 002's helper and
its existing call sites stay as they are; the hardening is tests plus the missing call sites.

## Build order

1. Fixture `Restricted` (catalog v3) with its self-check, and the `test_types.py` filter.
2. Unit tests for every read path and the guard test (seen failing for the new paths).
3. `IRIS_READ_PROBE`, the `--- 005 ---` section, the call site.
4. Integration tests; run on three tracks × three logins locally.
5. Grants table, ADR-0008, GAP-003, contracts.

## Dependencies

- **Spec 002**: `report_access_gap`, `_table_fqn`, `_get_columns_internal`. Merges first.
- **Spec 003**: the fixture catalog v2 and the column-read call site. This branch starts from 003.
- **Spec 004** uses the helper for its dictionary reads. The VECTOR grant row of the grants table is
  confirmed there.
- **Spec 006** uses the helper for sample data and profile. The profiler and data-quality rows are
  confirmed there.
- **Spec 007** confirms the dbt row.
- **Spec 008** moves the grants table into the docs page.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| One extra query per table and view | Nothing else reveals a visible-but-unreadable table (R2) | Leaving it to the profiler keeps every metadata run silent; a dictionary compare needs a grant (Principle IV) |
| Built on unmerged specs (002, 003) | The call site and the fixture version come from them | Waiting would idle the spec until 003 merges; the branch rebases like 003 did |
