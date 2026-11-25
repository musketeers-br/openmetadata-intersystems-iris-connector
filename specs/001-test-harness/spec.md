# Feature Specification: Test harness (shared fixtures + CI matrix)

**Feature Branch**: `001-test-harness`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "Provide the shared test environment that every other part of the IRIS connector for OpenMetadata is tested with. A single fixture set, loaded by one idempotent command, creates in the IRIS "USER" Namespace the sample schemas and objects every test relies on: the same table name in two schemas (Clinic.Patient and Billing.Patient), mixed-case names, primary, foreign and unique keys, table and column descriptions, a view, a table with a VECTOR(DOUBLE, 3) column, and an empty scratch schema for tests that must create and drop objects; plus two least-privilege logins: one with only SELECT on the sample schemas, and one that is also allowed to read the class dictionary. The loader ends by checking that everything it created is there. Public CI runs the test suite against the three IRIS Community release tracks (latest-em, latest-cd, latest-preview), each as administrator, as the plain least-privilege login and as the least-privilege login with the dictionary grant: nine cells, each reported separately. The latest-preview track is informative and does not block merging. CI first checks that the repository's connector files rebuild cleanly onto the pinned OpenMetadata release. Tests learn which cell they run in (release track, login, whether the login is admin, whether it can read the dictionary) from a shared test fixture, never by creating their own users or data. The same tests can run locally for one chosen cell with one command, and, when no IRIS address is given, start a single IRIS container themselves so the upstream project can run them too. A gap report file exists with its entry format and the known IRIS limitations."

**Covers**: NFR-1 · **Architecture**: AD-12 · **ADRs**: [0012](../../docs/adr/0012-shared-fixtures-and-matrix.md), [0013](../../docs/adr/0013-gap-report.md), [0014](../../docs/adr/0014-repository-topology.md) · **Spike**: SPIKE-06 (`is-omd/spikes/findings/SPIKE-06.md`) · **Contracts** (`is-omd/docs/contracts/`): fixtures, test-matrix, gap-report, repository-layout

## User Scenarios & Testing *(mandatory)*

Actors: the two **connector developers** and their coding agents (write and run tests), the **reviewer**
of a pull request (reads CI results), and the **upstream OpenMetadata maintainers** (run the
connector's tests in their own tree, without our CI).

### User Story 1 - Recreate the shared fixtures with one command (Priority: P1)

A developer points the fixture loader at any IRIS instance of a supported release track and runs
one command. The loader removes whatever an earlier run left, recreates every sample schema, object,
row, login and grant, and finishes by checking that each of them exists and behaves as expected.
Running it again gives the same result.

**Why this priority**: every other spec's tests assert on these objects and logins. Without a
reliable, repeatable fixture set nothing else can be tested.

**Independent Test**: start a fresh IRIS container of each track, run the command twice, and confirm
the self-check passes both times; then delete one fixture object by hand and confirm the self-check
fails and names it.

**Acceptance Scenarios**:

1. **Given** a fresh IRIS container of `latest-em`, `latest-cd` or `latest-preview` with its default
   passwords unexpired, **When** the developer runs the loader, **Then** every object, row, login and
   grant in the fixture catalog (FR-002, FR-003) exists and the self-check reports success.
2. **Given** an IRIS instance where the loader already ran, **When** it runs again, **Then** it
   finishes successfully and the resulting state is identical to a first run (no duplicate rows,
   users or grants).
3. **Given** an instance where a fixture object is missing or wrong after loading, **When** the
   self-check runs, **Then** it fails and names the object and the expectation that failed.
4. **Given** the loader run as the administrator, **When** it finishes, **Then** the plain
   least-privilege login cannot read the class dictionary and the dictionary-grant login can.

---

### User Story 2 - See every matrix cell on every push and pull request (Priority: P1)

On every push and pull request, CI rebuilds the connector onto the pinned OpenMetadata release, then
runs the test suite in nine separately reported cells: three IRIS release tracks × three logins.
The reviewer sees which cell failed without opening logs. A failure on `latest-preview` is visible
but does not block the merge.

**Why this priority**: the constitution (Principle VI) makes "green on every blocking cell" the
acceptance bar of every spec. This is the mechanism that measures it.

**Independent Test**: push a branch with a placeholder connector test and confirm the run shows the
rebuild check plus nine results named `iris-<track>-<login>`; then push a change that breaks one
cell and confirm only that cell fails and the other eight still report.

**Acceptance Scenarios**:

1. **Given** a push or pull request, **When** CI runs, **Then** it reports the rebuild check and nine
   independent results named `iris-latest-em-admin` … `iris-latest-preview-reader_dict`.
2. **Given** a failure in one cell, **When** CI runs, **Then** the remaining cells still run to
   completion and report their own result.
3. **Given** a failure only on `latest-preview`, **When** the reviewer looks at the pull request,
   **Then** the failure is visible and the pull request is still mergeable.
4. **Given** a change that makes the connector files no longer rebuild cleanly onto the pinned
   OpenMetadata release, **When** CI runs, **Then** the rebuild check fails before any cell runs.
5. **Given** the community IRIS dialect present in a cell's environment, **When** CI runs, **Then**
   that cell fails with a message naming the forbidden package.
6. **Given** each cell, **When** it finishes, **Then** its report shows the IRIS version and image
   identity it ran against, so two tracks pointing at the same image are recognizable.

---

### User Story 3 - Tests know their cell; one command runs one cell locally (Priority: P2)

A test author writes an integration test once. The shared test fixture tells the test which cell it
runs in: release track, login, user name, whether the login is an administrator, and whether it can
read the class dictionary. It also gives ready connections for that login and for the
administrator. The author branches expectations on these facts instead of creating users or data. A
developer runs the integration tests for one chosen cell locally with one documented command.
Upstream maintainers run the same tests with no IRIS address configured, and the tests start a
single IRIS instance themselves.

**Why this priority**: it removes per-spec setup code, keeps tests consistent across specs, and is
what makes the connector's tests runnable inside the upstream project.

**Independent Test**: run the placeholder test locally for `latest-em` as `reader`, then with no IRIS
address configured, and confirm both pass and report the expected cell.

**Acceptance Scenarios**:

1. **Given** an IRIS address, track and login supplied to the test run, **When** a test asks the
   shared fixture for its cell, **Then** it receives that track and login, the matching user name, and
   correct administrator and dictionary-grant flags.
2. **Given** a reachable IRIS instance, **When** the developer runs the documented one-cell command
   with a chosen track and login, **Then** the integration tests run for exactly that cell.
3. **Given** no IRIS address configured, **When** the integration tests run, **Then** they start one
   `latest-em` IRIS instance, prepare it (unexpire, load fixtures), run, and remove it afterwards.
4. **Given** a test that does not apply to the current cell, **When** it runs, **Then** it is
   reported as skipped with a reason that names the cell; it never passes silently.
5. **Given** the placeholder connector test, **When** it runs in any cell, **Then** a basic query
   succeeds for the cell's login, and reading the class dictionary succeeds exactly when the cell's
   dictionary-grant flag is true.

---

### User Story 4 - A gap report exists from day one (Priority: P3)

A developer who finds a missing or wrong behavior in IRIS, its driver or dialect, dbt-iris or
OpenMetadata records it in one place, in a fixed format, instead of working around it in code.

**Why this priority**: the constitution (Principle V) requires limitations to be recorded, and every
later spec appends entries. The file and its format must exist before the first spec needs it.

**Independent Test**: open the gap report and confirm it states the entry format and contains the
known entries, each with a reproduction runnable against the shared fixtures.

**Acceptance Scenarios**:

1. **Given** the repository, **When** a developer opens the gap report, **Then** it documents the
   entry format (component, affected tracks, spec, reproduction, expected, actual, connector
   behavior, user workaround, upstream link).
2. **Given** the gap report, **When** a developer reads it, **Then** it contains the known entries
   GAP-001 to GAP-008, each with affected tracks filled from evidence (SPIKE-01, SPIKE-06), and
   GAP-009 (schemas without tables are not listed) found while building the fixtures.

---

### Edge Cases

- **Fresh container with expired default passwords**: the documented preparation step unexpires
  them; until it runs, the loader fails with a message saying the instance is not prepared, not a
  generic connection error.
- **IRIS still starting**: the instance can report itself running before it accepts logins, and its
  container health status can lag behind. The loader and the automatic single-instance start wait
  for a successful administrator login, up to a bounded time, then fail with a clear message.
- **Two tracks resolve to the same image** (as of 2026-11-25, `latest-preview` equals `latest-cd`):
  both cells still run and report separately; the version shown in each report makes the overlap
  visible.
- **Port already in use on a developer machine**: the IRIS address and port are configurable; the
  documented local command does not assume the default port is free.
- **Leftover objects in the scratch schema** from an interrupted test: the loader empties the scratch
  schema; tests clean up their own objects and never assert on objects they did not create.
- **Rebuild tooling not available yet** (spec 000 not merged): the fixture loader, the IRIS part of
  each cell and the fixture self-check run on their own; the rebuild check and connector tests are
  added once the tooling lands.
- **A least-privilege login used for setup by mistake**: setup and assertions about fixture state use
  the administrator connection only; the behavior under test uses the cell's login.
- **A test needs a new fixture case**: it is added to the shared fixture set (additive only) in that
  spec's change, reviewed by the fixture owner, never created by the test itself.

## Requirements *(mandatory)*

### Functional Requirements

**Fixture set**

- **FR-001**: The project MUST provide exactly one fixture loader, run with one command, that
  recreates the whole fixture set from scratch on any supported IRIS release track and is idempotent.
- **FR-002**: The loader MUST create, in Namespace `USER`, the objects of the fixture catalog v1:
  `Clinic.Patient` (4 columns, primary key, table and column descriptions), `Clinic.Encounter`
  (foreign key to `Clinic.Patient`, bit and long-text columns), `Billing.Patient` (same table name as
  `Clinic.Patient`, 2 columns, primary key and a named unique constraint), `AI.Embedding` (a
  `VECTOR(DOUBLE, 3)` column), the view `Clinic.ActivePatient` over `Clinic.Patient` and
  `Clinic.Encounter`, and a schema `Scratch` that holds no objects after loading; with 2, 1, 1 and 1
  rows in the four tables. Names keep their mixed case exactly. Because IRIS lists a schema in its SQL
  catalog only while it contains at least one table (verified on `latest-em` and `latest-cd`,
  GAP-009), `Scratch` is defined by "no objects, and the administrator can create and drop a table
  in it", not by its presence in the catalog.
- **FR-003**: The loader MUST create two least-privilege logins with test-only credentials:
  `omd_reader` with read access to schemas `Clinic`, `Billing` and `AI` only, and `omd_reader_dict`
  with the same access plus read access to the class dictionary tables the connector and the official
  dialect use. Neither login may write anywhere; `Scratch` is writable by the administrator only.
- **FR-004**: The loader MUST end with a self-check that verifies every object, column count, key,
  description, row count, login and grant from FR-002 and FR-003, including that the plain login is
  refused on the class dictionary and the dictionary-grant login is not, that a write into `Scratch`
  by either least-privilege login is refused, and that the SQL catalog
  reports the VECTOR column as text (GAP-001). Any mismatch MUST fail the run and name the item.
- **FR-005**: The loader MUST take the IRIS address, port, Namespace and administrator credentials
  from configuration (environment), with defaults matching the CI cell setup.
- **FR-006**: The loader and all tests MUST connect only through the official InterSystems driver
  and dialect (Principle II).
- **FR-007**: Changes to the fixture catalog MUST be additive; the catalog version and the objects
  each later spec adds MUST be listed in the fixtures contract.

**CI matrix**

- **FR-008**: CI MUST run on every push and every pull request.
- **FR-009**: CI MUST first check that the connector's overlay and patches rebuild cleanly onto the
  pinned OpenMetadata release and that the rebuild changes nothing in the repository.
- **FR-010**: CI MUST then run nine cells, one per combination of track (`latest-em`, `latest-cd`,
  `latest-preview`) and login (`admin`, `reader`, `reader_dict`), each reported as a separate result
  named `iris-<track>-<login>`; a failing cell MUST NOT cancel the others.
- **FR-011**: Cells on `latest-preview` MUST be informative: their failures are reported but do not
  block merging. Cells on `latest-em` and `latest-cd` MUST block.
- **FR-012**: Each cell MUST start a fresh IRIS instance of its track, prepare it (unexpire default
  passwords, wait until it accepts logins), load the fixtures, and run the fixture self-check tests,
  the connector unit tests and the connector integration tests as the cell's login.
- **FR-013**: Each cell MUST fail if the community IRIS dialect is installed in its environment.
- **FR-014**: Each cell's report MUST show the IRIS version and image identity it ran against.
- **FR-015**: CI jobs MUST NOT require repository secrets and MUST NOT expose credentials to pull
  request code (OpenMetadata `REVIEW.md`, CI credentials rules).

**Test interface**

- **FR-016**: A shared test fixture MUST give every integration test its cell: track, login, user
  name, password, whether the login is an administrator, and whether it can read the class
  dictionary; plus a connection for the cell's login, an administrator connection for setup and
  assertions only, the connector's service-connection settings for the cell, and assurance that the
  fixtures are loaded.
- **FR-017**: CI MUST pass the cell to the tests only through environment configuration (address,
  port, Namespace, track, login); user names and passwords come from the fixture catalog.
- **FR-018**: Tests MUST NOT create IRIS users or datasets of their own; objects created during a test
  go in `Scratch`, are removed by the test, and are never asserted on by other tests.
- **FR-019**: A test that does not apply to a cell MUST skip with a reason naming the cell.
- **FR-020**: When no IRIS address is configured, the integration tests MUST start one `latest-em`
  instance themselves, prepare it, load the fixtures, and remove it at the end.
- **FR-021**: A developer MUST be able to run the integration tests for one chosen track and login
  locally with one documented command.
- **FR-022**: A placeholder connector test MUST run in every cell: a basic query as the cell's login,
  and a check that reading the class dictionary succeeds if and only if the cell's dictionary-grant
  flag is true. Any track that behaves differently is recorded in the gap report.

**Gap report and documentation**

- **FR-023**: The repository root MUST contain `GAP-REPORT.md` with the entry format, entries
  GAP-001 to GAP-008 from the gap-report contract (affected tracks filled from SPIKE-01 and SPIKE-06
  evidence), and GAP-009 found in this spec: a schema without tables is not listed in
  `INFORMATION_SCHEMA.SCHEMATA`, so a schema whose last table is dropped disappears from the catalog
  (input for spec 002's mark-deleted behavior).
- **FR-024**: The repository README MUST have a "Running tests" section covering the one-cell local
  command, the automatic single-instance mode, and the fixture loader.
- **FR-025**: The fixtures and test-matrix contracts in `is-omd` MUST be updated to match what was
  built, with no open `[VERIFY]` markers in the test-matrix contract.

### Key Entities

- **Release track**: one IRIS Community image tag (`latest-em`, `latest-cd`, `latest-preview`), its
  IRIS version at run time, and whether it blocks merging.
- **Login**: one of `admin`, `reader`, `reader_dict`; maps to an IRIS user, a password, an
  administrator flag and a dictionary-grant flag.
- **Cell**: one track × one login; the unit CI reports and tests branch on.
- **Fixture catalog**: the versioned list of schemas, objects, rows, logins and grants the loader
  creates and the self-check verifies; additive only.
- **Gap entry**: one recorded IRIS, driver, dialect, dbt-iris or OpenMetadata limitation, in the
  fixed format, with a reproduction against the fixture catalog.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a fresh IRIS instance of each of the three tracks, the fixture set is loaded and
  verified in under 2 minutes from instance start (image download excluded), and a second run
  produces the same verified state.
- **SC-002**: 100% of pushes and pull requests show the rebuild check and nine separately named cell
  results.
- **SC-003**: The placeholder test passes on all six blocking cells; the three informative cells
  report a result.
- **SC-004**: A full CI run, rebuild included, finishes in under 15 minutes of wall-clock time.
- **SC-005**: A developer with the one-time setup done runs one chosen cell locally with a single
  documented command, and the integration tests also pass with no IRIS address configured.
- **SC-006**: Installing the community dialect in a cell makes that cell fail every time.
- **SC-007**: The gap report contains the entry format and 9 entries; each has a reproduction
  runnable against the fixtures, or is marked pending with the spike that will provide it (GAP-003,
  SPIKE-03).
- **SC-008**: No integration test in the repository creates IRIS users or datasets outside the fixture
  loader (verified at review).

## Assumptions

- CI runs on GitHub-hosted Linux runners and the IRIS Community images are pulled without
  authentication (verified in SPIKE-06).
- The dev repository becomes public as planned. While it is private, each full run costs about 14
  billed Actions minutes for the cells alone (SPIKE-06); the rebuild adds to that.
- The rebuild tooling (`om-import` / `om-export`) and the connector package skeleton come from spec
  000. Until they merge, the fixture loader, IRIS preparation and fixture self-check are built and run
  first; the rebuild check and connector tests are wired in when 000 lands.
- No OpenMetadata server is needed for this spec's tests; end-to-end tests against a server are out
  of scope.
- The two least-privilege logins and their grants follow the fixtures contract as of 2026-11-25; the
  exact minimal dictionary grant is settled by SPIKE-03 (spec 004/005), and `omd_reader_dict` keeps
  both dictionary grants until then.
- Credentials in the fixture catalog are for throwaway containers only and are never reused
  elsewhere.
- Release tracks move over time; versions recorded in contracts are dated, not fixed.

## Out of Scope

- Feature tests themselves; each spec adds its own tests to the matrix.
- End-to-end tests against an OpenMetadata server in CI (possible later).
- Fixture cases owned by later specs (`Types.AllTypes` 003, second VECTOR column 004,
  `Restricted.Secret` 005, ≥ 50 rows 006, query-log table 010); this spec only creates `Scratch`.
