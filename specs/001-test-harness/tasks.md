---

description: "Task list for spec 001: test harness (shared fixtures + CI matrix)"
---

# Tasks: Test harness (shared fixtures + CI matrix)

**Input**: Design documents from `/specs/001-test-harness/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: REQUIRED (Constitution VI). Every story has test tasks, written first, and each test
must be able to fail ("a test that cannot fail is a finding", OpenMetadata `REVIEW.md`).

**Organization**: tasks are grouped by user story. Each task is also tagged with its delivery
phase from the plan:

- **A**: needs nothing from spec 000; can merge first.
- **B**: needs spec 000 on `main` (`make om-import`/`om-export`, the `Makefile`, the `iris/`
  connector package). B tasks start only after 000 merges.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1–US4 from spec.md
- Paths are relative to the dev repository root. `overlay/…/iris/` means
  `overlay/ingestion/tests/integration/iris/`.

## Conventions for every task

- Overlay Python files start with the Collate Community License header (plan, Constraints).
  Dev-repo files (`fixtures/`, `.github/`, root files) are Apache-2.0 and need no header.
- Only the official driver (`import iris`) and the official dialect, never `sqlalchemy_iris`.
- Never print passwords. Test credentials are throwaway (data-model, Login).
- Commit messages in English, with no AI attribution trailers.
- Local runs use port 11972 and host `127.0.0.1` (research R13). CI uses 1972.

---

## Phase 1: Setup (shared infrastructure)

**Purpose**: directories, line endings and pinned plain-venv dependencies.

- [ ] T001 [A] Create the directories `fixtures/iris/`, `overlay/ingestion/tests/integration/iris/data/` and `.github/workflows/`
- [ ] T002 [P] [A] Add `.gitattributes` at the repository root with `* text=auto eol=lf` and explicit `*.sh text eol=lf`, `*.py text eol=lf`, `*.yml text eol=lf` (research R14, SPIKE-06 surprise 6). Then run `git add --renormalize . && git status`, which must show no unexpected changes. This file is not in the ownership table, so tell Henry before merging
- [ ] T003 [P] [A] Create `fixtures/iris/requirements.txt` pinning `intersystems-irispython==5.4.1` and `pytest==9.0.3`. This is the only place these pins live for the plain venv (contracts/ci-matrix.md step 2, quickstart prerequisites)
- [ ] T004 [P] [A] Create `overlay/ingestion/tests/integration/iris/__init__.py` and `overlay/ingestion/tests/integration/iris/data/__init__.py`, each holding only the Collate Community License header

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the start script and the catalog definitions that US1, US2 and US3 all use.

**⚠️ CRITICAL**: US1 tests, US2 cells and US3 fallback all depend on T005 and T006.

- [ ] T005 [A] Write `fixtures/iris/start-iris.sh TAG [PORT=1972] [NAME=iris]` per research R2, with `set -euo pipefail`. It must:
  - run `docker rm -f NAME` (ignore a missing container);
  - run `docker run -d --name NAME -p 127.0.0.1:PORT:1972 containers.intersystems.com/intersystems/iris-community:TAG --check-caps false`;
  - poll `docker exec NAME iris qlist` until the state field is `running`, up to 180 s;
  - run `docker exec NAME iris session IRIS -U %SYS '##class(Security.Users).UnExpireUserPasswords("*")'`;
  - retry an admin SQL login with `${PYTHON:-python3}` and the driver (`iris.connect`, `SELECT $ZVERSION`) until it succeeds, up to 120 s. Before retrying, check the driver is importable; if it is not, exit 2 with "install fixtures/iris/requirements.txt";
  - print `digest=<RepoDigests[0]>` (from `docker image inspect`) and `zversion=<$ZVERSION>`, and append both to `$GITHUB_OUTPUT` when that variable is set;
  - exit 0 when ready, 1 when docker or the start fails, 2 on a readiness timeout or missing driver, printing which wait timed out;
  - honor `IRIS_ADMIN_USER`/`IRIS_ADMIN_PASSWORD` (default `_SYSTEM`/`SYS`), and never echo the password.

  Run `shellcheck fixtures/iris/start-iris.sh` (for example `docker run --rm -v "$PWD:/mnt" koalaman/shellcheck:stable fixtures/iris/start-iris.sh`), which must report nothing
- [ ] T006 [A] Write the catalog definitions at the top of `overlay/ingestion/tests/integration/iris/data/seed.py` (Collate header), as pure data with no side effects on import (contracts/fixture-loader.md, data-model.md):
  - `CATALOG_VERSION = 1`;
  - `LOGINS`: `admin`/`reader`/`reader_dict` → user, password, `is_admin`, `has_dict_grant`;
  - `DDL`: the ordered create statements for `Clinic.Patient`, `Clinic.Encounter`, `Billing.Patient`, `AI.Embedding`, the view `Clinic.ActivePatient` and `CREATE SCHEMA Scratch`, with table and column descriptions as `%DESCRIPTION`/`COMMENT` per data-model;
  - `ROWS`: the exact rows from the data-model;
  - `USERS` and `GRANTS`: per the data-model Grants table;
  - `EXPECTED`: one structure per self-check C1–C11 (object names, column lists with `DATA_TYPE`, constraints by type and columns, descriptions, row counts, dictionary tables, refusal statements).

  `import iris` happens inside functions only, so the conftest can import `LOGINS` without the driver installed

**Checkpoint**: an IRIS of any track can be started and prepared with one command, and the catalog
is defined in one place.

---

## Phase 3: User Story 1 — Recreate the shared fixtures with one command (Priority: P1) 🎯 MVP

**Goal**: one idempotent loader that recreates catalog v1 and self-checks C1–C11 (FR-001..007).

**Independent Test**: quickstart Q1–Q3. On a fresh container of each track, run the loader twice and
expect `FIXTURES OK v1` both times. Drop `Billing.Patient` and expect the self-check to fail and name it.

### Tests for User Story 1 (REQUIRED — Constitution VI) ⚠️

> Write these first and see them fail (the loader functions do not exist yet).

- [ ] T007 [US1] [A] Write `fixtures/iris/conftest.py` with these session fixtures:
  - `seed_module`: loads the canonical module by path with `importlib.util.spec_from_file_location`. It prefers `.om/ingestion/tests/integration/iris/data/seed.py` when that file exists, and falls back to `overlay/ingestion/tests/integration/iris/data/seed.py`;
  - `iris_env`: a dict with host, port, namespace and admin credentials from env, using the fixture-loader contract defaults;
  - `admin_conn`: an `iris.connect` connection as admin.

  Fixtures that need a live IRIS raise `pytest.UsageError("fixture tests need IRIS: run fixtures/iris/start-iris.sh … and set IRIS_HOST")` when `IRIS_HOST` is unset. They never skip, so CI cannot pass by skipping. Offline tests do not request these fixtures
- [ ] T008 [US1] [A] Write the offline tests in `fixtures/iris/test_seed.py`. They need no IRIS and use `monkeypatch` on the module's `iris` import:
  - (a) a connection error → `main()` returns 2 and stderr names `host:port`;
  - (b) an error whose text says the password must change → exit 2, and the message contains `start-iris.sh`;
  - (c) a cursor that raises on the 3rd DDL statement → exit 3, and stderr shows that statement's first 60 characters and the IRIS error;
  - (d) importing the module calls no `iris.connect` (import-safe);
  - (e) with `IRIS_ADMIN_PASSWORD` set to a unique token, the token appears nowhere in stdout or stderr, and neither does `Reader123`
- [ ] T009 [US1] [A] Write the live tests in `fixtures/iris/test_seed.py`. They use `admin_conn` and `seed_module` and connect as each reader with `iris.connect`:
  - `test_load_reports_all_checks`: `load()` passes, and the output has `PASS C1`…`PASS C11` plus `FIXTURES OK v1`;
  - `test_load_is_idempotent`: two `load()` calls give the same snapshot (row values per table, the users `omd_reader*` in `INFORMATION_SCHEMA.USERS` or `Security.Users`, and the grants);
  - `test_dictionary_toggle`: `omd_reader` gets `SQLCODE -99` on `%Dictionary.CompiledProperty` and `%Dictionary.PropertyDefinition`, and `omd_reader_dict` reads both;
  - `test_readers_cannot_write`: both readers get `-99` on `INSERT INTO Clinic.Patient` and on `CREATE TABLE Scratch.T001`;
  - `test_self_check_can_fail`: `self_check(expected=…)` with the `Clinic.Patient` row count set to 3 raises `SelfCheckError`, and its message has `C5`, `Clinic.Patient`, `expected 3` and `actual 2`;
  - `test_missing_object_is_named`: drop `Billing.Patient` as admin, then `self_check()` raises with `C1` and `Billing.Patient`. A `finally: load()` restores the state;
  - `test_scratch_is_emptied`: create `Scratch.Leftover` as admin, run `load()`, then `Scratch` has no tables and C7 passes

### Implementation for User Story 1

All of these edit `overlay/…/iris/data/seed.py`, so they run in order.

- [ ] T010 [US1] [A] Implement `_connect(host, port, namespace, user, password)` and the error classes in `overlay/ingestion/tests/integration/iris/data/seed.py`:
  - `NotPreparedError` (exit 2): connection refused, timeout, or the password must change;
  - `LoadError` (exit 3): holds the statement head and the IRIS error;
  - `SelfCheckError` (exit 1): holds the check id, object, expected and actual.

  Makes T008 (a), (b) pass
- [ ] T011 [US1] [A] Implement `_cleanup(cursor)` in `overlay/ingestion/tests/integration/iris/data/seed.py`:
  - drop the view, then the four tables in FK-safe order;
  - drop every table listed in `INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'Scratch'`, then the `Scratch` schema;
  - drop both users;
  - tolerate only "does not exist" codes (`-30`, `-473`, the user-not-found code recorded while implementing), and re-raise anything else as `LoadError`
- [ ] T012 [US1] [A] Implement `_create(cursor)` in `overlay/ingestion/tests/integration/iris/data/seed.py`. It runs `DDL`, inserts `ROWS` with bind parameters (`TO_VECTOR('0.1,0.2,0.3', DOUBLE)` for `AI.Embedding.Vec`), creates the users, runs the grants and commits. Any failure raises `LoadError` with the statement's first 60 characters. Makes T008 (c) pass
- [ ] T013 [US1] [A] Implement admin checks C1–C7 and C11 in `self_check()` in `overlay/ingestion/tests/integration/iris/data/seed.py`, per research R9:
  - query `INFORMATION_SCHEMA.TABLES`, `COLUMNS` (ordered by `ORDINAL_POSITION`), `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE`, `REFERENTIAL_CONSTRAINTS` and `VIEWS`, filtering by schema and name with bind parameters and comparing exact strings;
  - never use `GROUP BY` or `DISTINCT` on names;
  - assert constraints by type and columns, and by name only for `UqBillingCode`;
  - C7 creates and drops `Scratch.Probe` as admin;
  - `expected` defaults to `EXPECTED`;
  - return a list of `(check_id, object)` passes, and raise `SelfCheckError` on the first mismatch
- [ ] T014 [US1] [A] Implement reader checks C8–C10 in `self_check()` in `overlay/ingestion/tests/integration/iris/data/seed.py`:
  - connect as each reader from `LOGINS`;
  - `SELECT TOP 1 *` from each of the three schemas' tables;
  - query both dictionary tables, expecting `-99` for `omd_reader` and success for `omd_reader_dict`;
  - attempt the C10 writes and expect `-99`.

  Close the reader connections in `finally`
- [ ] T015 [US1] [A] Implement `load(host, port, namespace="USER", admin_user="_SYSTEM", admin_password="SYS")` and `main()` in `overlay/ingestion/tests/integration/iris/data/seed.py`:
  - `load()` runs connect → cleanup → create → `self_check`;
  - `main()` reads `IRIS_HOST`/`IRIS_PORT`/`IRIS_NAMESPACE`/`IRIS_ADMIN_USER`/`IRIS_ADMIN_PASSWORD` with the contract defaults (`127.0.0.1`, `1972`, `USER`, `_SYSTEM`, `SYS`);
  - print `PASS <id> <what> <object>` lines, then `FIXTURES OK v<CATALOG_VERSION> <$ZVERSION>`;
  - map the errors to exit codes 1, 2 and 3, writing messages to stderr;
  - end the file with `if __name__ == "__main__": sys.exit(main())`
- [ ] T016 [US1] [A] Write `fixtures/iris/seed.py`. It picks `.om/ingestion/tests/integration/iris/data/seed.py` when that file exists, else `overlay/ingestion/tests/integration/iris/data/seed.py`, then runs it with `runpy.run_path(path, run_name="__main__")` and propagates its `SystemExit` code. It prints which copy ran, as its first line
- [ ] T017 [US1] [A] Run the loader against `latest-em` (`fixtures/iris/start-iris.sh latest-em 11972 omd-test-iris-latest-em`). Record the catalog `DATA_TYPE` of every fixture column that the data-model does not yet list into `EXPECTED` in `overlay/…/iris/data/seed.py` and into the Objects table in `specs/001-test-harness/data-model.md` (C2)
- [ ] T018 [US1] [A] Run `pytest fixtures -q` against `latest-em` until T008 and T009 pass. Then run quickstart Q1 on all three tracks (two loader runs per track, timing start → `FIXTURES OK`, target < 2 min, SC-001), Q2 and Q3. Record the timings and any track difference in `specs/001-test-harness/research.md` (new section "Implementation measurements"). A track difference also becomes a gap entry (T034)

**Checkpoint**: US1 is complete and usable by every other spec, even before CI exists.

---

## Phase 4: User Story 2 — See every matrix cell on every push and pull request (Priority: P1)

**Goal**: nine separately reported cells, preview informative, guard and version identity in every
cell (FR-008..015). The round-trip check comes in delivery B.

**Independent Test**: quickstart Q7. A push shows 9 checks `iris-<tag>-<login>`, each summary shows
digest and `$ZVERSION`, and a deliberately broken cell fails alone.

### Tests for User Story 2 (REQUIRED — Constitution VI) ⚠️

- [ ] T019 [P] [US2] [A] Write `fixtures/iris/test_check_dialect.py`. These are offline tests that monkeypatch `importlib.metadata.distribution` and `importlib.metadata.entry_points`:
  - (a) distribution `sqlalchemy-iris` present → `main()` returns 1 and the message names `sqlalchemy-iris`;
  - (b) entry point `sqlalchemy.dialects:iris` → `sqlalchemy_iris.base:IRISDialect` → exit 1, and the message names the target;
  - (c) entry point → `sqlalchemy_intersystems_iris.iris:IRISDialect_iris` and no community distribution → exit 0;
  - (d) no IRIS dialect at all (plain venv) → exit 0

### Implementation for User Story 2

- [ ] T020 [US2] [A] Write `fixtures/iris/check_dialect.py` per research R6. It uses the standard library only, and exits 1 when the `sqlalchemy-iris` distribution is installed, when `importlib.util.find_spec("sqlalchemy_iris")` finds the module, or when the `iris` dialect entry point resolves to anything other than `sqlalchemy_intersystems_iris.iris:IRISDialect_iris`. It prints the offending package or target. Makes T019 pass
- [ ] T021 [US2] [A] Write `.github/workflows/iris-matrix.yml`, delivery A, per contracts/ci-matrix.md:
  - triggers `push` and `pull_request`; `permissions: contents: read`; no secrets;
  - `concurrency: { group: iris-matrix-${{ github.ref }}, cancel-in-progress: ${{ github.event_name == 'pull_request' }} }`;
  - one job with `name: iris-${{ matrix.tag }}-${{ matrix.login }}`, `strategy.fail-fast: false`, matrix `tag: [latest-em, latest-cd, latest-preview]` × `login: [admin, reader, reader_dict]`, `continue-on-error: ${{ matrix.tag == 'latest-preview' }}`, `timeout-minutes: 20`, and the cell env from the contract;
  - steps 1–6 in contract order: `actions/checkout@v4` with `persist-credentials: false`, `actions/setup-python@v5` 3.11, `pip install -r fixtures/iris/requirements.txt`, `start-iris.sh` with `id: iris`, `python fixtures/iris/seed.py`, `python fixtures/iris/check_dialect.py`, and `pytest fixtures -q -rs | tee pytest.log` using `set -o pipefail`;
  - capture each exit status with `rc=0; cmd || rc=$?` (SPIKE-06 fix)
- [ ] T022 [US2] [A] Add steps 11 and 12 to `.github/workflows/iris-matrix.yml`:
  - step 11, `if: always()`: write the cell name, `steps.iris.outputs.digest`, `steps.iris.outputs.zversion`, per-step durations (recorded with `date +%s` around each step into `$GITHUB_ENV`) and the pytest summary line from `pytest.log` to `$GITHUB_STEP_SUMMARY`;
  - step 12, `if: failure()`: `docker logs --tail 200 iris`.

  Then lint the workflow with `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`, which must report nothing
- [ ] T023 [US2] [A] Push `001-test-harness` to the dev repository. This needs `gh auth login` + `gh auth setup-git` in WSL, or a push from the Windows clone; confirm with the user first, because it is outward-facing and a run costs about 14 billed minutes while the repository is private. Confirm Q7 for delivery A: 9 checks with the exact names, and every summary shows digest + `$ZVERSION`. Record wall time and billed minutes (sum of per-job minutes rounded up) in `specs/001-test-harness/research.md` "Implementation measurements"
- [ ] T024 [US2] [A] Prove the failure paths on a throwaway branch `ci/001-break-cells`, in one run:
  - in `iris-latest-em-reader` only, a step that exits 1;
  - in `iris-latest-cd-admin` only, `pip install sqlalchemy-iris` before the guard;
  - in `iris-latest-preview-reader` only, a step that exits 1.

  Expected: those three fail, the guard message names `sqlalchemy-iris` (SC-006), the other six pass, and the preview failure shows as "continue-on-error". Record the run URL in `research.md`, then delete the branch (local and remote)
- [ ] T025 [US2] [B] Add job `overlay-roundtrip` to `.github/workflows/iris-matrix.yml` per contracts/ci-matrix.md: checkout with `persist-credentials: false`, setup-python 3.11, `actions/cache@v4` on `.om/` with key `om-${{ hashFiles('openmetadata.version','patches/**','Makefile') }}`, then `make om-import && make om-export && git diff --exit-code overlay patches`. Make the cell job `needs: overlay-roundtrip`
- [ ] T026 [US2] [B] Add cell steps 7–10 to `.github/workflows/iris-matrix.yml`:
  - restore the `.om/` cache and run `make om-import`, using the install command spec 000 settles (research R7, `install_dev` vs `install_dev_env`, with the `iris` extra and the test profile);
  - run `check_dialect.py` with the `.om/` interpreter;
  - unit tests: `pytest .om/ingestion/tests/unit/topology/database/test_iris.py`;
  - integration tests: `pytest .om/ingestion/tests/integration/iris -m iris -rs`, appended to `pytest.log`
- [ ] T027 [US2] [B] Push and measure delivery B: wall time (SC-004, < 15 min), `.om/` cache size and restore time, and billed minutes. Record them in `specs/001-test-harness/research.md` R7, and switch to the artifact fallback if the cache costs more than it saves
- [ ] T028 [US2] [B] After the repository is public, ask the repository admin to set branch protection on `main` with the required checks listed in contracts/ci-matrix.md (`overlay-roundtrip` + the six em/cd cells; never `latest-preview`). Then verify scenario 3: a PR failing only a preview cell is mergeable

**Checkpoint**: every push shows the 9 cells (A) plus the round-trip check (B).

---

## Phase 5: User Story 3 — Tests know their cell; one command runs one cell locally (Priority: P2)

**Goal**: the integration conftest, the placeholder test, `make test-cell` and the testcontainers
fallback (FR-016..022). All delivery B: needs 000's `IrisConnection`, `get_connection` and
`Makefile`.

**Independent Test**: quickstart Q4 and Q6. `make test-cell TAG=latest-em LOGIN=reader` passes with no
skips, and the same tests pass with no `IRIS_HOST` and leave no container behind.

### Tests for User Story 3 (REQUIRED — Constitution VI) ⚠️

- [ ] T029 [P] [US3] [B] Write `overlay/ingestion/tests/integration/iris/test_harness.py` (Collate header), per contracts/test-interface.md:
  - three tests marked `@pytest.mark.iris`:
    - `test_select_one`: `SELECT 1` via `iris_engine` returns 1;
    - `test_dictionary_toggle`: `SELECT TOP 1 Name FROM %Dictionary.CompiledProperty` succeeds iff `iris_cell.has_dict_grant`, otherwise the error text contains `-99`;
    - `test_cell_identity`: `SELECT $ZVERSION` contains `IRIS`, recorded with `record_property("zversion", …)`;
  - two unmarked pure tests of `_cell_from_env`:
    - an unknown `IRIS_LOGIN` raises `pytest.UsageError`;
    - each login maps to the user name and flags in `LOGINS`, and `name` is `iris-<tag>-<login>`

### Implementation for User Story 3

- [ ] T030 [US3] [B] Write `overlay/ingestion/tests/integration/iris/conftest.py` (Collate header), per contracts/test-interface.md and research R4, R11, R12:
  - `pytest_configure` registers the `iris` marker;
  - the frozen dataclass `IrisCell` and `_cell_from_env(env)` build the cell from `IRIS_*` env and `data.seed.LOGINS`; `IRIS_LOGIN` defaults to `reader`, `IRIS_TAG` to `latest-em`;
  - `_iris_endpoint` (session):
    - with `IRIS_HOST` set, yield `(host, port, tag)`;
    - otherwise start `DockerContainer("containers.intersystems.com/intersystems/iris-community:" + tag).with_command("--check-caps false").with_exposed_ports(1972)`, wait for `iris qlist` `running` and run the unexpire through `container.exec`, wait for the admin login, call `data.seed.load(...)`, yield `127.0.0.1` and the mapped port, and stop the container in `finally`;
  - `seeded`: `self_check` with an `IRIS_HOST`, `load` in fallback mode, failing the session on `SelfCheckError`;
  - `iris_service_connection`: imports `IrisConnection` lazily, and skips with "spec 000 connector package not available (<cell name>)" on `ImportError`;
  - `iris_engine` / `iris_admin_engine`: built via `metadata.ingestion.source.database.iris.connection.get_connection`, depend on `seeded`, and are disposed at session end.

  Confirm the `IrisConnection` field names against 000's generated model before writing
- [ ] T031 [US3] [B] Add the `Makefile` section `# --- 001: test harness ---` on top of 000's `Makefile`, per research R13:
  - `iris-up TAG=latest-em PORT=11972` runs `fixtures/iris/start-iris.sh $(TAG) $(PORT) omd-test-iris-$(TAG)`;
  - `iris-seed` runs `IRIS_HOST=127.0.0.1 IRIS_PORT=$(PORT) python fixtures/iris/seed.py`;
  - `iris-down` runs `docker rm -f omd-test-iris-$(TAG)`;
  - `test-cell TAG=… LOGIN=… [PORT=11972]` depends on `iris-up iris-seed`, then runs `IRIS_HOST=127.0.0.1 IRIS_PORT=$(PORT) IRIS_TAG=$(TAG) IRIS_LOGIN=$(LOGIN) <.om python> -m pytest .om/ingestion/tests/integration/iris -m iris -rs`, using the interpreter path 000 defines;
  - add all four to `.PHONY` and `make help`, if 000 has one
- [ ] T032 [US3] [B] Run `make om-export`, then `make py_format` on the overlay files. `make om-import && make om-export && git diff --exit-code overlay patches` must be clean (same as T025's job)
- [ ] T033 [US3] [B] Validate quickstart Q4 (`make test-cell TAG=latest-em LOGIN=reader`, `TAG=latest-cd LOGIN=reader_dict`: all pass, and `-rs` shows no skips) and Q6 (no `IRIS_HOST`: the fallback starts, seeds, passes, and `docker ps -a` shows no leftover container). Record the fallback time in `research.md`

**Checkpoint**: any spec can write `@pytest.mark.iris` tests against `iris_cell` and the engines.

---

## Phase 6: User Story 4 — A gap report exists from day one (Priority: P3)

**Goal**: `GAP-REPORT.md` with the entry format and GAP-001..009 (FR-023, SC-007). Delivery A.

**Independent Test**: quickstart Q8. `pytest fixtures/iris/test_gap_report.py` passes, and every
reproduction runs against a Q1 container.

### Tests for User Story 4 (REQUIRED — Constitution VI) ⚠️

- [ ] T034 [P] [US4] [A] Write `fixtures/iris/test_gap_report.py`. It is offline and parses `GAP-REPORT.md`:
  - entries are headed `## GAP-NNN — <title>`, with ids sequential from 001 and none skipped or repeated;
  - there are at least 9 entries;
  - every entry has the data-model Gap-entry fields (component from the allowed list, tracks, found_in, reproduction, expected, actual, connector_behavior, workaround, upstream);
  - `reproduction` is a fenced code block or the text `pending SPIKE-NN`.

  It must fail on the current tree, which has no file yet

### Implementation for User Story 4

- [ ] T035 [US4] [A] Write `GAP-REPORT.md` at the repository root:
  - the entry format from `is-omd/docs/contracts/gap-report.md`;
  - GAP-001..008 from the same contract, with tracks from evidence: SPIKE-01 for `latest-em`, SPIKE-06 for all three tracks on GAP-001/002, and untested tracks marked "not tested";
  - GAP-009 per research R10 (component IRIS SQL catalog, tracks `latest-em` + `latest-cd`, found in 001, connector behavior "decided in spec 002").

  GAP-003's reproduction reads "pending SPIKE-03". Makes T034 pass
- [ ] T036 [US4] [A] Run every GAP reproduction except GAP-003 against `latest-em` and `latest-cd` containers loaded by `fixtures/iris/seed.py`. Fix any reproduction that does not show the stated "actual" behavior, and add `latest-preview` to an entry's tracks when it reproduces there too

**Checkpoint**: later specs append entries in the fixed format.

---

## Phase 7: Polish & cross-cutting concerns

- [ ] T037 [P] [A] Write `fixtures/iris/test_repo_rules.py` (SC-008, offline). It fails if any file under `overlay/ingestion/tests/` other than `overlay/…/iris/data/seed.py` contains `CREATE USER`, `GRANT ` or `Security.Users` (case-insensitive), and prints each offending file and line
- [ ] T038 [P] [A] Add the README section `## Running tests` (delivery A part) to `README.md`, rebased on 000's stub if it exists. Cover: plain venv from `fixtures/iris/requirements.txt`, `fixtures/iris/start-iris.sh TAG 11972 NAME`, `IRIS_PORT=11972 python fixtures/iris/seed.py`, `pytest fixtures`, the guard, and the loader's exit codes
- [ ] T039 [B] Extend `README.md` "Running tests" (FR-024) with `make test-cell TAG=… LOGIN=…`, `make iris-down`, automatic single-instance mode (no `IRIS_HOST`), and the one-time setup (`make om-import`, using 000's install command)
- [ ] T040 [P] [A] In `is-omd`, on branch `spike/06-findings`, add an "Addendum: planning and implementation probes" to `spikes/findings/SPIKE-06.md`. It covers:
  - the entry-point clash (R6);
  - `GROUP BY` upper-casing (R9);
  - Scratch not listed while empty and `-473` (R10);
  - the measurements from T018/T023/T024.

  Pushing needs write access to `is-omd` or a fork (pending)
- [ ] T041 [B] Open the `is-omd` contract PR (FR-025):
  - `docs/contracts/fixtures.md`: entry point `fixtures/iris/seed.py`, source `overlay/…/iris/data/seed.py`, catalog v1 table, version history, `Scratch` defined by behavior;
  - `docs/contracts/test-matrix.md`: dated track versions and digests, `latest-cd` = 2026.3 (not 2026.2), the step order install → start, and no remaining `[VERIFY]` markers.

  Confirm with the user before opening the PR
- [ ] T042 Run quickstart Q1–Q8 end to end on the final branch. Tick SC-001..SC-008 in `specs/001-test-harness/checklists/requirements.md`, or list what remains open, and confirm Henry has reviewed SPIKE-06 before the merge to `main` (plan, Complexity Tracking)

---

## Dependencies & execution order

### Phase dependencies

- **Setup (T001–T004)**: none.
- **Foundational (T005–T006)**: after Setup. They block US1, US2 and US3.
- **US1 (T007–T018)**: after Foundational. Needed by US2's seed step and by US4's reproductions.
- **US2 A (T019–T024)**: T021–T024 need T015–T016 (the cells run the loader). T019–T020 can run alongside US1.
- **US4 (T034–T036)**: T034–T035 can run any time after Setup. T036 needs US1.
- **Delivery B (T025–T033, T039, T041)**: needs spec 000 on `main`. Within B: T030 → T029 passes → T031 → T032 → T033. T025–T026 → T027.
- **Polish**: T037, T038 and T040 after US1. T042 last.

### Order mapped to the demand

The demand's order is "fixtures loader → `test-cell` → conftest + placeholder → CI workflow (IRIS
service + seed first, then om-import + tests) → GAP-REPORT → README". It runs as follows:

1. Loader: T005–T018.
2. CI, IRIS + seed part: T019–T024.
3. GAP-REPORT: T034–T036.
4. README, A part: T038.
5. After 000 merges: `test-cell` T031, conftest + placeholder T029–T030, CI om-import + tests T025–T027, README B part T039.

`test-cell` and the conftest move behind the CI's IRIS part because they need 000.

### Within each story

- Tests first, seen failing (T008/T009 before T010–T015; T019 before T020; T029 before T030; T034 before T035).
- `seed.py` tasks T010–T015 edit one file, so they run in order.
- `iris-matrix.yml` tasks T021, T022, T025 and T026 edit one file, so they run in order.

## Parallel opportunities

```text
Setup:            T002 ∥ T003 ∥ T004
After T006:       T007–T009 (US1 tests) ∥ T019 (guard tests) ∥ T034 (gap-report test)
After T009:       T020 (guard) ∥ T035 (GAP-REPORT.md) ∥ T010… (loader, sequential)
After US1:        T021 (workflow) ∥ T036 (gap reproductions) ∥ T037 ∥ T038 ∥ T040
Delivery B:       T029 (placeholder test) ∥ T025 (round-trip job)
```

## Implementation strategy

### MVP (US1)

T001–T018. One command loads and verifies the fixtures on all three tracks. This already unblocks
fixture-dependent work in other specs locally.

### Incremental delivery

1. **A1, MVP**: Setup + Foundational + US1. Commit; no push needed.
2. **A2**: US2 delivery A (T019–T024). First push, and 9 cells are visible.
3. **A3**: US4 + T037/T038/T040. Delivery A is complete, and it is opened as a PR after Henry's SPIKE-06 review.
4. **B**, after 000 merges: rebase on `main`, then T025–T033, T039, T041, T042.

### Cost note

Each push runs 9 cells, which is about 14 billed minutes while the repository is private
(SPIKE-06). Batch commits before pushing (T023, T024 and T027 are the planned runs).

## Notes

- [P] = different files and no dependency on an unfinished task.
- Commit after each task or logical group, with no AI attribution.
- Do not create IRIS users or data in any test; only the loader does (SC-008, T037).
