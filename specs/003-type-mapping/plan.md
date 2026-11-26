# Implementation Plan: Type mapping

**Branch**: `003-type-mapping` (built on spec 002 applied on spec 001 until both merge; agreed order 000 → 001 → 002 → 003) |
**Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-type-mapping/spec.md`

## Summary

Give every ingested IRIS column the right OpenMetadata type from one table:

- `iris/types.py` (section `--- 003: type map ---`) holds the table of the 15 `DATA_TYPE` values the
  IRIS SQL catalog reports on all three tracks (research R1, R4), the resolver that turns a column's
  raw catalog facts into a SQLAlchemy type plus a display string, the unknown-type record, and the
  Markdown renderer;
- `queries.py` gets one bound query for a table's raw column types;
- `metadata.py` gets a section `--- 003: type map ---` with `map_column_types`, called once at the end
  of spec 002's `_get_columns_internal`;
- the fixtures gain `Types.AllTypes` (catalog v2);
- unit tests per row and for the unknown path, integration tests on every cell, and the generated
  table in `contracts/type-mapping.md`.

The framework still builds every column (constitution I): the connector only hands it a SQLAlchemy
type that `ColumnTypeParser` maps to the row's type, and the IRIS display string (research R3).

## Technical Context

**Language/Version**: Python 3.11 (OpenMetadata 2.1.1 ingestion).

**Primary Dependencies**: OpenMetadata 2.1.1 (`SqlColumnHandlerMixin`, `ColumnTypeParser`,
`DataType`, `Status`); SQLAlchemy 2.0 types; `sqlalchemy-intersystems-iris` 1.0.2 only through the
connector's engine; spec 002's `IrisSource` and `report_access_gap`; spec 001's fixtures and
conftest.

**Storage**: none; IRIS Community containers for tests.

**Testing**: pytest. Unit tests in `overlay/ingestion/tests/unit/topology/database/test_iris_types.py`
(no IRIS). Integration tests `overlay/ingestion/tests/integration/iris/test_types.py`, marked `iris`,
driving `IrisSource.get_columns_and_constraints` against the fixtures as spec 002's Part A does (no
OpenMetadata server, so they run in every CI cell). Fixture tests (`pytest fixtures`) cover the loader
change.

**Target Platform**: the CI matrix of spec 001 (9 cells) and local cells (`make test-cell`).

**Project Type**: connector code in the overlay (ADR-0014), plus fixture and docs changes.

**Performance Goals**: one extra bound query per table (the column types); the constitution asks for a
measured problem before any batching.

**Constraints**:

- one mapping module (constitution III, ADR-0006); direct SQL only in `queries.py`;
- no change to how spec 002 reads columns, keys or descriptions (FR-007);
- the `--- 004: VECTOR enrichment ---` sections of `types.py` and `metadata.py` stay free (FR-006);
- warnings in the ingestion status, never only in logs (constitution V);
- fixture changes additive (ADR-0012).

**Scale/Scope**: 15 type rows; 1 fixture table with 15 columns; 1 call site in spec 002's code.

## Constitution Check

| Gate | Plan | Status |
|---|---|---|
| I. Framework First | Columns are still built by `SqlColumnHandlerMixin`; the connector only sets `type` and `system_data_type` on the column dicts | ✅ |
| II. Official Driver Only | Reads through the connector's engine (official dialect) | ✅ |
| III. IRIS Fidelity | One mapping module; identity `(schema, table, column)` in the type query; unknown → `UNKNOWN`, one warning per type per run | ✅ |
| IV. Least Privilege | Raw types come from `INFORMATION_SCHEMA.COLUMNS`, readable by both reader logins; no dictionary access | ✅ |
| V. Nothing Silent | `IRIS-UNKNOWN-TYPE` in the status; type-query failures go through `IRIS-ACCESS`; GAP-008 stays reported, not patched (the connector reads the catalog instead of fixing the dialect) | ✅ |
| VI. Tested on the Matrix | Integration tests on every cell; `Types.AllTypes` in the shared fixtures | ✅ |
| VII. Upstream-Ready | Code inside `.om/`, `make py_format` on touched files, license headers | ✅ |
| VIII. English Artifacts | ✅ | ✅ |
| Workflow: spikes reviewed first | No spike: discovery is part of this spec's research (the type-map plan allows "from SPIKE-02 or discovery"); SPIKE-02 gave only the fixture types | ✅ |

**Post-design re-check**: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/003-type-mapping/
├── plan.md               # this file
├── research.md           # discovery on 3 tracks (R1), design decisions R2–R8
├── data-model.md         # type row, column facts, resolved type, unknown record, fixture v2
├── quickstart.md         # how to check the feature by hand
├── contracts/
│   ├── type-mapping.md         # the generated table (between markers) + rules
│   └── unknown-type-warning.md # warning key, text, de-duplication
├── checklists/requirements.md
└── tasks.md              # /speckit-tasks
```

### Source code

```text
# OpenMetadata tree (overlay/, edited in .om/, Collate Community License header)
overlay/ingestion/src/metadata/ingestion/source/database/iris/
├── types.py         # section "--- 003: type map ---": IRIS_TYPES, ColumnFacts, resolve(), UnknownTypes,
│                    #   unknown_type_message(), render_markdown_table(), __main__ prints the table
├── queries.py       # + IRIS_COLUMN_TYPES (bound on schema and table)
└── metadata.py      # + section "--- 003: type map ---": map_column_types(); one call at the end of
                     #   002's _get_columns_internal
overlay/ingestion/tests/unit/topology/database/test_iris_types.py    # new
overlay/ingestion/tests/integration/iris/test_types.py               # new
overlay/ingestion/tests/integration/iris/data/seed.py                # catalog v2: Types.AllTypes

# Dev-repo files
fixtures/iris/discover_types.py      # rerunnable discovery (research R1), plain venv
docs/adr/0006-single-type-map.md     # updated (FR-015)
```

**Structure Decision**: the mapping and everything derived from it (resolver, unknown record,
renderer) are in `types.py`; `metadata.py` only wires them into the column read, as ADR-0006 and the
section markers of spec 000 intend.

## Build order

1. Fixture `Types.AllTypes` (catalog v2) with its self-check, and `discover_types.py`.
2. Unit tests for the table, the resolver and the unknown record (seen failing).
3. `types.py` section 003; `IRIS_COLUMN_TYPES`; `map_column_types` and the call site.
4. Integration tests on the fixtures; run on all three tracks × three logins locally.
5. Renderer, generated contract table, ADR-0006 update.

## Dependencies

- **Spec 002**: `IrisSource._get_columns_internal`, `report_access_gap`, `_table_fqn`, `queries.py`.
  The branch is built on a local copy of 002 (origin `0c37079`) applied on 001; when 002 rebases on
  001 and merges, 003 rebases on it. The only line 003 adds to 002's code is the call at the end of
  `_get_columns_internal`.
- **Spec 001**: the loader (`Types.AllTypes`), conftest fixtures, the matrix.
- **Spec 004** builds on the `--- 004 ---` sections and the VECTOR column's `VARCHAR` row.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Built on an unmerged spec (002) | The only correct call site is in 002's column read | Overriding `_get_columns_internal` again in a 003 section would silently shadow 002's override after a merge (two methods of the same name in one class) |
