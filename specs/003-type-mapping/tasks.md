# Tasks: Type mapping

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: required (constitution VI). Tests are written first and seen failing.

**Order** (from the type-map plan): discovery on 3 tracks → fixture `Types.AllTypes` → map and
registration → unknown warning → Markdown renderer → tests → contract update.

**Paths**: OpenMetadata files are edited in `.om/` and committed from `overlay/` after
`make om-export` (`make om-check` must stay clean). Connector tests run from `.om/ingestion`.

## Phase 1: Setup

- [X] T001 Rebuild `.om/` on this branch (`OM_SKIP_UI_CODEGEN=1 make om-import`; FORCE=1 only after checking the diff is spec 002's files) and confirm spec 002's unit tests pass: `cd .om/ingestion && ../env/bin/python -m pytest tests/unit/topology/database/test_iris.py -q`
- [ ] T002 [P] Write `fixtures/iris/discover_types.py` (research R1): create one `Scratch` table per candidate DDL type, record what `INFORMATION_SCHEMA.COLUMNS` reports, drop it, then collect every distinct `DATA_TYPE` of the Namespace. `--check` (run with `.om/env/bin/python`) exits 1 and names any value missing from `IRIS_TYPES`. It never leaves a table behind

## Phase 2: Foundational — fixture `Types.AllTypes` (blocks US1 and US3)

- [X] T003 Add to `fixtures/iris/test_seed.py` the expectations of catalog v2 (`Types.AllTypes` in `EXPECTED`, `CATALOG_VERSION == 2`, both readers can read it); run against `latest-em` and see it fail
- [X] T004 Extend `.om/ingestion/tests/integration/iris/data/seed.py` (data-model, "Fixture catalog v2"): `CATALOG_VERSION = 2` with a history line; schema `Types` and `Types.AllTypes` in `DDL` and in the drop order; one row in `ROWS`; `Types` in `READER_SCHEMAS`; `EXPECTED` objects, columns with `DATA_TYPE`, primary key, row count and reader tables. Makes T003 pass
- [X] T005 Run the loader twice on `latest-em`, `latest-cd`, `latest-preview` (`FIXTURES OK v2`), `pytest fixtures` on each, and spec 001's and 002's integration tests on `latest-em` as `reader` (no regression from the new schema)

## Phase 3: User Story 1 — Columns show the right type (P1)

### Tests

- [ ] T006 [P] [US1] Write `.om/ingestion/tests/unit/topology/database/test_iris_types.py` (license header):
  - the table's keys equal an explicit list of the 15 values (research R4);
  - per row (parametrized from `IRIS_TYPES`): `ColumnTypeParser.get_column_type(resolve(facts).sqlalchemy_type) == row.data_type.value`; length rows carry the length (`_check_col_length`), the numeric row carries `(p, s)` (`check_col_precision`); `display` is as in research R4;
  - matching is case-insensitive (`VARCHAR`, `varchar`);
  - `varchar` with length 1 stays `VARCHAR` with length 1;
  - `longvarchar` with length 2147483647 is `TEXT` with display `LONGVARCHAR`;
  - an unmapped value gives `known = False`, `UNKNOWN`, display = upper-case raw value
- [ ] T007 [P] [US1] Write the source-level unit tests in the same file, with spec 002's stub pattern (`IrisSource.__new__`, stub connection returning catalog rows): `map_column_types` sets `type` and `system_data_type` on each column from the row of the same column name; it keys the query on `(schema, table)`; a column with no catalog row keeps the dialect's type; names, order, descriptions and every other key of the dict are untouched; a failing type query records one `IRIS-ACCESS` warning for `columns` and leaves the columns as they were

### Implementation

- [ ] T008 [US1] Implement in `.om/…/iris/types.py`, section `--- 003: type map ---`: `IrisTypeRow`, `IRIS_TYPES` (research R4, with `ddl` examples and notes), `ColumnFacts`, `ResolvedType`, `IrisUnmappedType`, `resolve()`. Makes T006 pass
- [ ] T009 [US1] Add `IRIS_COLUMN_TYPES` to `.om/…/iris/queries.py` (`COLUMN_NAME`, `DATA_TYPE`, `CHARACTER_MAXIMUM_LENGTH`, `NUMERIC_PRECISION`, `NUMERIC_SCALE` from `INFORMATION_SCHEMA.COLUMNS`, bound on `:schema` and `:table`)
- [ ] T010 [US1] Add section `# --- 003: type map ---` to `.om/…/iris/metadata.py` with `map_column_types(schema_name, table_name, columns)` (query inside `report_access_gap(..., "columns", ...)`), and the one call at the end of spec 002's `_get_columns_internal`. Makes T007 pass

## Phase 4: User Story 2 — An unknown type never breaks a run (P1)

### Tests

- [ ] T011 [P] [US2] Unit tests in `test_iris_types.py`: `UnknownTypes.first` is true once per type (case-insensitive) and keeps the first column; `map_column_types` with three columns of one unmapped type in two tables gives one warning keyed `iris_test.USER` with the contract text; two unmapped types give two warnings; a new source instance warns again; mapped types give none

### Implementation

- [ ] T012 [US2] Implement `UnknownTypes` and `unknown_type_message()` in `types.py`, and the warning in `map_column_types` (key: Database FQN). Makes T011 pass

## Phase 5: User Story 3 — Every mapping is tested on every track (P2)

- [ ] T013 [US3] Write `.om/ingestion/tests/integration/iris/test_types.py` (marker `iris`, conftest fixtures, a source built as in spec 002's Part A from `iris_service_connection`):
  - every column of `Types.AllTypes` has the data type, length, precision, scale and display of data-model's table;
  - `Clinic.Encounter.Notes` is `TEXT` / `LONGVARCHAR`; `AI.Embedding.Vec` is `VARCHAR` (1037); `Clinic.Patient.Weight` is `NUMERIC` (5, 2); the view `Clinic.ActivePatient` is mapped too;
  - no `IRIS-UNKNOWN-TYPE` warning after reading every fixture table;
  - with the `numeric` row removed for the test (monkeypatch), reading `Types.AllTypes` and `Clinic.Patient` gives one warning and both `numeric` columns are `UNKNOWN`
- [ ] T014 [US3] Run `test_types.py` and spec 002's Part A on all three tracks × three logins locally (`make test-cell`, ports 11972/11974/11975); `discover_types.py --check` on each track

## Phase 6: User Story 4 — The docs table comes from the mapping (P3)

- [ ] T015 [P] [US4] Unit test: `render_markdown_table()` has one row per `IRIS_TYPES` entry in key order with the header of contracts/type-mapping.md; the text between the markers of `specs/003-type-mapping/contracts/type-mapping.md` equals a fresh rendering (the test says how to regenerate)
- [ ] T016 [US4] Implement `render_markdown_table()` and a `__main__` that prints it; generate the table into `contracts/type-mapping.md`. Makes T015 pass

## Phase 7: Polish

- [ ] T017 Update `docs/adr/0006-single-type-map.md` (FR-015): replace the starting table with the 15-row decision and a link to the generated table; correct the GAP-008 sentence (the `LONGVARCHAR` half is OpenMetadata's `ColumnTypeParser`); note that the raw catalog is read because registering in `ischema_names` cannot fix GAP-008 nor keep an unknown type's name; dated "Revised" in the status line
- [ ] T018 `make py_format`-equivalent: ruff format and check (OpenMetadata's config) on the touched files only; `scripts/check_ruff_suppressions.py --check`; then `make om-export` and `make om-check` twice
- [ ] T019 Run quickstart Q1–Q6; tick the checklist; record in research.md the test counts per track
- [ ] T020 Prepare the contract changes for the planning repository on a local branch (type mapping table generated, fixtures `Types.AllTypes`, warnings row unchanged); push only with the user's go-ahead

## Dependencies

- T001 → everything. T002 any time after T001.
- T003 → T004 → T005 (fixture) → T013/T014.
- T006/T007 → T008 → T009 → T010. T011 → T012 (needs T010).
- T015 → T016. T017–T020 last.

## Parallel opportunities

```text
After T001:  T002 ∥ T003 ∥ T006 ∥ T011 ∥ T015 (different files or test-only)
After T010:  T012 ∥ T016 ∥ T017
```

## Notes

- Built on spec 002 applied locally on 001 (plan, Dependencies). When 002 is rebased on 001 and
  pushed, rebase this branch on it; the only shared line is the call in `_get_columns_internal`.
- Nothing in this spec is pushed without the user's go-ahead.
