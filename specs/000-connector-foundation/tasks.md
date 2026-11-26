---

description: "Task list for the connector foundation"
---

# Tasks: Connector Foundation

**Input**: Design documents from `/specs/000-connector-foundation/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/make-targets.md, quickstart.md

**Tests**: REQUIRED (Constitution VI). Tests follow the implementation inside each story, per the requested order.

**Organization**: grouped by user story. OpenMetadata files are written as `overlay/<path>` (new) or `patches/<path with / as __>.patch` (edits) and are worked on inside `.om/` until exported.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 round trip, US2 service type and form, US3 Test connection, US4 YAML workflow, US5 optional extra

Shorthand used below (all relative to `.om/` while working, `overlay/` once exported):

- `PKG` = `ingestion/src/metadata/ingestion/source/database/iris/`
- `SPEC` = `openmetadata-spec/src/main/resources/json/schema/entity/services/`
- `TESTDEF` = `openmetadata-service/src/main/resources/json/data/testConnections/database/`

Requested order: Makefile → scaffold → schema + enum → `setup.py` extra → `connection.py` → `metadata.py` / `service_spec.py` → test-connection JSON → UI registration → unit tests → integration test → `om-export` → record the UI file list in research.md → README stub. Phases follow stories, so the UI registration (US2) is placed before the test-connection JSON (US3); neither depends on the other.

---

## Phase 1: Setup

- [X] T001 Add `.om/` to `.gitignore` (file already exists untracked; keep its other entries)
- [X] T002 [P] Create `openmetadata.version` containing `2.1.1`
- [X] T003 [P] Create `scripts/antlr4` wrapper that runs the pinned, checksum-verified ANTLR 4.9.2 jar in an `eclipse-temurin:21-jre` container (`docker run --rm -v "$D:$D" -w "$PWD" eclipse-temurin:21-jre java -jar <jar> "$@"`, jar downloaded from Maven Central and checked against the SHA-256 pinned in OpenMetadata's Makefile, `ANTLR_COMPLETE_JAR_SHA256`), executable, so no local JDK is needed

---

## Phase 2: User Story 1 - Rebuild and write back the tree (Priority: P1) 🎯 MVP

**Goal**: one command rebuilds `.om/`, one writes edits back, and running both changes nothing.

**Independent Test**: from a clean clone, `make om-check` exits 0 and `git status` shows no change in `overlay/` or `patches/`.

- [X] T004 [US1] Create `Makefile` with `om-import`: shallow clone `open-metadata/OpenMetadata` at the tag in `openmetadata.version` into `.om/` when missing or stale; reset tracked files; copy `overlay/` into it; `git apply` every file in `patches/`; run `uv lock`; run `make install_dev generate` in `.om/ingestion` with Python 3.11 and `scripts/antlr4` on `PATH`. Idempotent; clear message when Python 3.11, Docker or a patch fails
- [X] T005 [US1] Add `om-export` to `Makefile`: in `.om/`, `git status --porcelain`; untracked files are copied to `overlay/<same path>`, modified tracked files are written with `git diff` to `patches/<path with / as __>.patch`; generated and ignored files are never exported; a deleted tracked file is an error that writes nothing
- [X] T006 [US1] Add `om-check` to `Makefile`: `om-import`, `om-export`, then `git diff --exit-code overlay patches`
- [X] T007 [US1] Run `make om-check` on the clean repository (empty `overlay/` and `patches/`) and confirm no diff; fix the export filter and apply logic until it holds (closes research V4)
- [X] T008 [US1] Add a tooling test target or script `scripts/test-roundtrip.sh` that proves the three acceptance cases: no-op round trip, a new file captured into `overlay/`, an edited existing file captured as one patch (then reverts the sample change)

**Checkpoint**: the round trip works; nothing else can be built without it.

---

## Phase 3: Foundational (blocking prerequisites)

**Purpose**: the scaffolded connector and its registration in OpenMetadata, which every remaining story edits.

- [X] T009 Run `make om-import`, then in `.om/` run `metadata scaffold-connector --name iris --service-type database --connection-type sqlalchemy --scheme iris --default-port 1972 --auth-types basic --capabilities metadata lineage profiler`
- [X] T010 Edit `SPEC/connections/database/irisConnection.json`: add required `namespace` (default `USER`), remove `databaseName` and `databaseSchema`, keep `authType` basicAuth and `sslConfig`, set `schemaFilterPattern` default excludes to `^%`, `^INFORMATION_SCHEMA$`, `^Ens`, required `username`, `hostPort`, `namespace`
- [X] T011 Edit `SPEC/databaseService.json`: add `Iris` to `enum` and `javaEnums`, and the `irisConnection.json` `$ref` to `oneOf`
- [X] T012 Edit `ingestion/setup.py`: add `"iris": {"intersystems-irispython==5.4.1", "sqlalchemy-intersystems-iris==1.0.2"}` to `plugins`; ensure no core dependency is added
- [X] T013 Refresh `ingestion/uv.lock` with `uv lock`, run `make generate` in `.om/ingestion`; decide whether `om-import` runs `uv lock` or the repository stores `patches/ingestion__uv.lock.patch` after checking determinism twice, and record the result under research.md item V3
- [X] T014 [P] Add OpenMetadata's license header to every Python file under `PKG` and tests, and copy ingestion's LICENSE text (Collate Community License 1.0, from the pinned tag) to `overlay/ingestion/LICENSE`
- [X] T015 Checkpoint: `make om-export` then `make om-check` has no diff; commit message and trailers carry no AI attribution (done by the developer, not by these tasks)

**Checkpoint**: schema, enum and extra are registered; user stories can proceed.

---

## Phase 4: User Story 2 - Choose and configure "InterSystems IRIS" (Priority: P1)

**Goal**: IRIS is selectable with its icon, the form has the required fields, passwords are masked, and the source yields the Namespace as Database.

**Independent Test**: unit tests pass; on `make om-image` images, the service list shows IRIS with its icon and the form fields, and a saved service shows a masked password.

- [X] T016 [US2] Implement `PKG/connection.py` basics: `IrisConnection` over `BaseConnection`, its own `get_connection_url()` building `iris://user:pwd@host:port/<namespace>` (never `get_connection_url_common`), password and options helpers reused, and `get_connection()` through `create_generic_db_connection`; no credentials in logs
- [X] T017 [US2] Implement `PKG/metadata.py`: `IrisSource(CommonDbSourceService)` with `create()` validating the config type and `get_database_names()` yielding `service_connection.namespace`; never call `set_inspector()`; add section headers for later specs
- [X] T018 [P] [US2] Create `PKG/service_spec.py` with `DefaultDatabaseSpec` for `IrisSource` and `IrisConnection`
- [X] T019 [P] [US2] Create stub `PKG/queries.py` and `PKG/types.py` (`__init__.py` too) with section headers for specs 002, 003, 004, 010; no logic
- [X] T020 [US2] Close research V1: register the service in the UI (`openmetadata-ui/.../utils/DatabaseServiceUtils.tsx`, service-type constants, locale entries) following `CONNECTOR_CONTEXT.md`; list the exact files in research.md
- [X] T021 [US2] Close research V2: add the IRIS icon under the UI assets, choose one whose licence permits redistribution, and record its source and licence next to the file and in the README stub; generate the TypeScript for the connection schema (research V5) and note which generated files need export
- [X] T022 [US2] Add `om-image` to `Makefile`: from `.om/`, in Docker (Maven for `openmetadata-spec` and `openmetadata-service`, yarn for the UI) build the OpenMetadata server image and an ingestion image installing the `iris` extra
- [X] T023 [P] [US2] Unit tests in `overlay/ingestion/tests/unit/topology/database/test_iris.py`: config parses from YAML and JSON; `namespace` required; URL contains the Namespace and no `databaseSchema`; password masked in the service model and absent from log output; `IrisSource.create()` rejects a wrong config type; `get_database_names()` yields the Namespace verbatim with its case
- [X] T024 [US2] Validate on the images: run `make om-image`, start them, and check the service list, icon, form fields, masked password and default filter patterns (quickstart step 4, UI part); record results in research.md

**Checkpoint**: US2 testable on its own.

---

## Phase 5: User Story 3 - Test connection step by step (Priority: P1)

**Goal**: five separate steps with the right failure messages, optional dictionary hint, and working with SELECT-only logins.

**Independent Test**: against the IRIS Community image, `admin` passes all five steps, `reader` passes four plus the dictionary hint, and a wrong host, port, Namespace or password fails on `CheckAccess`.

- [X] T025 [US3] Edit `TESTDEF/iris.json` to the definition in `data-model.md` (name `Iris`; steps `CheckAccess`, `GetSchemas`, `GetTables`, `GetViews`, `GetClassDictionary`; replace the scaffold's `GetQueries`; the last two non-mandatory; `CheckAccess` short-circuits)
- [X] T026 [US3] In `PKG/connection.py` add the single ADR-0015 function (right after engine creation): read `SELECT $ZVERSION` through the plain driver and parse it into `engine.dialect.server_version_info`, probe `SELECT TOP 1 Name FROM %Dictionary.PropertyDefinition` for `engine.dialect._dictionary_access`; no SQL rewriting, no monkey-patching, no subclassing; comment names GAP-004 and GAP-005
- [X] T027 [US3] In `PKG/connection.py` implement `test_connection()` with `test_connection_steps(...)` and a `test_fn` map for the five steps (first schema passing the filter for tables and views; dictionary step uses the same probe as T026); the `CheckAccess` failure text tells the user to check host, port, Namespace, username and password (the driver reports a bad password as `<COMMUNICATION LINK ERROR> … Invalid Message received`); dictionary failure returns the hint naming `GRANT SELECT ON %Dictionary.PropertyDefinition TO <user>`; no credentials in any message
- [X] T028 [P] [US3] Unit tests in `test_iris.py`: `$ZVERSION` parsing for the version strings of `latest-em`, `latest-cd` and `latest-preview` with a fake DB-API connection; access probe success and failure; a test that fails when the pinned dialect version changes (so presets are re-evaluated); dictionary-step failure keeps overall success; error messages contain no password
- [X] T029 [US3] Integration test `overlay/ingestion/tests/integration/iris/test_connection.py` (marker `iris`, reading `IRIS_HOST`, `IRIS_PORT`, `IRIS_LOGIN`, `IRIS_NAMESPACE` as in ADR-0012; `IRIS_LOGIN` ∈ `admin`, `reader`, `reader_dict`): the five steps per the expected-results table in `data-model.md` for each login; branch on login for the dictionary expectation, never skip silently; locally run `latest-em` × `admin`, `reader`, `reader_dict` (all nine cells once spec 001 lands)
- [X] T030 [US3] Add to the same file the negative cases (as `reader`): wrong password, host, port and Namespace each fail on `CheckAccess` with the clear message and no later step passes
- [X] T031 [US3] Validate in the UI on the images: Test connection as `admin` and `reader`, and with a wrong password (quickstart step 4); record results in research.md
- [ ] T032 [US3] Append GAP-004 (Native API on connect) and GAP-005 (`%CHECKPRIV` probe always true) to `GAP-REPORT.md` with reproductions from SPIKE-01, and open the upstream issues; record the issue links in the file and in research.md

**Checkpoint**: US3 testable on its own.

---

## Phase 6: User Story 4 - YAML workflow (Priority: P2)

**Goal**: the same fields run from a YAML workflow and create the service and Database.

**Independent Test**: the workflow creates service `iris_test` and Database `USER` as `admin`, with no credentials in logs.

- [X] T033 [US4] Add a workflow integration test in `overlay/ingestion/tests/integration/iris/test_connection.py` (or a sibling `test_workflow.py`): load a YAML workflow (`source.type: iris`, `serviceName: iris_test`, `serviceConnection.config` with `type: Iris`, `hostPort: 127.0.0.1:<port>` — not `localhost` — `username`, `authType.password`, `namespace: USER`; `sourceConfig.config.type: DatabaseMetadata`; sink `metadata-rest`; JWT from `${OM_JWT}`), run it against the overlay-built server, assert service `iris_test` and Database `USER` exist and logs contain no password; runs for `admin`, requires `OM_HOST_PORT` and `OM_JWT`
- [X] T034 [US4] Run it per quickstart step 4 and record the result in research.md

---

## Phase 7: User Story 5 - Optional driver install (Priority: P2)

**Goal**: the driver comes only with the `iris` extra.

**Independent Test**: install without the extra and list packages.

- [X] T035 [P] [US5] Unit test in `test_iris.py`: importing the connector code with the driver absent raises OpenMetadata's standard missing-extra error (simulate by blocking the import)
- [X] T036 [US5] Verify quickstart step 5: install `ingestion` without the extra and confirm `intersystems-irispython` and `sqlalchemy-intersystems-iris` are absent, and present with `[iris]`; record in research.md

---

## Phase 8: Polish and cross-cutting

- [X] T037 Run `make py_format` and `mvn spotless:apply` on the touched modules in `.om/`, then `make om-export` (constitution: before every commit)
- [X] T038 Run `make om-check` and confirm no diff (acceptance: write-back right after rebuild changes nothing)
- [X] T039 Record the confirmed UI registration files and locale paths (open item V1) in `specs/000-connector-foundation/research.md`
- [X] T040 Create `README.md` stub: what the repository is, `make om-import`, `make om-check`, `make om-image`, the icon source and licence, licensing summary (Apache-2.0 root, Collate Community License 1.0 for `overlay/ingestion/`, driver never vendored, optional `iris` extra)
- [X] T042 [US2] (found during T024) Server-side password masking: add `openmetadata-service/src/main/java/org/openmetadata/service/secrets/converter/IrisConnectionClassConverter.java` and register it in `ClassConverterFactory.java`; without it the server returns the Iris password in clear while Postgres is masked. Verified with an Iris and a Postgres service created through the API
- [x] T041 Move the spec's issue on the "IRIS connector" GitHub Project to Review once T037–T040 are done
- [X] T043 (review of PR #11) Add `.gitattributes` at the repository root with `* text=auto eol=lf`, so shell scripts, `seed.py` and patches keep LF line endings on Windows checkouts (`core.autocrlf`) and do not break under WSL; renormalize with `git add --renormalize .` and confirm `make om-check` shows no diff. Done by spec 001 (its T002): `.gitattributes` with `* text=auto eol=lf` plus explicit LF rules for `*.sh`, `*.py`, `*.yml`, `*.yaml`, `*.svg`; renormalized, every tracked text file is LF in the index
- [ ] T044 (review of PR #11) Check the install command `om-import` runs inside `.om/ingestion`: OpenMetadata 2.1.1's `CONTRIBUTING.md` points to `DEVELOPER.md` and `make install_dev_env` (Nox + pinned `uv`), while `om-import` runs `make install_dev`. Keep `install_dev` if it gives the same environment; otherwise switch. Record the decision in research.md and the README

---

## Dependencies and execution order

- Phase 1 → Phase 2 (US1) → Phase 3 (Foundational) → Phases 4–7 → Phase 8.
- T004 → T005 → T006 → T007 → T008 (same file, sequential). T009 needs T007.
- T010–T013 follow T009; T012 before T013. T014 can run once T009 is done.
- US2: T016 → T017 → T018/T019 (parallel) → T020 → T021 → T022; T023 after T016–T019; T024 after T020–T022 and T023.
- US3: T025 and T026 can start after T016; T027 after T025 and T026; T028 after T026; T029 and T030 after T027; T031 after T022 and T027; T032 after T026.
- US4 needs US2 and US3 complete (server image and test connection); US5 needs only Foundational.
- T037 → T038; T039 and T040 can run in parallel after T038.

## Parallel opportunities

- Phase 1: T002 and T003.
- Phase 3: T014 alongside T010–T013.
- US2: T018 and T019; T023 once the package exists.
- US3: T028 alongside T025.
- Phase 8: T039 and T040.

## Test map

| Test | Kind | Cells | Task |
|---|---|---|---|
| `make om-check` leaves no diff | tooling | — | T007, T008, T038 |
| Config parses from YAML/JSON; `namespace` required | unit | — | T023 |
| URL contains Namespace; password masked | unit | — | T023 |
| Missing extra → standard error | unit | — | T035 |
| Test connection: 5 steps per the contract table | integration | all 9 (local: `latest-em` × 3 logins until 001 lands) | T029 |
| Wrong password → fails on `CheckAccess` | integration | `reader` | T030 |
| Workflow creates `iris_test` service and Database `USER` | integration | `admin` | T033 |

## Implementation strategy

- **MVP**: Phases 1–3 plus US1 (the round trip) — the tree builds and round-trips. The first visible increment is US2.
- Then US2 → US3 (both P1), then US4 and US5, then Polish.
- Commit after each checkpoint, after `make om-export`.
