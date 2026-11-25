# Research: Test harness (shared fixtures + CI matrix)

**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Date**: 2026-11-25 (revised after
spec 000's PR)

This file records the decisions and the evidence that matters for them (constitution 1.2.2). Sources:

- **SPIKE-06** (2026-11-25), summarized below. The CI evidence is run
  [45611684116](https://github.com/musketeers-br/openmetadata-intersystems-iris-connector/actions/runs/45611684116)
  in this repository's Actions history (throwaway branch, deleted after the run).
- **SPIKE-01** (spec 000's evidence for GAP-004..008).
- **Probes made while planning** (R3, R6, R9, R10), run against `latest-em` and `latest-cd` on
  2026-11-25.
- **Spec 000's branch** (`000-connector-foundation`, PR #11), built locally on WSL2 on 2026-11-25
  (R7, R16).

No `NEEDS CLARIFICATION` remained in the Technical Context.

## SPIKE-06 outcome

Environment: GitHub-hosted `ubuntu-latest`; local WSL2 Ubuntu 24.04 with Docker 29.8;
`intersystems-irispython` 5.4.1; Python 3.11; `testcontainers` 4.8.

- **The mechanics work on all three tracks.** One job per tag × login (9 cells) plus a
  testcontainers job were all green on the first run: 82 s wall time, 48–77 s per job.
- **Step times in CI** (seconds): image pull 25–45 (image ≈ 3.6 GB; local first pull 85–99), start
  to `running` 9–22 (local 5–8), unexpire ≤ 1, seed ≈ 1, tests ≤ 2. Caching the image is not worth it.
- **No behavior difference between tracks.** Same seed, grants, errors and dictionary output.
  `reader` gets `SQLCODE -99` on both `%Dictionary.CompiledProperty` and
  `%Dictionary.PropertyDefinition`; `reader_dict` and `admin` read both. VECTOR is reported as
  `varchar` in `INFORMATION_SCHEMA.COLUMNS` on every track (GAP-001), and
  `%Dictionary.CompiledProperty` returns `Type=%Library.Vector` with `DATATYPE,DOUBLE` and `LEN,3`.
- **Fallback**: with `IRIS_HOST` unset, a generic testcontainers `DockerContainer` started
  `latest-em`, was unexpired, seeded and tested: 40 s in CI, 12 s locally with the image cached.
- **Cost while the repository is private**: 586 s of runner time, **14 billed minutes per run**
  (each job rounds up to a whole minute; 4 jobs ran over 60 s). About 140 runs a month on a
  2,000-minute plan. Free once the repository is public.
- **Images as of 2026-11-25**: `latest-em` = 2026.1.0.234.1 (rebuilt 2026-11-19); `latest-cd` and
  `latest-preview` are the same image, 2026.3.0.212.0 (digest `7c9cbbc6a06e`). Tags move, so
  versions are read at run time and dated wherever they are written down.
- **Surprises that shaped decisions**: Docker's healthcheck lags behind readiness (R2); Windows
  checkouts turn scripts into CRLF (R14); `pull_request` jobs must run without secrets and with
  `persist-credentials: false` (OpenMetadata `REVIEW.md`).

## R1 — Start IRIS with `docker run`, not `services:`

- **Decision**: each cell starts its IRIS with `docker run -d --name iris -p 127.0.0.1:1972:1972
  <image> --check-caps false` in a step (`start-iris.sh`, R2).
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
  (SPIKE-06). The unexpire command is identical on all three tracks. One script keeps CI and local
  runs identical (FR-012).
- **Alternatives**:
  - waiting on Docker health — rejected, it lags;
  - a sleep — rejected, it is flaky by construction (`REVIEW.md`).

## R3 — One canonical loader under `overlay/…/integration/iris/data/seed.py`

- **Decision**: the fixture catalog (DDL, rows, logins, grants), the loader and the self-check are
  one Python module that imports only `iris`, at
  `overlay/ingestion/tests/integration/iris/data/seed.py` (Collate Community License header).
  - `fixtures/iris/seed.py` (Apache-2.0) is the documented command. It runs the `.om/` copy when
    `.om/` exists, because developers edit there, and the `overlay/` copy otherwise
    (`runpy.run_path`), so the plain venv works without `.om/`.
  - The integration conftest imports the same module for the testcontainers fallback.
- **Rationale**: the upstream PR carries only overlay files. The fallback (FR-020) must seed from
  inside the OpenMetadata tree, and FR-001 forbids two loaders. Upstream connectors keep test data
  under their integration package (`tests/integration/mysql/data/`).
- **Alternatives**:
  - loader only in `fixtures/iris/` — rejected, upstream cannot seed;
  - a copy in both places — rejected, they would drift;
  - plain SQL files — rejected, logins, grants and the self-check need code.
- **ADR impact**: ADR-0012 says "Spec 001 creates it in `fixtures/iris/seed.py`". It is updated to
  "entry point `fixtures/iris/seed.py`; source `overlay/ingestion/tests/integration/iris/data/seed.py`"
  in the same change (FR-026).

## R4 — Engines come from the connector's `IrisConnection`

- **Decision**: `iris_engine` and `iris_admin_engine` are
  `metadata.ingestion.source.database.iris.connection.IrisConnection(config).client`, where `config`
  is the generated model `IrisConnection` (`hostPort`, `username`, `authType=BasicAuth(password=…)`,
  `namespace`) built from the cell. `iris_service_connection` is that model.
- **Rationale**: the official dialect cannot connect or reflect as a least-privilege login without
  the ADR-0015 presets (GAP-004, GAP-005). Spec 000 applies them in `IrisConnection._get_client` on
  the engine's `do_connect` event. Building a raw `create_engine("iris://…")` in the conftest would
  either fail for `reader` or duplicate the presets, which the constitution forbids. The connector's
  own path is also what tests should exercise.
- **Alternatives**:
  - a raw engine — rejected, it fails for `reader` and `reader_dict`;
  - presets inside the conftest — rejected by Principle V and ADR-0015;
  - the driver's `iris.connect` for integration tests — rejected, it bypasses the dialect the
    connector uses. It stays the tool for the loader and fixture tests.

## R5 — Fixture tests run in a plain venv; connector tests run in `.om/env`

- **Decision**: `fixtures/iris/test_*.py` need only `intersystems-irispython` and `pytest`
  (`pip install`, ≈ 3 s in CI). Connector unit and integration tests run in `.om/env`, the
  environment `make om-import` builds.
- **Rationale**: OpenMetadata's root integration `conftest.py` imports generated models and
  `_openmetadata_testutils`, so connector tests need the built tree. The fixture tests must give a
  verdict on the fixtures even when the rebuild fails, and they run in seconds.
- **Alternatives**: running everything in `.om/env` — rejected, a broken rebuild would hide whether
  the fixtures are right.

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

  A `find_spec('sqlalchemy_iris')` check alone misses the entry-point clash.
- **Alternatives**: only the module check — kept as a sub-check, not sufficient alone.
- **Test**: quickstart Q5 and one CI run install `sqlalchemy-iris` in a throwaway environment to show
  the guard fails. The package is installed only for that purpose and never imported (Principle II).

## R7 — `.om/` environment, round-trip job and cache

- **Facts** (spec 000's branch, built 2026-11-25):
  - `make om-import` installs OpenMetadata's `dev` profile into `.om/env` (`make install_dev`). The
    `.om/.venv` it also creates stays empty. The `dev` profile has neither the `iris` extra
    (`intersystems-irispython`, `sqlalchemy-intersystems-iris`) nor `testcontainers`, so the unit
    test that checks the dialect version skips and the integration tests cannot connect.
  - With `OM_SKIP_UI_CODEGEN=1`, `om-import` on an existing `.om/` takes 16 s and `om-check` 15 s;
    `.om/env` is 1.1 GB and the whole tree 2.6 GB (with the UI's `node_modules`).
- **Decision**:
  - 001 adds `make om-test-deps`: installs the `iris` extra and `testcontainers` into `.om/env` at
    the versions pinned in `ingestion/setup.py` and OpenMetadata's test profile. If spec 000 changes
    `om-import` to install them, the target only checks that they are present.
  - Job `overlay-roundtrip` runs `OM_SKIP_UI_CODEGEN=1 make om-import` and then
    `OM_SKIP_UI_CODEGEN=1 make om-check`, so the rebuild runs twice on a Linux runner (catches
    root-owned files, R16). All cells `needs:` it.
  - Each cell runs `OM_SKIP_UI_CODEGEN=1 make om-import` and `make om-test-deps` itself, with
    `actions/cache` on the uv download cache and `.cache/` (ANTLR jar), keyed on
    `hashFiles('openmetadata.version','patches/**','scripts/**','Makefile')`. `.om/` itself is not
    cached at first (2+ GB per entry against a 10 GB repository limit).
- **Rationale**: generated UI files are never exported (`scripts/om-export-ignore`), so skipping the
  UI codegen cannot change what `om-check` compares, and it avoids a Node container per job.
- **Alternatives**:
  - caching `.om/` — kept as the first optimization if SC-004 (under 15 min) is missed;
  - building `.om/` once and sharing it as an artifact — fallback if the cache is too slow.
- **Open for implementation**: cold `om-import` time on a runner, measured on the first CI run.

## R8 — Blocking vs informative cells

- **Decision**:
  - job-level `continue-on-error: ${{ matrix.tag == 'latest-preview' }}` and
    `strategy.fail-fast: false`;
  - after the repository is public, branch protection on `main` requires `overlay-roundtrip` and the
    six `iris-latest-em-*` / `iris-latest-cd-*` checks only.
- **Rationale**: FR-011 ("informative") is guaranteed by which checks are required, not only by
  `continue-on-error`. Branch protection on a private repository needs a paid plan, which is one more
  reason to go public on Day 1.
- **Duplicate tracks**: as of 2026-11-25, `latest-preview` and `latest-cd` are the same image. The
  cells still run (cheap) and each job summary prints the digest and `$ZVERSION` (FR-014).

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
  documented collation behavior, not a defect, so it is not a gap entry.

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
  It would be ingested by every metadata test, and "empty" is what ADR-0012 promises.

## R11 — Test interface in the integration conftest

- **Decision**:
  - session fixtures `iris_cell`, `iris_engine`, `iris_admin_engine`, `iris_service_connection` and
    `seeded`, as in `contracts/test-interface.md`;
  - marker `iris` registered in `pytest_configure` (`config.addinivalue_line("markers", …)`), because
    OpenMetadata's `pyproject.toml` marker list does not include it, and patching `pyproject.toml`
    for one marker is not worth a patch file;
  - `seeded` does not reload in CI. It runs the self-check as admin and fails if it does not pass,
    because loading is a separate CI step. In fallback mode the fixture loads first.
- **Rationale**: ADR-0012's fixture names plus upstream conventions. Upstream's root conftest
  auto-groups tests per package for xdist (`iris_suite`) and retries transient image pulls, and both
  work for us unchanged.
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

## R13 — Makefile targets (a section in spec 000's Makefile)

- **Decision**: a section `# --- 001: test harness ---` with these targets:
  - `om-test-deps` (R7);
  - `iris-up TAG=latest-em PORT=11972` (runs `start-iris.sh`, container `omd-test-iris-<tag>`);
  - `iris-seed` (runs `fixtures/iris/seed.py` against `PORT`);
  - `iris-down`;
  - `test-cell TAG=… LOGIN=… [PORT=11972]`, which runs `iris-up` and `iris-seed`, then
    `IRIS_HOST=127.0.0.1 IRIS_PORT=… IRIS_TAG=… IRIS_LOGIN=… .om/env/bin/python -m pytest
    .om/ingestion/tests/integration/iris -m iris -rs`.
- **Rationale**:
  - the default local port is 11972, because host port 1972 is often taken by another IRIS on
    developer machines (seen on 2026-11-25);
  - `127.0.0.1`, not `localhost` (SPIKE-01: OpenMetadata rewrites `localhost`);
  - spec 000's Makefile keeps targets small and puts logic in `scripts/`; 001 follows that.
- **Alternatives**: a separate `test.mk` include — rejected, spec 000 plans a `test-cell` section in
  its Makefile (its make-targets contract).

## R14 — Gap report and line endings

- **Decision**:
  - `GAP-REPORT.md` exists (spec 000: GAP-004, GAP-005). 001 inserts GAP-001..003 and GAP-006..009 in
    id order, in the same entry format, and fills every entry's tracks from the matrix;
  - GAP-003's reproduction is marked "pending SPIKE-03";
  - the `Upstream` field stays "not raised yet" until both developers agree to open an issue;
  - `.gitattributes` (`* text=auto eol=lf`) is added, coordinated with Henry (spec 000 owns
    `.gitignore`).
- **Rationale**: SC-007; and SPIKE-06's CRLF finding (Windows checkouts break scripts under WSL).

## R15 — Spec 000's integration test moves onto the conftest

- **Decision**: `test_connection.py` (spec 000) drops its own `LOGINS` table and `IRIS_*` reading and
  uses `iris_cell` and `iris_service_connection`. Its assertions are unchanged.
  `test_workflow.py` stays as it is: it needs an OpenMetadata server and skips with a reason when
  `OM_HOST_PORT` / `OM_JWT` are unset.
- **Rationale**: the file's docstring already says "spec 001's conftest replaces this ad-hoc
  environment reading". Two login tables would drift (FR-016, FR-025).

## R16 — Findings on spec 000's tooling that the CI depends on

Found while running `make om-import && make om-check` on spec 000's branch on WSL2 (Docker 29.8,
native, not Docker Desktop), 2026-11-25. Reported on PR #11; fixed in spec 000, not here.

- `scripts/antlr4` runs the ANTLR container as root. On Linux, `generated/antlr/` becomes
  root-owned, and the next `make generate` fails (`shutil.rmtree(..., ignore_errors=True)` cannot
  remove it, then `mkdir` raises `FileExistsError`). Running the container with
  `-u "$(id -u):$(id -g)"` fixed it locally: `om-import` and `om-check` then passed.
- `scripts/om-ui-codegen.sh` runs `yarn install --frozen-lockfile` in `node:22-bookworm`, which runs
  the UI's `postinstall` (`build-check` → `js-antlr`) and fails with `antlr4: not found` on a fresh
  clone. The JS parser is already generated by `make generate`, so `--ignore-scripts` avoids it. The
  container also leaves `node_modules` root-owned (≈ 150,000 files).

**Consequence for 001**: GitHub's Linux runners hit the first issue on the second rebuild, which is
exactly what `om-check` does; CI uses `OM_SKIP_UI_CODEGEN=1` (R7).
