# Tasks: Least privilege and access-gap reporting

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: required (constitution VI). Tests are written first and seen failing.

**Order** (from the demand): research from SPIKE-03 → fixture `Restricted` → helper audit and
hardening → tests → grants table → GAP-003 and ADR-0008 updates.

**Paths**: OpenMetadata files are edited in `.om/` and committed from `overlay/` after
`make om-export` (`make om-check` must stay clean). Connector tests run from `.om/ingestion`.

## Phase 1: Setup

- [ ] T001 Rebuild `.om/` on this branch (`OM_SKIP_UI_CODEGEN=1 make om-import`, with `uv` on `PATH`) and confirm specs 002 and 003 unit tests pass: `cd .om/ingestion && ../env/bin/python -m pytest tests/unit/topology/database/test_iris.py tests/unit/topology/database/test_iris_types.py -q`

## Phase 2: Foundational — fixture `Restricted` (blocks US1, US2)

- [ ] T002 Add to `fixtures/iris/test_seed.py` the expectations of catalog v3 (data-model "Restricted fixtures"): `CATALOG_VERSION == 3`, `VERSION_HISTORY` has 1–3, the three tables in `EXPECTED`, and per reader: listed tables in `Restricted` are `["ColumnGrant", "Secret"]`, `SELECT TOP 1 *` refused with -99 on all three, `SELECT TOP 1 Id FROM Restricted.ColumnGrant` reads. Run against `latest-em` and see it fail
- [ ] T003 Extend `.om/ingestion/tests/integration/iris/data/seed.py`:
  - `CATALOG_VERSION = 3` with its history line;
  - DDL, one row each and the drop order for `Restricted.Secret`, `Restricted.ColumnGrant`, `Restricted.Hidden`;
  - grants: `GRANT REFERENCES ON Restricted.Secret` and `GRANT SELECT (Id) ON Restricted.ColumnGrant`, one statement per reader (a column grant takes one grantee);
  - `EXPECTED` objects, columns, constraints, rows, and `"restricted"`;
  - check C11 in `_check_readers`.

  Makes T002 pass. `READER_SCHEMAS` stays as it is
- [ ] T004 In `.om/ingestion/tests/integration/iris/test_types.py`, keep `test_the_fixtures_give_no_unknown_type_warning` to `READER_SCHEMAS` (imported from the loader) instead of skipping `Scratch` by name
- [ ] T005 Run the loader twice on `latest-em`, `latest-cd`, `latest-preview` (`FIXTURES OK v3`), `pytest fixtures` on each, and the existing integration tests as `reader` on `latest-em` (no regression from the new schema)

## Phase 3: User Story 2 — What cannot be read is reported (P1)

### Tests

- [ ] T006 [P] [US2] Write `.om/ingestion/tests/unit/topology/database/test_iris_access.py` (license header), with spec 002's stub pattern (`IrisSource.__new__`, stub inspector and connection). For each read of data-model "Features" (`tables`, `views`, `columns` ×2, `keys` ×3, `description`, `view definition`, `data`), make the read raise `OperationalError` with a two-line message containing a password-like string. Assert:
  - exactly one status warning with the right key (table or schema FQN) and the prefix `IRIS-ACCESS: cannot read <feature> of <Schema>[.<Table>]: `;
  - only the first line of the message, and not the password-like string;
  - the method returns its empty value and does not raise;
  - nothing is only logged (`caplog` holds no error record without a matching warning).
- [ ] T007 [P] [US2] In the same file:
  - keys failing in all three steps give one `keys` warning;
  - the same table failing `data` twice in one run gives one warning;
  - a new source (new run) warns again;
  - a non-`SQLAlchemyError` exception from a read propagates (a bug, not an access gap);
  - `check_readable` quotes mixed-case and dotted names with the dialect's preparer (`"Sql_Name"."Odd"`)

### Implementation

- [ ] T008 [US2] Add `IRIS_READ_PROBE = "SELECT TOP 0 * FROM {schema}.{table}"` to `.om/…/iris/queries.py`, section `--- 005: access gaps ---`, with a comment pointing to research R2
- [ ] T009 [US2] Add the section `--- 005: access gaps ---` to `.om/…/iris/metadata.py`:
  - `_schema_fqn(schema)`;
  - `query_table_names_and_types` and `query_view_names_and_types`, each calling `super()` inside `report_access_gap(<schema FQN>, "tables"|"views", schema, schema)` and returning `[]` on failure; the message must read `of <Schema>`, not `of <Schema>.<Schema>`, so give the helper an optional display name or build the schema message accordingly (contract "Key and text");
  - `check_readable(schema, table)`: the quoted probe inside `report_access_gap(<table FQN>, "data", …)`, closing its result.

  Add one line, `self.check_readable(schema_name, table_name)`, after 003's call in `_get_columns_internal`. Makes T006–T007 pass
- [ ] T010 [US2] Check that spec 002's unit tests (`test_iris.py`) still pass with the extra statement. Their `_Connection` stub answers every statement; adjust only if it breaks, and note it for spec 002's owner

### Integration

- [ ] T011 [US2] Write `.om/ingestion/tests/integration/iris/test_access.py` (marked `iris`), with the `source` fixture pattern of `test_types.py`. Drive schema `Restricted` as the framework does: `get_tables_name_and_type`, then `get_columns_and_constraints` and `get_table_description` for each listed table. Assert per login (data-model "Expected warnings per cell"):
  - readers: exactly two warnings, `data` for `Restricted.Secret` and `Restricted.ColumnGrant`; `Hidden` not listed; `Secret` has 3 columns; `ColumnGrant` has `Id` only;
  - admin: no warning, three tables, `ColumnGrant` has 2 columns.
- [ ] T012 [US2] In the same file, drive every readable fixture table and view (`READER_SCHEMAS`) the same way and assert no `IRIS-ACCESS` warning, for every login
- [ ] T013 [US2] Run unit and integration tests on the nine local cells (3 tracks × 3 logins); record counts and timings in research.md "Implementation measurements"

## Phase 4: User Story 3 — No silent path (P2)

- [ ] T014 [P] [US3] Write `.om/ingestion/tests/unit/topology/database/test_iris_access_guard.py` (research R5). Parse every `.py` file of `iris/` with `ast`. Each `except` handler, and each `contextlib.suppress` (as a call or in a `with`), must contain a `raise` or a call whose attribute chain ends in `status.warning`, or be listed in `ALLOWED = {(file, function): reason}` (data-model "Guard allow list"). On failure, list `file:line` of each offender. Self-tests: a snippet with `except SQLAlchemyError: logger.debug(...)` fails, one with `self.status.warning(...)` passes, an allow-listed one passes, and an allow-list entry that matches nothing fails (no stale entries)
- [ ] T015 [US3] Run the guard on the real package; it passes with the single `connection.py` entry. Then run quickstart step 3 by hand: an injected silent handler fails, and undo it

## Phase 5: User Story 1 — An ordinary login ingests everything it can read (P1)

- [ ] T016 [US1] Confirm on the nine cells that the whole suite passes as `reader` and `reader_dict` with the same expectations as `admin` for `READER_SCHEMAS`. VECTOR detail apart: spec 004 has not landed, so `AI.Embedding.Vec` is `VARCHAR` for every login. Record it in research.md

## Phase 6: User Story 4 — The grants table (P2)

- [ ] T017 [US4] Check every statement of quickstart "Minimal grants" against the fixtures' reader setup (`CREATE USER … IDENTIFIED BY`, `GRANT SELECT ON SCHEMA`, the dictionary grant), and the "What administrators should know" examples against research R1 and R4. The table-level `REVOKE` example is reproduced once on `latest-em` with a throwaway login and schema, then removed

## Phase 7: Polish and cross-cutting

- [ ] T018 Update `GAP-REPORT.md` GAP-003 (FR-014):
  - IRIS tracks checked on all three;
  - a reproduction as `omd_reader`: `SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'Restricted'` lists `ColumnGrant` and `Secret`, never `Hidden`;
  - actual behavior from SPIKE-03 (no privilege views; detection only with `%Dictionary.CompiledClass`);
  - connector behavior: documented limitation; visible-but-unreadable objects are reported (`data`).

  `pytest fixtures/iris/test_gap_report.py` passes
- [ ] T019 Update `docs/adr/0008-access-gaps-as-warnings.md` (FR-013), dated "Revised":
  - the decision adds the readability check (`data`) and the schema listing (`tables`, `views`);
  - invisible objects: SPIKE-03's evidence and the 2026-11-26 decision to keep the limitation;
  - validation: `GRANT REFERENCES` on `Restricted.Secret` instead of a revoke, one warning per restricted table, the run completes
- [ ] T020 [P] Prepare the planning-repository contract changes on a local branch `contracts/005-least-privilege` (from its `main`):
  - `docs/contracts/warnings.md`: features `data`, `tables`, `views`, and the schema key;
  - `docs/contracts/fixtures.md`: catalog v3, the `Restricted` rows and grants, the planned-additions row for 005 marked done, the reader rows.

  Push only with the user's go-ahead
- [ ] T021 `make py_format` on touched OpenMetadata files, `make om-export`, `make om-check` (no diff), and ruff on the dev-repo files; `pytest fixtures` passes (the gap-report check needs spec 001's `not applicable` change, present once this branch is rebased on it)

## Dependencies

- T001 → everything.
- T002 → T003 → T004 → T005 (fixture) → T011–T013, T016.
- T006/T007 → T008 → T009 → T010.
- T014 → T015 (needs T009 for the real package).
- T017–T021 last; T020 any time after T003.

## Parallel opportunities

```text
After T001:  T002 ∥ T006 ∥ T007 ∥ T014 (different files or test-only)
After T009:  T011 ∥ T015 ∥ T017
After T013:  T018 ∥ T019 ∥ T020
```

## Notes

- Built on spec 003 (plan, Dependencies). When 003 rebases or merges, rebase this branch; the only
  shared line is the call in `_get_columns_internal`.
- The readability check (FR-005) goes beyond the demand's text; the spec's checklist notes it for
  Henry's review.
- Nothing in this spec is pushed without the user's go-ahead.
