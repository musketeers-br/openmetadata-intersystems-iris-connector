# Research: Test harness (shared fixtures + CI matrix)

**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Date**: 2026-11-25

Experiments live in `is-omd`. This file records the decisions and links the evidence instead of
repeating it:

- **SPIKE-06**: `is-omd/spikes/findings/SPIKE-06.md`, with CI run
  [45611684116](https://github.com/musketeers-br/openmetadata-intersystems-iris-connector/actions/runs/45611684116).
- **SPIKE-01**: `is-omd/spikes/findings/SPIKE-01.md`.
- **Probes made while planning** (R3, R6, R9, R10): run against `latest-em` and `latest-cd` on
  2026-11-25. They are noted inline and will be added to SPIKE-06 as an addendum.

No `NEEDS CLARIFICATION` remained in the Technical Context.

## R1 — Start IRIS with `docker run`, not `services:`

- **Decision**: each cell starts its IRIS with `docker run -d --name iris -p 1972:1972 <image>
  --check-caps false` in a step.
- **Rationale**: GitHub `services:` cannot pass the container command (`--check-caps false`). A step
  also gives per-step timing and logs. Proven on all 9 cells (SPIKE-06).
- **Alternatives**:
  - `services:` with `options:` — rejected, no command override.
  - A docker compose file — rejected, an extra layer for one container.

## R2 — Readiness = `iris qlist` running, then unexpire, then admin SQL login

- **Decision**: one script, `fixtures/iris/start-iris.sh TAG [PORT] [NAME]`, does four things, and is
  used by CI, the Makefile targets and documentation:
  - `docker run`;
  - poll `iris qlist` until `running` (≤ 180 s);
  - `iris session IRIS -U %SYS '##class(Security.Users).UnExpireUserPasswords("*")'`;
  - retry an admin SQL login until it succeeds (≤ 120 s).

  It prints the image digest and `$ZVERSION`.
- **Rationale**: the image's Docker healthcheck still says `starting` while SQL logins already work
  (SPIKE-06, surprise 3). The unexpire command is identical on all three tracks. One script keeps CI
  and local runs identical (FR-012).
- **Alternatives**:
  - waiting on Docker health — rejected, it lags;
  - a sleep — rejected, it is flaky by construction (`REVIEW.md`).

## R3 — One canonical loader under `overlay/…/integration/iris/data/seed.py`

- **Decision**: the fixture catalog (DDL, rows, logins, grants), the loader and the self-check are
  one Python module that imports only `iris`, at
  `overlay/ingestion/tests/integration/iris/data/seed.py` (Collate Community License header).
  - `fixtures/iris/seed.py` (Apache-2.0) is the documented command; it runs that module
    (`runpy.run_path`), so the module works without the `.om/` tree.
  - The integration conftest imports the same module for the testcontainers fallback.
- **Rationale**: the upstream PR carries only overlay files. The fallback (FR-020) must seed from
  inside the OpenMetadata tree, and FR-001 forbids two loaders. Upstream connectors keep test data
  under their integration package (`tests/integration/mysql/data/`).
- **Alternatives**:
  - loader only in `fixtures/iris/` — rejected, upstream cannot seed;
  - a copy in both places — rejected, they would drift;
  - plain SQL files — rejected, logins, grants and the self-check need code.
- **Contract impact**: `is-omd/docs/contracts/fixtures.md` says "One loader, `fixtures/iris/seed.py`".
  It will be updated to "entry point `fixtures/iris/seed.py`; source
  `overlay/ingestion/tests/integration/iris/data/seed.py`" (B4).

## R4 — Engines come from the connector's `get_connection`

- **Decision**: `iris_engine` and `iris_admin_engine` are built by calling
  `metadata.ingestion.source.database.iris.connection.get_connection(IrisConnection(...))` with the
  cell's credentials. `iris_service_connection` builds the `IrisConnection` model with these fields:
  - `hostPort`;
  - `username`;
  - `authType.password`;
  - `namespace`.

  The import is lazy. If spec 000's package is not importable, the three fixtures skip with
  "spec 000 connector package not available" plus the cell name.
- **Rationale**: the official dialect cannot connect or reflect as a least-privilege login without
  the ADR-0015 presets (SPIKE-01 blockers A and B; GAP-004, GAP-005). Those presets may exist only in
  `iris/connection.py`. Building a raw `create_engine("iris://…")` in the conftest would either fail
  for `reader` or duplicate the presets, which the constitution forbids. The connector's own path is
  also what tests should exercise.
- **Alternatives**:
  - a raw engine — rejected, it fails for `reader` and `reader_dict`;
  - presets inside the conftest — rejected by Principle V and ADR-0015;
  - the driver's `iris.connect` for integration tests — rejected, it bypasses the dialect the
    connector uses. It stays the tool for the loader and fixture tests.
- **Note**: the skip exists only until 000 merges. After that, an import error is a real failure,
  because Phase B wires the integration step only on a tree where the package exists.

## R5 — Fixture tests run in a plain venv; connector tests run in `.om/`

- **Decision**: `fixtures/iris/test_seed.py` needs only `intersystems-irispython` and `pytest`
  (`pip install`, ≈ 3 s in CI). Unit and integration tests run in the `.om/ingestion` environment.
- **Rationale**: OpenMetadata's root integration `conftest.py` imports generated models and
  `_openmetadata_testutils`, so connector tests need the built tree. The fixture tests must run in
  Phase A, before that tree exists.
- **Alternatives**: running everything in `.om/` — rejected, it blocks Phase A on spec 000.

## R6 — Community-dialect guard checks the distribution and the entry point

- **Decision**: `fixtures/iris/check_dialect.py`, run in every environment that runs tests, fails
  when either of these holds:
  - the distribution `sqlalchemy-iris` is installed;
  - the `sqlalchemy.dialects` entry point `iris` resolves to anything other than
    `sqlalchemy_intersystems_iris.iris:IRISDialect_iris`.
- **Rationale**: probe on 2026-11-25 with `sqlalchemy-intersystems-iris` 1.0.2:
  - the official package's top-level module is `sqlalchemy_intersystems_iris`, with entry point
    `iris = sqlalchemy_intersystems_iris.iris:IRISDialect_iris`;
  - the community package provides module `sqlalchemy_iris` and registers the **same** `iris`
    entry-point name, so it could silently shadow the official dialect.

  The contract's `find_spec('sqlalchemy_iris')` guard is correct but misses an entry-point clash.
- **Alternatives**: only the contract one-liner — kept as a sub-check, not sufficient alone.
- **Test**: quickstart scenario Q5 installs `sqlalchemy-iris` in a throwaway venv and expects a
  non-zero exit, so the guard is shown to be able to fail.

## R7 — Overlay round-trip job and `.om/` cache

- **Decision** (Phase B):
  - job `overlay-roundtrip` runs `make om-import && make om-export && git diff --exit-code overlay
    patches`, and all cells `needs:` it;
  - each cell restores `.om/` from `actions/cache`, keyed on
    `hashFiles('openmetadata.version', 'patches/**', 'Makefile')`, then runs `make om-import`, which
    re-copies `overlay/` and must be idempotent on a warm tree (000's contract).
- **Rationale**: the clone and `make install_dev` are the expensive part and change only with the
  tag, the patches or the tooling. `overlay/` changes every commit, and copying it is cheap.
- **Alternatives**:
  - no cache — kept as fallback if the cache costs more than it saves;
  - build once and share `.om/` as an artifact — fallback if the cache is too large (10 GB per-repo
    limit).
- **Open for implementation**:
  - the cache size and restore time are measured in Phase B against SC-004 (under 15 min);
  - the exact install command (`make install_dev` vs `make install_dev_env`, SPIKE-06 surprise 7) and
    whether it installs the `iris` extra and the test profile (`pytest`, `testcontainers`) come from
    spec 000. 001 writes the command 000 settles into the README and `test-cell`.

## R8 — Blocking vs informative cells

- **Decision**:
  - job-level `continue-on-error: ${{ matrix.tag == 'latest-preview' }}` and
    `strategy.fail-fast: false`;
  - after the repository is public, branch protection on `main` requires `overlay-roundtrip` and the
    six `iris-latest-em-*` / `iris-latest-cd-*` checks only.
- **Rationale**: FR-011 ("informative") is guaranteed by which checks are required, not only by
  `continue-on-error`. Branch protection on a private repository needs a paid plan, which is one more
  reason to go public on Day 1.
- **Duplicate tracks**: as of 2026-11-25, `latest-preview` and `latest-cd` are the same image (digest
  `7c9cbbc6a06e`). The cells still run (cheap) and each job summary prints the digest and `$ZVERSION`
  (FR-014).

## R9 — Self-check reads `INFORMATION_SCHEMA` with exact names, no `GROUP BY` on names

- **Decision**: the self-check queries these views per object, filtered by schema and name with bind
  parameters, and compares the values exactly:
  - `TABLES` (type, `DESCRIPTION`);
  - `COLUMNS` (names, order, `DATA_TYPE`, `DESCRIPTION`);
  - `TABLE_CONSTRAINTS` and `KEY_COLUMN_USAGE` (PK, unique, FK);
  - `REFERENTIAL_CONSTRAINTS` (FK target);
  - `VIEWS`.

  It counts columns by fetching rows, never with `GROUP BY` on names.
- **Rationale**: probe on 2026-11-25 (`latest-em`):
  - all these views exist and return the fixture's constraints with system-generated names
    (`PATIENT_PKEY1`, `ENCOUNTERFKey3`) next to the declared `UqBillingCode`;
  - `GROUP BY TABLE_SCHEMA, TABLE_NAME` returned **`CLINIC`, `PATIENT`**: the default `SQLUPPER`
    collation upper-cases grouped strings.

  The self-check therefore asserts on constraint *type and columns*, not on generated names (except
  `UqBillingCode`), and avoids grouping.
- **Note for spec 002**: any catalog SQL in `queries.py` that groups or uses `DISTINCT` on names must
  use `%EXACT(...)` or avoid grouping, or names lose their case (Principle III). This is IRIS's
  documented collation behavior, not a defect, so it is not a gap entry. It is passed to spec 002 as
  a planning note.

## R10 — `Scratch` schema: create explicitly, verify by behavior

- **Decision**:
  - the loader drops every table in `Scratch`, then runs `CREATE SCHEMA Scratch`;
  - the self-check verifies that no table exists in `Scratch` and that the admin can create and drop
    a probe table there;
  - both least-privilege logins are refused when they INSERT into or create a table in `Scratch`.
- **Rationale**: probes on `latest-em` and `latest-cd`:
  - `CREATE SCHEMA` succeeds and can be repeated;
  - the schema is **not** listed in `INFORMATION_SCHEMA.SCHEMATA` while it has no tables, nor after
    its last table is dropped;
  - a second `DROP SCHEMA` fails with `SQLCODE -473`, so cleanup tolerates it;
  - `reader` and `reader_dict` get `SQLCODE -99` for both INSERT and CREATE TABLE.

  This becomes **GAP-009**.
- **Alternatives**: a permanent placeholder table in `Scratch` so the schema stays listed — rejected.
  It would be ingested by every metadata test, and "empty" is what the contract promises.

## R11 — Test interface in the integration conftest

- **Decision**:
  - session fixtures `iris_cell`, `iris_engine`, `iris_admin_engine`, `iris_service_connection` and
    `seeded`, as in `contracts/test-interface.md`;
  - marker `iris` registered in `pytest_configure` (`config.addinivalue_line("markers", …)`), because
    OpenMetadata's `pyproject.toml` marker list does not include it, and patching `pyproject.toml`
    for one marker is not worth a patch file;
  - `seeded` does not reload in CI. It runs the self-check as admin and fails if it does not pass,
    because loading is a separate CI step. In fallback mode the fixture loads first.
- **Rationale**: the contract table plus upstream conventions. Upstream's root conftest auto-groups
  tests per package for xdist (`iris_suite`) and retries transient image pulls, and both work for us
  unchanged.
- **Alternatives**: registering the marker through a `pyproject.toml` patch — rejected (patch churn).

## R12 — Testcontainers fallback uses the generic `DockerContainer`

- **Decision**: when `IRIS_HOST` is unset, the conftest starts
  `containers.intersystems.com/intersystems/iris-community:latest-em` with
  `DockerContainer(...).with_command("--check-caps false").with_exposed_ports(1972)`. It then:
  - waits as in R2, through `container.exec`;
  - unexpires;
  - runs the R3 loader;
  - yields host and mapped port.

  The container stops at session end.
- **Rationale**: testcontainers has no IRIS module. The generic container worked in SPIKE-06
  (40 s in CI, 12 s locally with the image cached). The fallback runs as `reader` by default
  (`IRIS_LOGIN` still applies).
- **Upstream cost**: a 3.6 GB image pull from `containers.intersystems.com` on a cold runner.
  Upstream's pull-retry fixture covers transient registry errors.

## R13 — Makefile targets (Phase B, inside 000's Makefile)

- **Decision**: a section `# --- 001: test harness ---` with these targets:
  - `iris-up TAG=latest-em PORT=11972` (runs `start-iris.sh`, container `omd-test-iris-<tag>`);
  - `iris-seed` (runs `fixtures/iris/seed.py` against `PORT`);
  - `iris-down`;
  - `test-cell TAG=… LOGIN=… [PORT=11972]`, which runs `iris-up` and `iris-seed`, then
    `IRIS_HOST=127.0.0.1 IRIS_PORT=… IRIS_TAG=… IRIS_LOGIN=… <.om python> -m pytest
    .om/ingestion/tests/integration/iris -m iris`.
- **Rationale**:
  - the default local port is 11972, because host port 1972 is often taken by another IRIS on
    developer machines (seen on 2026-11-25), and SPIKE-01 uses 11972 too;
  - `127.0.0.1`, not `localhost` (SPIKE-01: OpenMetadata rewrites `localhost`);
  - merge order: 000 owns the Makefile and merges first, and 001 rebases its section on top.
- **Alternatives**: a separate `test.mk` include — rejected, the ownership table already plans a
  `test-cell` section in the Makefile.

## R14 — Gap report seed and line endings

- **Decision**:
  - `GAP-REPORT.md` is created at the repository root with the contract's entry format and entries
    GAP-001..008, with affected tracks filled from SPIKE-01 (`latest-em`) and SPIKE-06 (all three
    for GAP-001/002), plus GAP-009 (R10);
  - GAP-003's reproduction is marked "pending SPIKE-03";
  - `.gitattributes` (`* text=auto eol=lf`) is added in Phase A.
- **Rationale**: SC-007; and SPIKE-06 surprise 6 (Windows checkouts turn scripts into CRLF, which
  breaks them under WSL). `.gitattributes` is not in the ownership table, so it is coordinated with
  Henry (000 owns `.gitignore`).
