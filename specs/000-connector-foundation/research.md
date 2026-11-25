# Research: Connector Foundation

This file records the decisions taken from SPIKE-01 (OpenMetadata 2.1.1, IRIS 2026.1 `latest-em`,
`intersystems-irispython` 5.4.1, `sqlalchemy-intersystems-iris` 1.0.2) and the evidence that matters.

## Decisions

### 1. Base version and working tree
- **Decision**: OpenMetadata 2.1.1 in `openmetadata.version`; shallow clone of the tag into git-ignored `.om/`, re-cloned when the version file changes.
- **Rationale**: SPIKE-01 §1. ADR-0014.
- **Alternatives**: a fork (only for the upstream PR); a git submodule (carries a full tree and hides our own diff).

### 2. Round trip
- **Decision**: `om-import` = clone-if-stale → copy `overlay/` → `git apply patches/*.patch` → `make install_dev generate` in `.om/ingestion` (Python 3.11). `om-export` = `git status --porcelain` in `.om/`; untracked files copied to `overlay/`, modified tracked files to `patches/<path with / as __>.patch` via `git diff`; a deleted file is an error. `om-check` = both, then `git diff --exit-code overlay patches`.
- **Rationale**: small shell targets, no extra tooling (user constraint, constitution). Idempotence comes from regenerating patches deterministically and from not exporting generated or ignored files.
- **Alternatives**: rsync of the whole tree (captures generated files); quilt/stgit (new dependency).
- **Watch-outs to settle in tasks**: exclude generated output (models, `.nox`, venv, build dirs) from `om-export` through `.om`'s own ignore rules; `git apply` must be a no-op when the patch is already applied (use a clean checkout of tracked files before applying, or `--check`/reverse check).

### 3. Scaffold, then hand registration
- **Decision**: run `metadata scaffold-connector --name iris --service-type database --connection-type sqlalchemy --scheme iris --default-port 1972 --auth-types basic --capabilities metadata lineage profiler` once inside `.om/`, then edit and export. The scaffold creates only new files, so registration is manual: `databaseService.json` (`enum`, `javaEnums`, `oneOf`), `setup.py` extra, `uv.lock`, UI registration.
- **Rationale**: SPIKE-01 §4 (the scaffold docs mention only the enum; `javaEnums` is also required).
- **Alternatives**: writing every file by hand (drifts from the scaffold's conventions).

### 4. `uv.lock`
- **Decision**: `om-import` runs `uv lock` after applying patches, and the repository does not store a `uv.lock` patch unless `uv lock` proves non-deterministic across machines (then store the patch).
- **Rationale**: a stale lock makes `install`/`generate` refuse to run (SPIKE-01 §2); a lock patch for a large lock file is noisy and conflicts on every OpenMetadata bump.
- **Open**: confirm determinism during implementation; record the result here.

### 5. Connection schema and URL
- **Decision**: schema: required `username`, `hostPort`, `namespace`; `authType` basicAuth; `sslConfig` present; no `databaseName`/`databaseSchema`; default `schemaFilterPattern` excludes `^%`, `^INFORMATION_SCHEMA$`, `^Ens`. Own `get_connection_url()` producing `iris://user:pwd@host:port/<namespace>`.
- **Rationale**: the common builder would put `databaseSchema` in the URL as the Namespace (SPIKE-01 §3). ADR-0004, ADR-0009.

### 6. Dialect presets
- **Decision**: ADR-0015. One function in `connection.py`, run once at engine creation: `server_version_info` from `SELECT $ZVERSION` (parsed), `_dictionary_access` from a real `SELECT TOP 1 Name FROM %Dictionary.PropertyDefinition` probe. Unit-tested with a fake DB-API connection (version strings of the three tracks; probe success and failure). GAP-004 and GAP-005 entries and upstream issues are listed in `GAP-REPORT.md`.
- **Alternatives**: require `%Native_ClassExecution` and a dictionary grant (breaks least privilege); wait for a dialect fix.

### 7. Test connection
- **Decision**: five steps `CheckAccess`, `GetSchemas`, `GetTables`, `GetViews`, `GetClassDictionary` (last two non-mandatory), definition in `testConnections/database/iris.json` replacing the scaffold's `GetQueries`; the `CheckAccess` message tells the user to check credentials because the driver reports a bad password as `<COMMUNICATION LINK ERROR> … Invalid Message received`. Expected results per login are in `data-model.md`.
- **Rationale**: SPIKE-01 §5.

### 8. Server and ingestion images
- **Decision**: `make om-image` builds, from `.om/`, the OpenMetadata server (Maven for `openmetadata-spec` + `openmetadata-service`, yarn for the UI) and ingestion images with the `iris` extra, in Docker. Model generation uses the containerized ANTLR 4.9.2 wrapper (checksum-verified jar on `eclipse-temurin:21-jre`), so no local JDK.
- **Rationale**: a stock 2.1.1 server rejects `Iris` and has no Iris test-connection definition (SPIKE-01 §6). Image tags and any registry push are out of this spec.
- **Alternatives**: custom image built once by hand (not reproducible); override test connection in the source (spike-only hack).

### 9. Licensing and headers
- **Decision**: repository root Apache-2.0 (existing `LICENSE`); `overlay/ingestion/LICENSE` holds the Collate Community License 1.0 text copied from OpenMetadata's `ingestion/LICENSE` at the pinned tag; every Python file under `overlay/ingestion/` carries OpenMetadata's license header. Driver and dialect are never vendored (ADR-0003).

### 10. Missing-extra behavior
- **Decision**: importing `iris` connector code without the `iris` extra fails with OpenMetadata's standard missing-extra message (as for other optional-driver plugins); the unit test asserts it and that `pip install` without the extra does not pull `intersystems-irispython`.

## Open verification items (to be closed during implementation, with evidence added here)

| # | Item | How |
|---|---|---|
| V1 | Exact UI files for registration (`DatabaseServiceUtils.tsx`, service-type constants, locale files) | Follow the scaffold's `CONNECTOR_CONTEXT.md` on 2.1.1 and record the final file list here |
| V2 | Icon source and licence | Choose an icon we may redistribute; record its source and licence next to the file and in the README. Not decided yet, do not copy a logo without a licence |
| V3 | `uv lock` determinism (decision 4) | Run twice on two machines/containers |
| V4 | Idempotence details of `git apply` and the export filter (decision 2) | Covered by the `om-check` acceptance test |
| V5 | Generated TS for the new connection schema: which generated files are committed upstream and so need export | Inspect `git status` in `.om/` after `make generate` and UI schema generation |

## Implementation findings (2026-11-25)

- **Round trip (V4, T004–T008)**: `scripts/om-import.sh`, `om-export.sh`, `om-check.sh`, `test-roundtrip.sh`. Import refuses to overwrite unexported work (`FORCE=1` overrides) and never deletes `.om/`. OpenMetadata's `env/`, `.nox/`, generated models and `target/` are git-ignored in the tree, so export sees only our changes. `om-check` compares against a snapshot taken first, so it also works before the files are committed. `ingestion/LICENSE` is exported verbatim through `scripts/om-export-always` (it is unmodified in OpenMetadata, so git alone would not list it).
- **uv pin**: OpenMetadata requires `uv==0.13.4` (`ingestion/pyproject.toml`); `om-import` runs `uv lock` through `uv tool run --from uv==<pin>`. `make generate` is a root Makefile target, not an `ingestion/` one.
- **`uv.lock` (V3, decision 4 revised)**: `uv lock` is deterministic (same SHA-256 twice) and the lock patch is small (about 11 KB), so the repository stores `patches/ingestion__uv.lock.patch`; the `uv lock` step in `om-import` is then a no-op guard. The `all` extra also pulls the driver, as it does for other optional-driver plugins; the core install does not.
- **Presets (decision 6 refined)**: `preset_dialect_state` runs from an SQLAlchemy `do_connect` listener, so it still runs before the first pooled connection but stays lazy: a wrong host or password now fails inside `CheckAccess`, not while the client is built. It is the one function; the listener is a one-line lambda in `_get_client`.
- **Namespace in the URL**: SQLAlchemy does not unquote the database part of the URL, so the Namespace is not percent-encoded (`%SYS` must stay `%SYS`); tested.
- **Step helpers**: the common Test connection helper reads `service_connection.databaseSchema`, which this model does not have, so `connection.py` has its own step functions (tables: first schema passing the schema filter that has a table; views: first schema passing the filter).
- **Scaffold leftovers**: `lineage.py` and `query_parser.py` were removed from the scaffold output (spec 002 owns lineage); `service_spec.py` uses `DefaultDatabaseSpec` with the metadata source and connection only.
- **V1 UI registration files (OpenMetadata 2.1.1, confirmed; paths under `openmetadata-ui/src/main/resources/ui/`)**:
  - hand edits: `src/utils/DatabaseServicePureUtils.ts` (connection schema loader for `DatabaseServiceType.Iris`), `src/utils/EntityUtils.interface.ts` (`FormattedDatabaseServiceType.Iris`), `src/utils/ServiceIconUtils.ts` (icon map), `src/assets/img/service-icon-iris.svg`;
  - regenerated (done, exported as patches/overlay): `public/jsons/connectionSchemas/connections/database/irisConnection.json` (new), `public/jsons/connectionSchemas/connections/serviceConnection.json`, `src/jsons/ingestionSchemas/{workflow,testSuitePipeline}.json`, `src/generated/entity/services/connections/database/irisConnection.ts` (new) and 15 existing `src/generated/**` files that list the service types; `make om-ui-codegen` reproduces them in a Node container;
  - no locale file is needed.
- **V2 icon (resolved)**: `service-icon-iris.svg` is an original placeholder (three concentric circles) drawn for this repository, not derived from any InterSystems asset or logo. Licence: Apache-2.0, same as the repository root. Source and licence are recorded in `service-icon-iris.LICENSE.md` next to the file and in the README. Replace it only with an asset whose licence permits redistribution.
- **Integration results (T029, T030)**: on IRIS Community `latest-em` (2026.1.0.234), seeded with the SPIKE-01 fixtures, `IRIS_LOGIN=admin|reader|reader_dict` each pass 7/7 tests (`reader`: dictionary step reported as not passed with the grant hint; wrong password, host, port and Namespace fail on `CheckAccess` only). `latest-cd` and `latest-preview` cells arrive with spec 001.
- **US5 (T036)**: `uv pip install --dry-run ./.om/ingestion` lists no InterSystems package; with `[iris]` it lists `intersystems-irispython==5.4.1` and `sqlalchemy-intersystems-iris==1.0.2`.
- **Masking gap (T042)**: the Java server masks passwords only for connection classes registered in `ClassConverterFactory`. Without an entry the Iris password came back in clear from the API while a Postgres service was masked. Fixed with `IrisConnectionClassConverter` (basic auth and SSL config), spotless-formatted; verified after rebuilding the images (Iris and Postgres both return `*********`).
- **Images (T022)**: `make om-image` builds in Docker: Maven with Python 3 and a containerized-ANTLR shim for the UI's `js-antlr`, then the server and ingestion images (`openmetadata-iris/openmetadata-{server,ingestion}:2.1.1-iris`, ingestion built with `INGESTION_DEPENDENCY=iris`). It runs out of memory (exit 137) if the stack is running at the same time on an 8 GB Docker VM: stop it first. First run: Maven about 8 minutes, UI included.
- **UI generated files (T020, T021)**: the Maven UI build does not refresh the committed generated files. `yarn parse-schema` (run as `node parseSchemas`) added `public/jsons/connectionSchemas/connections/database/irisConnection.json` and updated `serviceConnection.json` and `src/jsons/ingestionSchemas/{workflow,testSuitePipeline}.json`; `json2ts-generate-all.sh -l true` (needs `jq` and Python 3 in the Node container) updated 15 files and added `src/generated/entity/services/connections/database/irisConnection.ts`. Both runs only touched Iris-related lines; Prettier and ESLint pass on the three edited utils files.
- **UI check (T024, T031)**: on the overlay-built stack (Postgres, Elasticsearch, server, ingestion) the add-service page lists the connector with its icon; the form shows Username, Host and Port, Namespace, authentication (password) and advanced options. Test connection as `omd_reader`: connect, schemas, tables and views pass, and the class dictionary step shows a warning (the overall banner reads "partially successful"). Through the automation API: `admin` and `reader_dict` pass all five steps, `reader` fails only the optional dictionary step, a wrong password or Namespace fails `CheckAccess` with the "Check host, superserver port, Namespace, username and password" message.
- **Display name (open)**: the connector card and form show "Iris" (derived from the service type enum), not "InterSystems IRIS". `FormattedDatabaseServiceType.Iris = 'InterSystems IRIS'` is added, but the add-service list does not use it. A label override would need more UI edits; decide whether it is worth the patch weight.
- **Workflow (T033, T034)**: `test_workflow.py` against the overlay-built server passes: service `iris_test_000` (type Iris) and Database `iris_test_000.USER`, with the password masked and absent from the logs. The schema filter matches nothing, so no tables are ingested (spec 002 owns that).
- **Generated UI files are not exported (decision)**: `src/generated/**`, `src/jsons/ingestionSchemas/*` and `public/jsons/connectionSchemas/**` (19 paths for Iris) are excluded from `om-export` through `scripts/om-export-ignore`, so `patches/` keeps only real edits. `make om-import` regenerates them after applying the patches (`scripts/om-ui-codegen.sh`, Node container; `OM_SKIP_UI_CODEGEN=1` skips it for quick loops), so `om-check` has nothing to compare for them. `om-branch` (spec 009) regenerates them in the OpenMetadata fork before the upstream PR, where OpenMetadata expects them committed.
- **Real patches kept (7)**: `ingestion/setup.py` (the `iris` extra), `ingestion/uv.lock`, `databaseService.json` (enum, `javaEnums`, `oneOf`), `ClassConverterFactory.java` and the three UI utils (`DatabaseServicePureUtils.ts`, `EntityUtils.interface.ts`, `ServiceIconUtils.ts`).
- **Why `ClassConverterFactory.java` needs a patch**: the server masks and unmasks credentials by looking up each connection class in the static map of `ClassConverterFactory`; there is no plugin hook and no fallback for unknown classes. The new `IrisConnectionClassConverter` (an overlay file) therefore does nothing until one `Map.entry(IrisConnection.class, ...)` line and its import are added to that map. Without them the API returned the password in clear (T042).
