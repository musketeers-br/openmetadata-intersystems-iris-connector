---

description: "Task list for spec 001: test harness (shared fixtures + CI matrix)"
---

# Tasks: Test harness (shared fixtures + CI matrix)

**Input**: Design documents from `/specs/001-test-harness/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: REQUIRED (Constitution VI). Every story has test tasks, written first, and each test
must be able to fail ("a test that cannot fail is a finding", OpenMetadata `REVIEW.md`).

**Organization**: tasks are grouped by user story. The branch is built on spec 000
(`000-connector-foundation` until it merges, then `main`), so every task can start now.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1–US4 from spec.md
- `overlay/…/iris/` means `overlay/ingestion/tests/integration/iris/`; `.om/…/iris/` is the same path
  inside `.om/`.

## Conventions for every task

- **OpenMetadata-tree files are edited inside `.om/`** (for example
  `.om/ingestion/tests/integration/iris/conftest.py`). Before committing: `make py_format` in
  `.om/ingestion` for touched Python files, then `make om-export` and `make om-check` (constitution,
  ADR-0014). Only `overlay/` and `patches/` are committed.
- Overlay Python files start with the license header spec 000 uses (`#  Copyright 2025 OpenMetadata`,
  Collate Community License 1.0). Dev-repo files (`fixtures/`, `.github/`, root files) are
  Apache-2.0 and need no header.
- Only the official driver (`import iris`) and the official dialect, never `sqlalchemy_iris`.
- Never print passwords. Test credentials are throwaway (data-model, Login).
- Local runs use port 11972 and host `127.0.0.1` (research R13). CI uses 1972.
- Documents and comments do not refer to planning material outside this repository (constitution
  1.2.2). No upstream issue is opened without both developers agreeing.
- Commit messages in English, with no AI attribution trailers.

---

## Phase 1: Setup (shared infrastructure)

**Purpose**: the `.om/` tree, line endings and pinned plain-venv dependencies.

- [X] T001 Build `.om/` once with `OM_SKIP_UI_CODEGEN=1 make om-import`, and confirm that `.om/env/bin/python -m pytest .om/ingestion/tests/unit/topology/database/test_iris.py` passes. On Linux, until spec 000 fixes research R16, `om-import` fails even on its first run; apply spec 000's one-line `-u "$(id -u):$(id -g)"` fix to `scripts/antlr4` locally, hand any root-owned files back first (`docker run --rm -v "$PWD/.om:/om" alpine chown -R "$(id -u):$(id -g)" /om`), and never commit that file from this branch. Spec 000 has since fixed it (`02a194f`); the local patch is gone
- [X] T002 [P] Add `.gitattributes` at the repository root with `* text=auto eol=lf` and explicit `*.sh text eol=lf`, `*.py text eol=lf`, `*.yml text eol=lf` (research R14). Then run `git add --renormalize . && git status`, which must show no unexpected changes (agreed with Henry, 2026-11-25)
- [X] T003 [P] Create `fixtures/iris/requirements.txt` pinning `intersystems-irispython==5.4.1` and `pytest==9.0.3`. This is the only place these pins live for the plain venv (contracts/ci-matrix.md step 2, quickstart prerequisites)
- [X] T004 [P] Create `.om/ingestion/tests/integration/iris/data/__init__.py` holding only the license header (`overlay/…/iris/__init__.py` already exists from spec 000)

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the start script, the catalog definitions and the test dependencies that US1, US2 and
US3 all use.

**⚠️ CRITICAL**: US1 tests, US2 cells and US3 all depend on T005–T007.

- [X] T005 Write `fixtures/iris/start-iris.sh TAG [PORT=1972] [NAME=iris]` per research R2, with `set -euo pipefail`. It must:
  - run `docker rm -f NAME` (ignore a missing container);
  - run `docker run -d --name NAME -p 127.0.0.1:PORT:1972 containers.intersystems.com/intersystems/iris-community:TAG --check-caps false`;
  - poll `docker exec NAME iris qlist` until the state field is `running`, up to 180 s;
  - run `docker exec NAME iris session IRIS -U %SYS '##class(Security.Users).UnExpireUserPasswords("*")'`;
  - retry an admin SQL login with `${PYTHON:-python3}` and the driver (`iris.connect`, `SELECT $ZVERSION`) until it succeeds, up to 120 s. Before retrying, check the driver is importable; if it is not, exit 2 with "install fixtures/iris/requirements.txt";
  - print `digest=<RepoDigests[0]>` (from `docker image inspect`) and `zversion=<$ZVERSION>`, and append both to `$GITHUB_OUTPUT` when that variable is set;
  - exit 0 when ready, 1 when docker or the start fails, 2 on a readiness timeout or missing driver, printing which wait timed out;
  - honor `IRIS_ADMIN_USER`/`IRIS_ADMIN_PASSWORD` (default `_SYSTEM`/`SYS`), and never echo the password.

  Run `shellcheck fixtures/iris/start-iris.sh` (for example `docker run --rm -v "$PWD:/mnt" koalaman/shellcheck:stable fixtures/iris/start-iris.sh`), which must report nothing
- [X] T006 Write the catalog definitions at the top of `.om/ingestion/tests/integration/iris/data/seed.py` (license header), as pure data with no side effects on import (contracts/fixture-loader.md, data-model.md):
  - `CATALOG_VERSION = 1` and `VERSION_HISTORY = {1: "spec 001: Clinic, Billing, AI, Scratch (sentinel Scratch.Keep); omd_reader, omd_reader_dict"}`;
  - `LOGINS`: `admin`/`reader`/`reader_dict` → user, password, `is_admin`, `has_dict_grant`;
  - `DDL`: the ordered create statements for `Clinic.Patient`, `Clinic.Encounter`, `Billing.Patient`, `AI.Embedding`, the view `Clinic.ActivePatient`, `CREATE SCHEMA Scratch` and the empty sentinel `Scratch.Keep (Id INT PRIMARY KEY)`, with table and column descriptions as `%DESCRIPTION`/`COMMENT` per data-model;
  - `ROWS`: the exact rows from the data-model;
  - `USERS` and `GRANTS`: per the data-model Grants table;
  - `EXPECTED`: one structure per self-check C1–C11 (object names, column lists with `DATA_TYPE`, constraints by type and columns, descriptions, row counts, dictionary tables, refusal statements).

  `import iris` happens inside functions only, so the conftest can import `LOGINS` without the driver installed
- [X] T007 Add the `Makefile` section `# --- 001: test harness ---` with target `om-test-deps` (research R7): it installs into `.om/env` the `iris` extra at the versions in the `ingestion/setup.py` patch (`intersystems-irispython==5.4.1`, `sqlalchemy-intersystems-iris==1.0.2`) and `testcontainers` at the version OpenMetadata 2.1.1's `ingestion/uv.lock` pins, using `uv pip install --python .om/env/bin/python`. It is idempotent and prints the installed versions. Keep the target one line that calls `scripts/om-test-deps.sh`, as spec 000's targets do. Add it to `.PHONY`

**Checkpoint**: an IRIS of any track can be started and prepared with one command, the catalog is
defined in one place, and `.om/env` can run IRIS tests.

---

## Phase 3: User Story 1 — Recreate the shared fixtures with one command (Priority: P1) 🎯 MVP

**Goal**: one idempotent loader that recreates catalog v1 and self-checks C1–C11 (FR-001..007).

**Independent Test**: quickstart Q1–Q3. On a fresh container of each track, run the loader twice and
expect `FIXTURES OK v1` both times. Drop `Billing.Patient` and expect the self-check to fail and name it.

### Tests for User Story 1 (REQUIRED — Constitution VI) ⚠️

> Write these first and see them fail (the loader functions do not exist yet).

- [X] T008 [US1] Write `fixtures/iris/conftest.py` with these session fixtures:
  - `seed_module`: loads the canonical module by path with `importlib.util.spec_from_file_location`. It prefers `.om/ingestion/tests/integration/iris/data/seed.py` when that file exists, and falls back to `overlay/ingestion/tests/integration/iris/data/seed.py`;
  - `iris_env`: a dict with host, port, namespace and admin credentials from env, using the fixture-loader contract defaults;
  - `admin_conn`: an `iris.connect` connection as admin.

  Fixtures that need a live IRIS raise `pytest.UsageError("fixture tests need IRIS: run fixtures/iris/start-iris.sh … and set IRIS_HOST")` when `IRIS_HOST` is unset. They never skip, so CI cannot pass by skipping. Offline tests do not request these fixtures
- [X] T009 [US1] Write the offline tests in `fixtures/iris/test_seed.py`. They need no IRIS and use `monkeypatch` on the module's `iris` import:
  - (a) a connection error → `main()` returns 2 and stderr names `host:port`;
  - (b) an error whose text says the password must change → exit 2, and the message contains `start-iris.sh`;
  - (c) a cursor that raises on the 3rd DDL statement → exit 3, and stderr shows that statement's first 60 characters and the IRIS error;
  - (d) importing the module calls no `iris.connect` (import-safe);
  - (e) with `IRIS_ADMIN_PASSWORD` set to a unique token, the token appears nowhere in stdout or stderr, and neither does `Reader123`;
  - (f) `iris.connect` fails twice with "connection refused" and then succeeds → the load proceeds; refused past `IRIS_WAIT_SECONDS=1` → exit 2 and the message states the time waited; a password-change error is not retried (`iris.connect` called once). Patch `time.sleep` and `time.monotonic`, so no test really waits
- [X] T010 [US1] Write the live tests in `fixtures/iris/test_seed.py`. They use `admin_conn` and `seed_module` and connect as each reader with `iris.connect`:
  - `test_load_reports_all_checks`: `load()` passes, and the output has `PASS C1`…`PASS C11` plus `FIXTURES OK v1`;
  - `test_load_is_idempotent`: after each of two `load()` calls, take a snapshot. It holds, per table, the rows ordered by primary key, plus the columns and constraints as read by C2/C3, plus the C8–C10 outcome per login (login ok, readable schemas, dictionary allowed or `-99`, write refused). The two snapshots must be equal. Users and grants are compared by behavior, because `Security.Users` is only in `%SYS`;
  - `test_dictionary_toggle`: `omd_reader` gets `SQLCODE -99` on `%Dictionary.CompiledProperty` and `%Dictionary.PropertyDefinition`, and `omd_reader_dict` reads both;
  - `test_readers_cannot_write`: both readers get `-99` on `INSERT INTO Clinic.Patient` and on `CREATE TABLE Scratch.ReaderProbe`;
  - `test_self_check_can_fail`: `self_check(expected=…)` with the `Clinic.Patient` row count set to 3 raises `SelfCheckError`, and its message has `C5`, `Clinic.Patient`, `expected 3` and `actual 2`;
  - `test_missing_object_is_named`: drop `Billing.Patient` as admin, then `self_check()` raises with `C1` and `Billing.Patient`. A `finally: load()` restores the state;
  - `test_scratch_is_emptied`: create `Scratch.Leftover` as admin, run `load()`, then `Keep` is the only table in `Scratch` and C7 passes
  - `test_scratch_stays_listed`: as admin, create and drop `Scratch.Tmp`; `Scratch` is still in `INFORMATION_SCHEMA.SCHEMATA` and `Keep` still exists (the case spec 002's mark-deleted test relies on)

### Implementation for User Story 1

All of these edit `.om/…/iris/data/seed.py`, so they run in order.

- [X] T011 [US1] Implement `_connect(host, port, namespace, user, password)`, with bounded retry per the contract (`IRIS_WAIT_SECONDS`), and the error classes in `.om/ingestion/tests/integration/iris/data/seed.py`:
  - `NotPreparedError` (exit 2): connection refused, timeout, or the password must change;
  - `LoadError` (exit 3): holds the statement head and the IRIS error;
  - `SelfCheckError` (exit 1): holds the check id, object, expected and actual.

  Makes T009 (a), (b), (f) pass
- [X] T012 [US1] Implement `_cleanup(cursor)` in `.om/ingestion/tests/integration/iris/data/seed.py`:
  - drop the view, then the four tables in FK-safe order;
  - drop every table listed in `INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'Scratch'` (including `Keep`), then the `Scratch` schema;
  - drop both users;
  - tolerate only "does not exist" codes (`-30`, `-473`, the user-not-found code recorded while implementing), and re-raise anything else as `LoadError`
- [X] T013 [US1] Implement `_create(cursor)` in `.om/ingestion/tests/integration/iris/data/seed.py`. It runs `DDL`, inserts `ROWS` with bind parameters (`TO_VECTOR('0.1,0.2,0.3', DOUBLE)` for `AI.Embedding.Vec`), creates the users, runs the grants and commits. Any failure raises `LoadError` with the statement's first 60 characters. Makes T009 (c) pass
- [X] T014 [US1] Implement admin checks C1–C7 and C11 in `self_check()` in `.om/ingestion/tests/integration/iris/data/seed.py`, per research R9:
  - query `INFORMATION_SCHEMA.TABLES`, `COLUMNS` (ordered by `ORDINAL_POSITION`), `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE`, `REFERENTIAL_CONSTRAINTS` and `VIEWS`, filtering by schema and name with bind parameters and comparing exact strings;
  - never use `GROUP BY` or `DISTINCT` on names;
  - assert constraints by type and columns, and by name only for `UqBillingCode`;
  - C7 checks that `Keep` is the only `Scratch` table, with 0 rows, and that `Scratch` is in `SCHEMATA`, then creates and drops `Scratch.Probe` as admin;
  - `expected` defaults to `EXPECTED`;
  - return a list of `(check_id, object)` passes, and raise `SelfCheckError` on the first mismatch
- [X] T015 [US1] Implement reader checks C8–C10 in `self_check()` in `.om/ingestion/tests/integration/iris/data/seed.py`:
  - connect as each reader from `LOGINS`;
  - `SELECT TOP 1 *` from each of the three schemas' tables;
  - query both dictionary tables, expecting `-99` for `omd_reader` and success for `omd_reader_dict`;
  - attempt the C10 writes and expect `-99`.

  Close the reader connections in `finally`
- [X] T016 [US1] Implement `load(host, port, namespace="USER", admin_user="_SYSTEM", admin_password="SYS")` and `main()` in `.om/ingestion/tests/integration/iris/data/seed.py`:
  - `load()` runs connect → cleanup → create → `self_check`;
  - `main()` reads `IRIS_HOST`/`IRIS_PORT`/`IRIS_NAMESPACE`/`IRIS_ADMIN_USER`/`IRIS_ADMIN_PASSWORD`/`IRIS_WAIT_SECONDS` with the contract defaults (`127.0.0.1`, `1972`, `USER`, `_SYSTEM`, `SYS`, `60`);
  - print `PASS <id> <what> <object>` lines, then `FIXTURES OK v<CATALOG_VERSION> <$ZVERSION>`;
  - map the errors to exit codes 1, 2 and 3, writing messages to stderr;
  - end the file with `if __name__ == "__main__": sys.exit(main())`
- [X] T017 [US1] Write `fixtures/iris/seed.py`. It picks `.om/ingestion/tests/integration/iris/data/seed.py` when that file exists, else `overlay/ingestion/tests/integration/iris/data/seed.py`, then runs it with `runpy.run_path(path, run_name="__main__")` and propagates its `SystemExit` code. It prints which copy ran, as its first line
- [X] T018 [US1] Run the loader against `latest-em` (`fixtures/iris/start-iris.sh latest-em 11972 omd-test-iris-latest-em`). Record the catalog `DATA_TYPE` of every fixture column that the data-model does not yet list into `EXPECTED` in `.om/…/iris/data/seed.py` and into the Objects table in `specs/001-test-harness/data-model.md` (C2)
- [X] T019 [US1] Run `pytest fixtures -q` against `latest-em` until T009 and T010 pass. Then run quickstart Q1 on all three tracks (two loader runs per track, timing start → `FIXTURES OK`, target < 2 min, SC-001), Q2 and Q3. Record the timings and any track difference in `specs/001-test-harness/research.md` (new section "Implementation measurements"). A track difference also becomes a gap entry (T036)
- [X] T020 [US1] Run `make py_format` in `.om/ingestion`, then `make om-export` and `make om-check` (no diff). Confirm `overlay/ingestion/tests/integration/iris/data/{__init__,seed}.py` exist and match `.om/`. Commit

**Checkpoint**: US1 is complete and usable by every other spec locally, before CI exists.

---

## Phase 4: User Story 2 — See every matrix cell on every pull request and every push to main (Priority: P1)

**Goal**: the overlay round-trip check plus nine separately reported cells, preview informative,
guard and version identity in every cell (FR-008..015).

**Independent Test**: quickstart Q7. A draft pull request shows `overlay-roundtrip` and 9 checks
`iris-<tag>-<login>`, each summary shows digest and `$ZVERSION`, and a deliberately broken cell fails
alone.

### Tests for User Story 2 (REQUIRED — Constitution VI) ⚠️

- [X] T021 [P] [US2] Write `fixtures/iris/test_cell_login.py`, a fast driver-level check of the cell's login that runs before the connector tests. Parametrize over `IRIS_LOGIN` when it is set, else over all three logins from `LOGINS`. For each login, connect with `iris.connect`, then check:
  - `SELECT COUNT(*) FROM Clinic.Patient` returns 2;
  - `SELECT TOP 1 Name FROM %Dictionary.CompiledProperty` succeeds iff `has_dict_grant`, otherwise the error carries `-99`;
  - `INSERT INTO Clinic.Patient` is refused with `-99` unless `is_admin` (admin's insert runs in a transaction that is rolled back).

  The test id contains the login, so the job summary shows which login ran
- [X] T022 [P] [US2] Write `fixtures/iris/test_check_dialect.py`. These are offline tests that monkeypatch `importlib.metadata.distribution` and `importlib.metadata.entry_points`:
  - (a) distribution `sqlalchemy-iris` present → `main()` returns 1 and the message names `sqlalchemy-iris`;
  - (b) entry point `sqlalchemy.dialects:iris` → `sqlalchemy_iris.base:IRISDialect` → exit 1, and the message names the target;
  - (c) entry point → `sqlalchemy_intersystems_iris.iris:IRISDialect_iris` and no community distribution → exit 0;
  - (d) no IRIS dialect at all (plain venv) → exit 0

### Implementation for User Story 2

- [X] T023 [US2] Write `fixtures/iris/check_dialect.py` per research R6. It uses the standard library only, and exits 1 when the `sqlalchemy-iris` distribution is installed, when `importlib.util.find_spec("sqlalchemy_iris")` finds the module, or when the `iris` dialect entry point resolves to anything other than `sqlalchemy_intersystems_iris.iris:IRISDialect_iris`. It prints the offending package or target. Makes T022 pass
- [ ] T024 [US2] Write `.github/workflows/iris-matrix.yml` per contracts/ci-matrix.md:
  - triggers (`pull_request`, `push` on `main` only, `workflow_dispatch`), `permissions: contents: read`, no secrets, `concurrency` exactly as in the contract, `OM_SKIP_UI_CODEGEN: "1"` at workflow level;
  - job `overlay-roundtrip`: checkout with `persist-credentials: false`, `astral-sh/setup-uv`, `actions/cache@v4` on the uv cache and `.cache/` with the contract's key, `make om-import`, `make om-check`;
  - job `iris` with `name: iris-${{ matrix.tag }}-${{ matrix.login }}`, `needs: overlay-roundtrip`, `strategy.fail-fast: false`, matrix `tag: [latest-em, latest-cd, latest-preview]` × `login: [admin, reader, reader_dict]`, `continue-on-error: ${{ matrix.tag == 'latest-preview' }}`, `timeout-minutes: 30`, and the cell env from the contract;
  - cell steps 1–10 in contract order; pytest output goes through `tee -a pytest.log` with `set -o pipefail`;
  - capture each exit status with `rc=0; cmd || rc=$?` (SPIKE-06 fix)
- [ ] T025 [US2] Add steps 11 and 12 to `.github/workflows/iris-matrix.yml`:
  - step 11, `if: always()`: write the cell name, `steps.iris.outputs.digest`, `steps.iris.outputs.zversion`, per-step durations (recorded with `date +%s` around each step into `$GITHUB_ENV`), the pytest summary lines and the skip reasons from `pytest.log` to `$GITHUB_STEP_SUMMARY`;
  - step 12, `if: failure()`: `docker logs --tail 200 iris`.

  Then lint the workflow with `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.7`, which must report nothing
- [ ] T026 [US2] **Prerequisite** (met by spec 000's `02a194f`): spec 000's `scripts/antlr4` runs its container as the calling user (research R16, PR #11 review). Without it `overlay-roundtrip` fails on the runner and every cell is skipped. Then push `001-test-harness` and open it as a **draft** pull request to `000-connector-foundation` (to `main` once 000 has merged). Confirm with the user first: it is outward-facing, and a run costs at least 14 billed minutes while the repository is private. Confirm Q7: `overlay-roundtrip` plus 9 checks with the exact names, and every summary shows digest + `$ZVERSION`. Record wall time, cold `om-import` time per job and billed minutes (sum of per-job minutes rounded up) in `specs/001-test-harness/research.md` "Implementation measurements". If the run misses SC-004 (15 min), apply research R7's first optimization (cache `.om/`)
- [ ] T027 [US2] Same prerequisite as T026. Prove the failure paths on a throwaway branch `ci/001-break-cells` opened as a draft pull request (confirm with the user first), in one run:
  - in `iris-latest-em-reader` only, a step that exits 1;
  - in `iris-latest-cd-admin` only, `pip install sqlalchemy-iris` before the guard;
  - in `iris-latest-preview-reader` only, a step that exits 1.

  Expected: those three fail, the guard message names `sqlalchemy-iris` (SC-006), the other six pass, and the preview failure shows as "continue-on-error". Also break `overlay-roundtrip` with a stray file in `overlay/` that `om-export` would remove, and expect it to fail before any cell runs (US2 scenario 4). Record the run URL in `research.md`, then close the pull request and delete the branch (local and remote)
- [ ] T028 [US2] After the repository is public, ask the repository admin to set branch protection on `main` with the required checks listed in contracts/ci-matrix.md (`overlay-roundtrip` + the six em/cd cells; never `latest-preview`). Then verify scenario 3: a PR failing only a preview cell is mergeable

**Checkpoint**: every pull request and push to `main` shows the round-trip check and the 9 cells.

---

## Phase 5: User Story 3 — Tests know their cell; one command runs one cell locally (Priority: P2)

**Goal**: the integration conftest, the placeholder test, spec 000's test moved onto it,
`make test-cell` and the testcontainers fallback (FR-016..022, FR-025).

**Independent Test**: quickstart Q4, Q6 and Q9. `make test-cell TAG=latest-em LOGIN=reader` passes
with no unexpected skips, the same tests pass with no `IRIS_HOST` and leave no container behind, and
`make om-check` passes twice.

### Tests for User Story 3 (REQUIRED — Constitution VI) ⚠️

- [X] T029 [P] [US3] Write `.om/ingestion/tests/integration/iris/test_harness.py` (license header), per contracts/test-interface.md:
  - three tests marked `@pytest.mark.iris`:
    - `test_select_one`: `SELECT 1` via `iris_engine` returns 1;
    - `test_dictionary_toggle`: `SELECT TOP 1 Name FROM %Dictionary.CompiledProperty` succeeds iff `iris_cell.has_dict_grant`, otherwise the error text contains `-99`;
    - `test_cell_identity`: `SELECT $ZVERSION` contains `IRIS`, recorded with `record_property("zversion", …)`;
  - two unmarked pure tests of `_cell_from_env`:
    - an unknown `IRIS_LOGIN` raises `pytest.UsageError`;
    - each login maps to the user name and flags in `LOGINS`, and `name` is `iris-<tag>-<login>`

### Implementation for User Story 3

- [X] T030 [US3] Write `.om/ingestion/tests/integration/iris/conftest.py` (license header), per contracts/test-interface.md and research R4, R11, R12:
  - `pytest_configure` registers the `iris` marker;
  - the frozen dataclass `IrisCell` and `_cell_from_env(env)` build the cell from `IRIS_*` env and `data.seed.LOGINS`; `IRIS_LOGIN` defaults to `reader`, `IRIS_TAG` to `latest-em`;
  - `_iris_endpoint` (session):
    - with `IRIS_HOST` set, yield `(host, port, tag)`;
    - otherwise start `DockerContainer("containers.intersystems.com/intersystems/iris-community:" + tag).with_command("--check-caps false").with_exposed_ports(1972)`, wait for `iris qlist` `running` and run the unexpire through `container.exec`, wait for the admin login, call `data.seed.load(...)`, yield `127.0.0.1` and the mapped port, and stop the container in `finally`;
  - `seeded`: `self_check` with an `IRIS_HOST`, `load` in fallback mode, failing the session on `SelfCheckError`;
  - `iris_service_connection`: the generated `IrisConnection` model (`hostPort`, `username`, `authType=BasicAuth(password=…)`, `namespace`) for the cell;
  - `iris_engine` / `iris_admin_engine`: `metadata.ingestion.source.database.iris.connection.IrisConnection(config).client`, depending on `seeded`, disposed at session end. Makes T029 pass
- [X] T031 [US3] Migrate `.om/ingestion/tests/integration/iris/test_connection.py` (spec 000) onto the conftest (FR-025, research R15): remove its `LOGINS` table, `_login()` and the `IRIS_*` reading; build connections from `iris_service_connection` (with `model_copy(update=…)` for the wrong-password, host, port and namespace cases) and branch on `iris_cell.has_dict_grant` instead of the login string; keep every assertion. Update its docstring. Then migrate `.om/…/iris/test_workflow.py` the same way (research R15): host, port and Namespace from `iris_service_connection`, admin user and password from `data.seed.LOGINS["admin"]`, and the `OM_HOST_PORT`/`OM_JWT` check as a module-level `skipif`; keep every assertion. Both files are Henry's; the change is agreed (2026-11-25). Spec 002 also edits `test_workflow.py`, so whichever branch merges second rebases
- [X] T032 [US3] Add to the `Makefile` section `# --- 001: test harness ---`, per research R13:
  - `iris-up TAG=latest-em PORT=11972` runs `fixtures/iris/start-iris.sh $(TAG) $(PORT) omd-test-iris-$(TAG)`;
  - `iris-seed` runs `IRIS_HOST=127.0.0.1 IRIS_PORT=$(PORT) python fixtures/iris/seed.py`;
  - `iris-down` runs `docker rm -f omd-test-iris-$(TAG)`;
  - `test-cell TAG=… LOGIN=… [PORT=11972]` depends on `om-test-deps iris-up iris-seed`, then runs, from `.om/ingestion`, `IRIS_HOST=127.0.0.1 IRIS_PORT=$(PORT) IRIS_TAG=$(TAG) IRIS_LOGIN=$(LOGIN) ../env/bin/python -m pytest tests/integration/iris -m iris -rs` (research R13);
  - add all four to `.PHONY`
- [X] T033 [US3] Run `make py_format` in `.om/ingestion`, then `make om-export`, and `make om-check` twice (Q9). Commit `overlay/…/iris/{conftest,test_harness,test_connection}.py` and the `Makefile`
- [X] T034 [US3] Validate quickstart Q4 (`make test-cell TAG=latest-em LOGIN=reader`, `TAG=latest-cd LOGIN=reader_dict`: all pass, and `-rs` shows only `test_workflow.py`'s server skip) and Q6 (no `IRIS_HOST`: the fallback starts, seeds, passes, and `docker ps -a` shows no leftover container). Record the fallback time in `research.md`

**Checkpoint**: any spec can write `@pytest.mark.iris` tests against `iris_cell` and the engines.

---

## Phase 6: User Story 4 — A gap report exists from day one (Priority: P3)

**Goal**: `GAP-REPORT.md` completed to GAP-001..009, with tracks filled for every entry (FR-023,
SC-007).

**Independent Test**: quickstart Q8. `pytest fixtures/iris/test_gap_report.py` passes, and every
reproduction runs against a Q1 container.

### Tests for User Story 4 (REQUIRED — Constitution VI) ⚠️

- [X] T035 [P] [US4] Write `fixtures/iris/test_gap_report.py`. It is offline and parses `GAP-REPORT.md`:
  - entries are headed `### GAP-NNN — <title>`, with ids sequential from 001 and none skipped or repeated;
  - there are at least 9 entries;
  - every entry has the bold labels of the existing entries (GAP-004, GAP-005) in this order: `Component`, `IRIS tracks`, `Found in spec`, `Reproduction`, `Expected`, `Actual`, `Connector behavior`, `User workaround`, `Upstream` (data-model, Gap entry);
  - `Component` is one of the data-model's values;
  - `Reproduction` is a fenced code block or the text `pending SPIKE-NN`;
  - `IRIS tracks` names all three tracks, each as reproduced, not reproduced or not tested.

  It must fail on the current tree, which has only GAP-004 and GAP-005

### Implementation for User Story 4

- [X] T036 [US4] Complete `GAP-REPORT.md`:
  - insert GAP-001..003 before GAP-004 and GAP-006..009 after GAP-005, from the data-model's "Known entries" table, in the format of the existing entries;
  - fill tracks from evidence: SPIKE-06 for GAP-001/002 (all three tracks), SPIKE-01 for GAP-006..008 (`latest-em`), R10 for GAP-009 (`latest-em`, `latest-cd`);
  - GAP-003's reproduction reads "pending SPIKE-03";
  - keep the `Upstream` fields "not raised yet" (no issue without both developers agreeing).

  Tracks without evidence yet are written "not tested", which T037 replaces. Makes T035 pass
- [X] T037 [US4] Run every GAP reproduction except GAP-003 against `latest-em`, `latest-cd` and `latest-preview` containers loaded by `fixtures/iris/seed.py` (GAP-004..008 with `.om/env/bin/python`). Fix any reproduction that does not show the stated "actual" behavior, and update every entry's `IRIS tracks`, GAP-004 and GAP-005 included. Makes T035 pass

**Checkpoint**: later specs append entries in the fixed format.

---

## Phase 7: Polish & cross-cutting concerns

- [X] T038 [P] Write `fixtures/iris/test_repo_rules.py` (FR-018, SC-008, offline). It parses every `.py` file under `overlay/ingestion/tests/` except `overlay/…/iris/data/seed.py` with `ast`, and inspects only string constants passed as the first argument of `execute`, `exec_driver_sql` or `text` (so assertion messages such as `test_connection.py`'s `"GRANT SELECT ON %Dictionary…"` are not flagged). It fails, printing each offending file and line, on:
  - `CREATE USER`, `GRANT`, `Security.Users` (case-insensitive);
  - `CREATE TABLE`, `CREATE VIEW`, `INSERT INTO`, `DROP TABLE` whose target is not `Scratch.<name>`;
  - any `CREATE TABLE` or `DROP TABLE` on `Scratch.Keep` (the loader owns it).

  Include self-tests on temporary files: `text("CREATE TABLE Clinic.X …")` and `text("DROP TABLE Scratch.Keep")` fail; `assert "GRANT SELECT ON X" in msg` passes. So the rule can be shown to fail, and to ignore assertion text
- [ ] T039 [P] Replace the integration-test paragraph of `README.md` with a `## Running tests` section (FR-024): plain venv from `fixtures/iris/requirements.txt`; `fixtures/iris/start-iris.sh TAG 11972 NAME`; `IRIS_PORT=11972 python fixtures/iris/seed.py` and its exit codes; `pytest fixtures`; the guard; `make om-import` installing the test dependencies (`make om-test-deps` by hand only after another sync); `make test-cell TAG=… LOGIN=…`; `make iris-down`; automatic single-instance mode (no `IRIS_HOST`); `.om/env/bin/python` as the connector's interpreter. The README stub is Henry's until spec 009; the change is agreed (2026-11-25)
- [ ] T040 [P] Update `docs/adr/0012-shared-fixtures-and-matrix.md` (FR-026): entry point `fixtures/iris/seed.py` with source `overlay/ingestion/tests/integration/iris/data/seed.py`; `Scratch` with the sentinel `Scratch.Keep` (GAP-009, research R10); CI on pull requests, pushes to `main` and by hand, plus the `overlay-roundtrip` check; a dated "Revised" note in the status line
- [ ] T041 Run quickstart Q1–Q9 end to end on the final branch. Tick SC-001..SC-008 in `specs/001-test-harness/checklists/requirements.md`, or list what remains open, and confirm Henry has reviewed SPIKE-06 before the merge (plan, Complexity Tracking)

---

## Dependencies & execution order

### Phase dependencies

- **Setup (T001–T004)**: none. T001 takes a few minutes (clone, install, generate).
- **Foundational (T005–T007)**: after Setup. They block US1, US2 and US3.
- **US1 (T008–T020)**: after Foundational. Needed by US2's seed step, US3's fallback and US4's reproductions.
- **US2 (T021–T028)**: T021–T023 can be written alongside US1. T024–T027 need US1 and US3 (the cells run the connector tests).
- **US3 (T029–T034)**: after US1. T030 → T029 passes → T031 → T032 → T033 → T034.
- **US4 (T035–T037)**: T035–T036 can run any time after Setup. T037 needs US1 and T007.
- **Polish**: T038–T040 after US1. T041 last.

### Order as the work is done

1. Loader: T001–T020.
2. Harness conftest and `test-cell`: T029–T034.
3. CI: T021–T027.
4. Gap report: T035–T037.
5. README, ADR, repo rules, final validation: T038–T041.

### Within each story

- Tests first, seen failing (T009/T010 before T011–T016; T022 before T023; T029 before T030; T035 before T036).
- `seed.py` tasks T011–T016 edit one file, so they run in order.
- `iris-matrix.yml` tasks T024 and T025 edit one file, so they run in order.
- `Makefile` tasks T007 and T032 edit one section, so they run in order.

## Parallel opportunities

```text
Setup:            T002 ∥ T003 ∥ T004
After T007:       T008–T010 (US1 tests) ∥ T021 (cell-login test) ∥ T022 (guard tests) ∥ T035 (gap-report test)
After T010:       T023 (guard) ∥ T036 (GAP-REPORT.md) ∥ T011… (loader, sequential)
After US1:        T029 (placeholder test) ∥ T037 (gap reproductions) ∥ T038 ∥ T039 ∥ T040
```

## Implementation strategy

### MVP (US1)

T001–T020. One command loads and verifies the fixtures on all three tracks. This already unblocks
fixture-dependent work in other specs locally.

### Incremental delivery

1. **MVP**: Setup + Foundational + US1. Commit; no push needed.
2. **Harness**: US3. Integration tests run locally against any cell, and spec 000's test uses the fixtures.
3. **CI**: US2. First draft pull request, and the round-trip check plus 9 cells are visible.
4. **Gap report and polish**: US4, T038–T041. Opened for review after Henry's SPIKE-06 review and after 000 merges. Merge order 000 → 001 → 002 (agreed 2026-11-25): spec 002 rebases on 001, and its GAP-010..013 follow 001's GAP-001..009.

### Cost note

Each pull request commit runs the round-trip job and 9 cells once (no duplicate push run). The cells
alone cost about 14 billed minutes while the repository is private (SPIKE-06); the rebuild adds to
that. Batch commits before pushing to the pull request (T026 and T027 are the planned runs).

## Notes

- [P] = different files and no dependency on an unfinished task.
- Commit after each task or logical group, after `make om-export` and `make om-check`, with no AI attribution.
- Do not create IRIS users or data in any test; only the loader does (SC-008, T038).
