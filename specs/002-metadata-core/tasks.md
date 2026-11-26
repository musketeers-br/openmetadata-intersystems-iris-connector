---

description: "Task list for metadata core ingestion"
---

# Tasks: Metadata Core Ingestion

**Input**: Design documents from `/specs/002-metadata-core/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/access-gap-helper.md, contracts/catalog-facts.md, quickstart.md

**Tests**: REQUIRED (Constitution VI). Integration tests assert the "Expected OpenMetadata entities" table of the shared fixtures (spec 001) using `iris_cell` / `iris_service_connection`, run in-process with a test sink or against a local OpenMetadata, as spec 000 established.

**Organization**: grouped by user story, in the requested order: research → access-gap helper (own PR) → catalog hooks → keys → descriptions → view definitions → view lineage → filters → mark deleted / override tests → regression tests. Work happens inside `.om/` (`make om-import`); only `overlay/` and `patches/` are committed after `make om-export`, and only when the developer asks.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 hierarchy and columns, US2 keys / descriptions / view definitions, US3 view lineage, US4 filters, US5 re-runs (mark deleted, override), US6 access gaps

Shorthand (relative to `.om/` while working, `overlay/` once exported):

- `PKG` = `ingestion/src/metadata/ingestion/source/database/iris/`
- `UNIT` = `ingestion/tests/unit/topology/database/test_iris.py`
- `INTEG` = `ingestion/tests/integration/iris/test_metadata_core.py`

Cells: "all" = every matrix cell (track × login `admin`/`reader`); "admin" = admin login only.

---

## Phase 1: Setup — evidence first

**Gate**: steps marked ⛔ in later phases MUST NOT start until T002 confirms research.md.

- [X] T001 Look for an earlier spike result on inspector vs `INFORMATION_SCHEMA` and record in `specs/002-metadata-core/research.md` the confirmed source per fact (inspector method or `INFORMATION_SCHEMA` view, and why) in the fact-by-fact table. If there is none, say so in research.md and continue with T002
- [X] T002 For every fact still unconfirmed, compare the dialect inspector (`get_schema_names`, `get_table_names`, `get_view_names`, `get_columns`, `get_pk_constraint`, `get_foreign_keys`, `get_unique_constraints`, `get_view_definition`, `get_table_comment`) with `INFORMATION_SCHEMA` (`TABLES`, `COLUMNS`, `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE`, `REFERENTIAL_CONSTRAINTS`, `VIEWS`) on the fixture objects, on `latest-em`, `latest-cd`, `latest-preview`, as `admin` and `reader`; fill the "Confirmed" column and the `DATA_TYPE` list for spec 003 in `specs/002-metadata-core/research.md`; record whether generated/deprecated classes are name-expressible. Reproduce each inspector failure for the Gap Report (T029)
- [X] T003 [P] Run `make om-import` and confirm the spec 000 unit and connection integration tests pass in `.om/` before changes (baseline)

---

## Phase 2: Foundational — access-gap helper (own PR)

**Purpose**: `report_access_gap` is needed by every story and by spec 005 (due Dec 2). Ship it alone: its own commit/PR, nothing else in it.

- [X] T004 Add `report_access_gap(self, fqn, feature, schema, name)` context manager to `IrisSource` in `PKG/metadata.py` under `# --- 002: catalog ---`, exactly as `specs/002-metadata-core/contracts/access-gap-helper.md`: catch database errors, call `self.status.warning(fqn, "IRIS-ACCESS: cannot read <feature> of <schema>.<name>: <first line of error>")`, never re-raise database errors, let other exceptions propagate, no credentials in the message
- [X] T005 [P] Unit tests `Test002AccessGap` in `UNIT`: warning recorded with exact key and `IRIS-ACCESS:` prefix; only the first line of a multi-line error; run continues after the block; non-database exception propagates; password string never appears
- [X] T006 Run `make py_format` on touched files, `make om-export`, verify only `overlay/`/`patches/` change for this helper; hand the helper to the developer as its own commit/PR (do not commit unless asked)

**Checkpoint**: helper available; spec 005 can start.

---

## Phase 3: User Story 1 - Ingest the structure of a Namespace (Priority: P1) 🎯 MVP

**Goal**: Database → Database Schemas → tables/views with type → columns, case exact, same-name tables separate.

**Independent Test**: ingest the fixtures; hierarchy, FQNs, column counts and case match the fixtures contract.

- [X] T007 ⛔ [US1] Add the catalog constants research.md marks as "catalog" for tables, views and columns to `PKG/queries.py` under `# --- 002: catalog ---`: bind parameters, rows carry `TABLE_SCHEMA`, `TABLE_NAME` (and `COLUMN_NAME`), joins on schema AND name, no case changes
- [X] T008 ⛔ [US1] In `PKG/metadata.py` add the catalog hooks for schema, table/view and column reads (inspector by default, `queries.py` constant where research.md says so), every per-object read wrapped in `report_access_gap` (features `columns`), all internal maps keyed on `(schema, name[, column])`; types come only from the existing type map, `types.py` untouched
- [X] T009 [P] [US1] Unit tests `Test002Hierarchy` in `UNIT`: hierarchy mapping with a stubbed inspector — two tables named `Patient` in `Clinic` and `Billing` yield distinct entities with their own columns; table type (table/view) set; names unchanged in case
- [X] T010 [US1] Create `INTEG`: shared setup running the ingestion workflow for `iris_service_connection` into the test sink, plus tests (cells: all) for hierarchy and FQNs (`iris_test.USER`, `.Clinic`, `.Billing`, `.AI`, `…Clinic.Patient`, `Clinic.Encounter`, `Billing.Patient`, `AI.Embedding`, `Clinic.ActivePatient` with `tableType=View`), `Clinic.Patient` has 4 columns and `Billing.Patient` 2 (`Code`, `Balance`), case preserved (`PatientId`), and the run finishes without failure
- [X] T011 [US1] Assert in `INTEG` the column attributes from the fixtures (ordinal position, nullability of `FullName`/`PatientId` in `Clinic.Encounter`, length of `FullName` 120, precision/scale of `Weight` 5,2, default values where the fixtures define them)

**Checkpoint**: MVP; hierarchy ingests on every cell.

---

## Phase 4: User Story 2 - Keys, descriptions and view definitions (Priority: P1)

**Goal**: constraints, descriptions and view definitions as in the fixtures contract.

**Independent Test**: ingest the fixtures; keys, descriptions and the view definition match.

- [X] T012 ⛔ [US2] Keys: add the key/constraint constants research.md marks as "catalog" to `PKG/queries.py` (primary, foreign with referenced schema and table, unique; joins on schema AND name) and wire primary key, foreign keys and unique constraints in `PKG/metadata.py`, each read inside `report_access_gap` (feature `keys`); foreign keys point to the referenced table's schema, never resolved by table name alone
- [X] T013 [P] [US2] Unit tests `Test002Keys` in `UNIT`: a foreign key referencing `Patient` resolves to `Clinic.Patient` even when `Billing.Patient` exists; constraint maps keyed by `(schema, name, constraint)`
- [X] T014 [US2] Descriptions: table and column descriptions come from the inspector (`get_table_comment`, column `comment`); only the failure path is added, wrapped in `report_access_gap` (feature `description`). No catalog query was needed (T002 evidence)
- [X] T015 [US2] View definitions: add the view definition constant to `PKG/queries.py` if research.md requires it, and set the view's definition in `PKG/metadata.py` inside `report_access_gap` (feature `view definition`)
- [X] T016 [US2] In `INTEG` (cells: all) assert: PK `PatientId` on `Clinic.Patient`; PK `EncounterId` and FK `PatientId` → `iris_test.USER.Clinic.Patient` on `Clinic.Encounter`; PK `Code` and unique `UqBillingCode` on `Billing.Patient`; table description "Patients registered in the clinic" and `PatientId` description "Patient identifier"; view definition of `Clinic.ActivePatient` present for `admin`, and for `reader` either present or exactly one `IRIS-ACCESS` warning for it (assert accordingly)

**Checkpoint**: keys, descriptions, definitions on every cell.

---

## Phase 5: User Story 3 - Lineage from views to tables (Priority: P1)

**Goal**: `Clinic.ActivePatient` has lineage from `Clinic.Patient` and `Clinic.Encounter`.

**Independent Test**: ingest metadata then lineage; the view's upstream set is exactly those two tables.

- [X] T017 ⛔ [US3] Create `PKG/lineage.py` with `IrisLineageSource(LineageSource)` modeled on `.om/ingestion/src/metadata/ingestion/source/database/sqlite/lineage.py` (`create()` validates `IrisConnection`, raises `InvalidSourceException` otherwise); license header kept
- [X] T018 [US3] Register it in `PKG/service_spec.py`: `lineage_source_class=IrisLineageSource`
- [X] T019 [P] [US3] Unit tests `Test002Lineage` in `UNIT`: `create()` accepts an IRIS config and rejects another; `ServiceSpec.lineage_source_class` is `IrisLineageSource`
- [X] T020 [US3] In `INTEG` (cells: all) run the lineage step after metadata and assert `iris_test.USER.Clinic.ActivePatient` has upstream edges from `Clinic.Patient` and `Clinic.Encounter` and no others; for `reader` with an unreadable definition assert no lineage plus the warning, not a failure

**Checkpoint**: lineage works; an unparsable view is ingested without lineage.

---

## Phase 6: User Story 4 - Filters (Priority: P2)

**Goal**: system content excluded by default through patterns; include/exclude behave as in other connectors.

**Independent Test**: three runs with default, include `Clinic`, and cleared excludes.

- [X] T021 [US4] Check the defaults in `irisConnection.json` (`^%`, `^INFORMATION_SCHEMA$`, `^Ens`) against research.md; add a pattern only if T002 found a name-expressible generated/deprecated rule, in a `patches/` edit, never as Python skip logic; if the defaults change update `docs/adr/0009-exclusions-as-filter-patterns.md`
- [X] T022 [US4] In `INTEG` (cells: admin) assert: default run ingests no `%*`, `INFORMATION_SCHEMA` or `Ens*` schema; `schemaFilterPattern.includes=["^Clinic$"]` yields only `Clinic`; clearing the default excludes brings system schemas back; a `tableFilterPattern` limits tables within allowed schemas

---

## Phase 7: User Story 5 - Re-runs: mark deleted and override (Priority: P2)

**Goal**: framework options behave as specified; this phase only tests them.

**Independent Test**: ingest, drop a table, edit a description, ingest again with each option on and off.

- [X] T023 [US5] Fixtures: add the first use of the `Scratch` schema through the shared fixtures (spec 001, reviewed by the fixture owner) — done: `Scratch` has a sentinel table `Scratch.Keep` that is never dropped; tests create and drop their own table there and clean up
- [X] T024 [US5] In `INTEG` (cells: admin) create `Scratch.Tmp`, ingest, `DROP TABLE`, ingest again with `markDeletedTables` on → table deleted and others untouched; with it off → not deleted; re-created table is active again
- [X] T025 [US5] In `INTEG` (cells: admin) edit the description of `Clinic.Patient` in OpenMetadata, re-ingest with `overrideMetadata` off → edit kept; with it on → IRIS description restored

---

## Phase 8: User Story 6 - Access problems never fail the run (Priority: P1)

**Goal**: unreadable parts are warnings with the object's full name; the rest is ingested.

**Independent Test**: run as `reader` and with a failing read injected; one warning per unreadable part, run succeeds.

- [X] T026 [US6] Confirm every per-object read added in T008/T012/T014/T015 sits inside `report_access_gap` and that no other `try/except` logs an access problem; fix any that does not in `PKG/metadata.py`
- [X] T027 [P] [US6] Unit tests `Test002AccessGapIngest` in `UNIT`: a stubbed read raising a database error for one table's columns, keys, view definition and description produces exactly one warning each with the table's FQN, and the other tables are still produced
- [X] T028 [US6] In `INTEG` (cells: all) assert the run completes as `reader`, the number of `IRIS-ACCESS` warnings equals the number of unreadable parts found, each key is an object FQN, and none contains the password

---

## Phase 9: Polish, regression and cross-cutting

- [X] T029 Add one `GAP-REPORT.md` entry per confirmed inspector workaround (reproduction, tracks, connector behavior, upstream TODO) and one for views whose lineage cannot be parsed, if any were seen
- [X] T030 [P] Regression unit test `Test002IdentityRegression` in `UNIT` (ADR-0005): build the catalog maps from rows where two schemas contain the same table name and assert both survive; also assert the test fails against a name-only map (e.g. by monkeypatching the key function to return the name alone and expecting the assertion to trip)
- [X] T031 [P] Case regression in `UNIT`: mixed-case schema, table and column names round-trip through the maps unchanged
- [X] T032 Run `make py_format` on touched modules inside `.om/`, then `make om-export` and `make om-check`; confirm only intended `overlay/` and `patches/` changes
- [X] T033 Run the quickstart steps in `specs/002-metadata-core/quickstart.md` on `latest-em` locally; list the cells run and the cells left to the CI matrix (spec 001) (done on latest-em only; cd and preview left to the matrix)
- [ ] T034 Update `specs/002-metadata-core/research.md` open items and the fixtures contract notes with anything learned; ask the developer whether to commit

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → Phase 3. ⛔ tasks need T002 confirmed. T004–T006 do not, and ship as their own PR.
- US1 (Phase 3) before US2 and US3 (both read the same entities). US2 and US3 are independent of each other after US1.
- US4, US5 and US6 need US1; US6's T026 needs the reads from US2 (T012, T014, T015).
- Phase 9 last; T030/T031 may start once T008 and T012 exist.

## Parallel opportunities

- T003 with T001/T002.
- Unit-test tasks T005, T009, T013, T019, T027, T030, T031 are in one file but separate classes: write in parallel, merge sequentially.
- US2 (T012–T016) and US3 (T017–T020) after US1.
- US4 and US5 after US1.

## Implementation strategy

1. Evidence (T001–T003), then ship the helper PR (T004–T006).
2. MVP = US1: hierarchy and columns on every cell.
3. Add US2, then US3, then US6 verification; then US4 and US5.
4. Close with Gap Report entries, regression tests and the round trip.
