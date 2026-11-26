# Implementation Plan: VECTOR enrichment

**Branch**: `004-vector-enrichment` (built on spec 005, which is built on 003; agreed order
000 → 001 → 002 → 003 → 005 → 004) | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-vector-enrichment/spec.md`

## Summary

Catalog VECTOR columns as `ARRAY` of their element type, displayed `VECTOR(<TYPE>, <dim>)`, when
the login can read `%Dictionary.PropertyDefinition`. Without access, give one hint per run.

- **`queries.py`**: section `--- 004 ---` gets `IRIS_VECTOR_COLUMNS`, one join of
  `%Dictionary.PropertyDefinition` with `INFORMATION_SCHEMA.TABLES.CLASSNAME` for every
  `%Library.Vector` property (research R2).
- **`types.py`**: section `--- 004 ---` gets:
  - the element table;
  - `parse_vector_parameters()`;
  - `resolve_vector()`, which gives an `ARRAY` SQLAlchemy type and the display;
  - the native-metadata branch for a `DATA_TYPE` that names VECTOR (R4);
  - the two message builders.
- **`metadata.py`**: section `--- 004 ---` gets:
  - `enrich_vector_columns(schema, table, columns)`, called once in `_get_columns_internal` after
    spec 003's map;
  - a per-run cache of the dictionary read, which is skipped when the ADR-0015 preset says there is
    no access;
  - the hint and the per-column parameter warning.
- **Fixtures**: `AI.Embedding` gains `Vec4 VECTOR(INT, 4)` and `"vec_low" VECTOR(FLOAT, 2)` (catalog
  v4).
- **Tests**:
  - unit tests for parsing, the once-per-run read, the hint and the native branch;
  - integration tests on every cell, branching on `has_dict_grant`;
  - spec 003's `Vec` assertion moves to this branching.
- **Docs**:
  - ADR-0007 becomes *Accepted*;
  - GAP-001 and GAP-002 name `PropertyDefinition`;
  - the "VECTOR columns" note goes in `quickstart.md`;
  - the warnings, type-mapping and fixtures contracts are updated in the planning repository.

## Technical Context

**Language/Version**: Python 3.11 (OpenMetadata 2.1.1 ingestion).

**Primary Dependencies**:
- OpenMetadata 2.1.1: `SqlColumnHandlerMixin`, which builds `ARRAY` columns and reads `item_type` for
  `arrayDataType`; `Status`; `fqn.build`.
- SQLAlchemy 2.0 `ARRAY`.
- The ADR-0015 preset: `engine.dialect._dictionary_access`.
- Spec 003's `resolve()` and column hook; spec 005's guard test and fixture catalog v3.

**Storage**: none; IRIS Community containers for tests.

**Testing**: pytest.
- Unit tests in `overlay/ingestion/tests/unit/topology/database/test_iris_vector.py`, no IRIS.
- Integration tests in `overlay/ingestion/tests/integration/iris/test_vector.py`, marked `iris`,
  driving `IrisSource` as specs 003 and 005 do. They run in every CI cell.
- Fixture tests (`pytest fixtures`).

**Target Platform**: the CI matrix of spec 001 (9 cells) and local cells.

**Project Type**: connector code in the overlay (ADR-0014), plus fixture and docs changes.

**Performance Goals**: one dictionary query per run, 120–620 ms measured on the fixtures (R2); none
for a login without access.

**Constraints**:

- Never a prerequisite (constitution IV); one hint per run (V).
- Direct SQL only in `queries.py`; identity by `(schema, table, column)` from the join (III).
- Only the `--- 004 ---` sections, plus one call in `_get_columns_internal`.
- Additive fixture change (ADR-0012).

**Scale/Scope**: 5 element types (6 spellings); 3 fixture VECTOR columns; 1 query per run; 1 call
site.

## Constitution Check

| Gate | Plan | Status |
|---|---|---|
| I. Framework First | The framework builds the `ARRAY` column from `type` and `system_data_type`, as for every other type | ✅ |
| II. Official Driver Only | The query runs through the connector's engine | ✅ |
| III. IRIS Fidelity | The join gives the exact `(schema, table, column)`; `SqlFieldName` gives the exact column name | ✅ |
| IV. Least Privilege | The grant is optional; without it the connector runs no dictionary query and catalogs `VARCHAR` | ✅ |
| V. Nothing Silent | One `IRIS-VECTOR-GRANT` per run; `IRIS-VECTOR-PARAMS` per bad column; the inherited-property and view limits are in the docs note | ✅ |
| VI. Tested on the Matrix | Fixture VECTOR columns; integration tests branch on `has_dict_grant` on every cell | ✅ |
| VII. Upstream-Ready | Code inside `.om/`, `make py_format`, license headers | ✅ |
| VIII. English Artifacts | ✅ | ✅ |
| Workflow: spikes reviewed first | SPIKE-03 reviewed and its decisions agreed on 2026-11-26 | ✅ |

**Post-design re-check**: unchanged. One open check, the UI rendering (R5), needs an OpenMetadata
server; it does not gate the matrix.

## Project Structure

### Documentation (this feature)

```text
specs/004-vector-enrichment/
├── plan.md               # this file
├── research.md           # SPIKE-03 (R1), one-query join (R2), element types (R3), hook (R4), UI (R5)
├── data-model.md         # VECTOR property, facts, element rows, hint, fixture v4
├── quickstart.md         # the "VECTOR columns" docs note and how to check the feature
├── contracts/
│   └── vector-warnings.md   # IRIS-VECTOR-GRANT and IRIS-VECTOR-PARAMS
├── checklists/requirements.md
└── tasks.md              # /speckit-tasks
```

### Source code

```text
# OpenMetadata tree (overlay/, edited in .om/, Collate Community License header)
overlay/ingestion/src/metadata/ingestion/source/database/iris/
├── queries.py       # + section 004: IRIS_VECTOR_COLUMNS
├── types.py         # + section 004: VECTOR_ELEMENT_TYPES, VectorFacts, parse_vector_parameters(),
│                    #   resolve_vector(), native branch, vector_grant_message(), vector_params_message()
└── metadata.py      # + section 004: enrich_vector_columns(), the per-run cache and hint;
                     #   one call in _get_columns_internal after 003's
overlay/ingestion/tests/unit/topology/database/test_iris_vector.py   # new
overlay/ingestion/tests/integration/iris/test_vector.py              # new
overlay/ingestion/tests/integration/iris/test_types.py               # Vec assertion → test_vector.py
overlay/ingestion/tests/integration/iris/data/seed.py                # catalog v4: Vec4, vec_low

# Dev-repo files
fixtures/iris/test_seed.py
GAP-REPORT.md                                  # GAP-001, GAP-002
docs/adr/0007-vector-optional-enrichment.md    # Accepted, with evidence
```

**Structure Decision**: parsing and resolving are pure functions in `types.py`, next to spec 003's
table (ADR-0006: one type module). `metadata.py` holds only the run state (cache, hint) and the
call.

## Build order

1. Fixture columns (catalog v4) with the self-check.
2. Unit tests for the parser, resolver, native branch and per-run behavior (seen failing).
3. `IRIS_VECTOR_COLUMNS`, the `types.py` section, `enrich_vector_columns` and the call site.
4. Integration tests; nine local cells.
5. ADR-0007, GAP-001/002, docs note, contracts. UI check when a server is available.

## Dependencies

- **Spec 003**: `resolve()`, `map_column_types` and the column hook.
- **Spec 005**: fixture catalog v3 (this spec takes v4) and the guard test (the hint handler warns).
- **Spec 000**: the ADR-0015 preset and the `GetClassDictionary` step, whose message already names
  `PropertyDefinition`.
- **Spec 008** takes the docs note and does the UI screenshots.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Built on unmerged specs (003, 005) | The column hook and the fixture version come from them | Branching from 003 would collide with 005 on the fixture version and on the same call site |
