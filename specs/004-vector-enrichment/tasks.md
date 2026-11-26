# Tasks: VECTOR enrichment

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: required (constitution VI). Tests are written first and seen failing.

**Order** (from the demand): research from SPIKE-03 → representation (ADR-0007) → fixture columns →
query constant → probe and cache → enrichment → warnings → tests → GAP updates → docs note.

**Paths**: OpenMetadata files are edited in `.om/` and committed from `overlay/` after
`make om-export` (`make om-check` must stay clean). Connector tests run from `.om/ingestion`.

## Phase 1: Setup

- [ ] T001 Rebuild `.om/` on this branch (`OM_SKIP_UI_CODEGEN=1 make om-import`, `uv` on `PATH`) and confirm the unit tests of specs 002, 003 and 005 pass

## Phase 2: Foundational — fixture catalog v4 (blocks US1, US2)

- [ ] T002 Add to `fixtures/iris/test_seed.py` the expectations of catalog v4 (data-model "Fixture catalog v4"):
  - `CATALOG_VERSION == 4`, history 1–4;
  - `AI.Embedding` columns with `Vec4` and `vec_low` (`varchar`);
  - `EXPECTED["vectors"]`.

  Run against `latest-em` and see it fail
- [ ] T003 Extend `.om/ingestion/tests/integration/iris/data/seed.py`:
  - `Vec4 VECTOR(INT, 4)` and `"vec_low" VECTOR(FLOAT, 2)` in the `AI.Embedding` DDL, with values in its row (`TO_VECTOR(?, INT)`, `TO_VECTOR(?, FLOAT)`);
  - `EXPECTED` columns and `"vectors"`;
  - version 4 with its history line.

  Makes T002 pass
- [ ] T004 Run the loader twice on the three tracks (`FIXTURES OK v4`), `pytest fixtures` on each, and the existing integration tests as `reader` (no regression; spec 003's `test_types.py` still sees `Vec` as `VARCHAR(1037)` until T012)

## Phase 3: User Story 1 — VECTOR columns show element type and dimension (P1)

### Tests

- [ ] T005 [P] [US1] Write `.om/ingestion/tests/unit/topology/database/test_iris_vector.py` (license header), pure functions:
  - `parse_vector_parameters`:
    - `DATATYPE,DOUBLE,LEN,3` → `(DOUBLE, 3)`;
    - `CompiledProperty`-style strings with extra pairs;
    - lower-case keys and values;
    - `INTEGER` → `INT`;
    - missing `LEN`, `LEN,0`, `LEN,abc`, missing `DATATYPE`, odd number of items → `None`.
  - `resolve_vector`, for each element row:
    - `ColumnTypeParser.get_column_type(type) == "ARRAY"`;
    - the framework's `arrayDataType` for the element (as `SqlColumnHandlerMixin` computes it) equals the row;
    - display `VECTOR(<TYPE>, <dim>)`;
    - an unknown element gives `UNKNOWN`.
  - The element table's keys equal an explicit list.
- [ ] T006 [P] [US1] In the same file, source-level tests with spec 002's stub pattern:
  - `enrich_vector_columns` replaces `type` and `system_data_type` only for the cached `(schema, table, column)`;
  - it leaves other columns and other keys untouched;
  - it matches exact case and schema (same table name in two schemas);
  - the dictionary query runs once for many tables (count statements on the stub).

### Implementation

- [ ] T007 [US1] Add `IRIS_VECTOR_COLUMNS` (research R2) to `.om/…/iris/queries.py`, section `--- 004 ---`
- [ ] T008 [US1] Implement in `.om/…/iris/types.py`, section `--- 004: VECTOR enrichment ---`:
  - `VECTOR_ELEMENT_TYPES` and `VectorFacts`;
  - `parse_vector_parameters()`;
  - `resolve_vector()`, which returns spec 003's `ResolvedType` with `sqlalchemy.ARRAY(<element type>)`.

  Makes T005 pass
- [ ] T009 [US1] Implement in `.om/…/iris/metadata.py`, section `--- 004 ---`:
  - `_vector_columns()`, the per-run cache: no query when `engine.dialect._dictionary_access is False`; one query otherwise; on `SQLAlchemyError`, mark it unavailable with the reason;
  - `enrich_vector_columns(schema, table, columns)`.

  Add one line, `self.enrich_vector_columns(schema_name, table_name, columns)`, after 003's call in `_get_columns_internal`. Makes T006 pass

## Phase 4: User Story 2 — Without the grant, one hint (P1)

- [ ] T010 [P] [US2] Unit tests in `test_iris_vector.py`:
  - `_dictionary_access is False` → no query, one `IRIS-VECTOR-GRANT` keyed on the Database FQN naming the login, on the first `varchar` column, and none for a table with no `varchar` column;
  - a failing query → one hint with the reason's first line;
  - many tables → still one hint;
  - a new source → hint again;
  - no password in the message;
  - spec 005's guard test still passes.
- [ ] T011 [US2] Implement the hint (`vector_grant_message()` in `types.py`, recorded from `enrich_vector_columns`). Makes T010 pass

## Phase 5: Integration (US1, US2)

- [ ] T012 [US1] [US2] Write `.om/ingestion/tests/integration/iris/test_vector.py` (marked `iris`), with the `source` fixture pattern of `test_types.py`. Branch on `iris_cell.has_dict_grant`:
  - granted: the three columns as data-model; no hint;
  - not granted: `VARCHAR` with lengths 1037, 83, 691; exactly one hint after reading every `READER_SCHEMAS` table.

  For every login, the non-VECTOR columns of `AI.Embedding` are as spec 003 gives. Move spec 003's `Vec` assertion in `test_types.py` here (it branches now)
- [ ] T013 [US1] Run unit and integration tests on the nine local cells; record counts and the dictionary query time in research.md "Implementation measurements"

## Phase 6: User Story 3 — Odd dictionary values (P2)

- [ ] T014 [P] [US3] Unit tests:
  - unusable parameters → one `IRIS-VECTOR-PARAMS` per column, keyed on the column FQN, with the raw text; the column stays as spec 003 gave it;
  - an unknown element → `ARRAY` of `UNKNOWN` plus one warning;
  - the same column twice in a run → one warning.
- [ ] T015 [US3] Implement `vector_params_message()` and the two warning paths. Makes T014 pass

## Phase 7: User Story 4 — Native metadata wins (P3)

- [ ] T016 [P] [US4] Unit tests with a mocked catalog row whose `DATA_TYPE` names VECTOR (`vector`, and `VECTOR(DOUBLE, 3)` as text):
  - `ARRAY`, element and dimension from the text when present, else `UNKNOWN`;
  - display is the catalog text;
  - no `IRIS-UNKNOWN-TYPE`;
  - the enrichment skips the column;
  - no hint when no other `varchar` column was read.
- [ ] T017 [US4] Implement the native branch in `types.py` section 004, consulted by spec 003's `resolve()` before its table lookup (one call, no change to the 15 rows). Makes T016 pass

## Phase 8: Polish and cross-cutting

- [ ] T018 Update `docs/adr/0007-vector-optional-enrichment.md`:
  - status plain *Accepted*;
  - grant `%Dictionary.PropertyDefinition`, with SPIKE-03's evidence;
  - one query per run joined on `CLASSNAME`;
  - representation and its framework evidence; the UI check pending a server (research R5);
  - validation with the three fixture columns.
- [ ] T019 Update `GAP-REPORT.md`:
  - GAP-001: connector behavior and the workaround name `PropertyDefinition`;
  - GAP-002: title, reproduction (`SELECT Type, Parameters FROM %Dictionary.PropertyDefinition WHERE parent = 'AI.Embedding' AND Name = 'Vec'`), actual and workaround; tracks rechecked on all three.

  `pytest fixtures/iris/test_gap_report.py` passes
- [ ] T020 Point spec 005's grants table (`specs/005-least-privilege/quickstart.md`, VECTOR row) at this spec's docs note, and mark the row confirmed
- [ ] T021 [P] Prepare the planning-repository contract changes on a local branch `contracts/004-vector-enrichment`:
  - `docs/contracts/warnings.md`: the `IRIS-VECTOR-GRANT` text becomes the conditional text of [contracts/vector-warnings.md](contracts/vector-warnings.md), naming `PropertyDefinition`, emitted only when the dictionary check fails; `IRIS-VECTOR-PARAMS` gains the unknown-element text;
  - `docs/contracts/type-mapping.md`: the VECTOR element table and the join;
  - `docs/contracts/fixtures.md`: catalog v4, the two columns, the 004 planned-additions row done;
  - `docs/contracts/test-connection.md`: drop the "SPIKE-03 may add `CompiledProperty`" sentence.

  Push only with the user's go-ahead
- [ ] T022 UI check (quickstart step 3) when an OpenMetadata server built from the overlay is available; screenshot and result into ADR-0007. If no server is available before review, leave this task open and say so in the PR
- [ ] T023 `make py_format` on touched OpenMetadata files, `make om-export`, `make om-check` (no diff), ruff on dev-repo files; `pytest fixtures` passes

## Dependencies

- T001 → everything.
- T002 → T003 → T004 → T012–T013.
- T005/T006 → T007 → T008 → T009 → T010 → T011.
- T014 → T015; T016 → T017 (both after T008).
- T018–T023 last; T021 any time after T003.

## Parallel opportunities

```text
After T001:  T002 ∥ T005 ∥ T006 (different files or test-only)
After T009:  T010 ∥ T014 ∥ T016
After T013:  T018 ∥ T019 ∥ T020 ∥ T021
```

## Notes

- Built on spec 005, which is built on 003. When they rebase or merge, rebase this branch. The
  shared line is the call list in `_get_columns_internal` (003, then 004); spec 005 calls its
  readability check from `get_columns_and_constraints` instead. The fixture catalog goes v2 (003),
  v3 (005), v4 (004).
- First cut inside the MVP: if it is parked, spec 003's `VARCHAR` stays, and GAP-001 and GAP-002
  say why.
- Nothing in this spec is pushed without the user's go-ahead.
