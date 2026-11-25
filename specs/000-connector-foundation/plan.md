# Implementation Plan: Connector Foundation

**Branch**: `000-connector-foundation` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/000-connector-foundation/spec.md`

## Summary

Register InterSystems IRIS as a database service type in OpenMetadata 2.1.1 without forking it: this
repository holds only `overlay/` (new files), `patches/` (edits, one per file), `openmetadata.version`
and a `Makefile`. `make om-import` rebuilds a working tree in `.om/`, `make om-export` writes edits
back, `make om-check` proves the round trip is a no-op, and `make om-image` builds the server and
ingestion images that know `Iris` (needed for the UI form, UI Test connection and workflow runs).
The connector package starts from the `metadata scaffold-connector` output (SPIKE-01), with its own
Namespace-based URL builder, the ADR-0015 dialect presets in one function, a five-step Test
connection, `IrisSource(CommonDbSourceService)` yielding the Namespace as Database, and the `iris`
install extra. Schemas/tables/columns, type mapping and VECTOR are left as sectioned stubs.

## Technical Context

**Language/Version**: Python 3.11 (ingestion), Java 21 + containerized ANTLR 4.9.2 (model generation), Maven and yarn in Docker (images), POSIX shell + GNU make

**Primary Dependencies**: OpenMetadata 2.1.1 (`openmetadata.version`); `intersystems-irispython==5.4.1` and `sqlalchemy-intersystems-iris==1.0.2` only through the `iris` extra; SQLAlchemy 2.0.x (OpenMetadata's lock); `uv` for the lock; Docker

**Storage**: N/A (the repository holds files only; IRIS and OpenMetadata are external)

**Testing**: pytest. Unit: `overlay/ingestion/tests/unit/topology/database/test_iris.py` (no IRIS, no image). Integration: `overlay/ingestion/tests/integration/iris/test_connection.py` against the IRIS Community image, driven by `IRIS_HOST`/`IRIS_PORT`/`IRIS_LOGIN`. UI and workflow checks run on the overlay-built images

**Target Platform**: macOS and Linux developer machines and coding agents; CI is spec 001

**Project Type**: overlay on a third-party source tree (library/connector + build tooling)

**Performance Goals**: none beyond the framework (constitution: measured problem first). `om-import` is idempotent and skips the clone when the tree is current

**Constraints**: Test connection never leaks credentials; works with SELECT-only logins; no vendored driver; `om-import && om-export` changes nothing; Apache-2.0 root, Collate Community License 1.0 for `overlay/ingestion/` and its patches (license header on every Python file); no AI attribution in commits

**Scale/Scope**: about 10 new connector files, about 4–6 patches (`databaseService.json`, `setup.py`, `uv.lock`, UI utils and locale), 3 make targets plus `om-image`, one README stub

## Constitution Check

*Constitution v1.2.1. Gate before Phase 0; re-checked after Phase 1 design.*

| Gate | Result |
|---|---|
| I. Framework First: `IrisSource` extends `CommonDbSourceService`, `DefaultDatabaseSpec`, shared test-connection helpers; only `get_database_names()` and the URL builder are IRIS-specific | Pass |
| II. Official Driver Only: official driver and dialect only, pinned, never vendored; no JDBC/ODBC/`sqlalchemy-iris` | Pass |
| III. IRIS Fidelity: one Namespace per service, Database named after it verbatim; `(schema, name)` identity untouched here; type map stub only | Pass |
| IV. Least Privilege: every step works with SELECT-only logins; dictionary step optional with a hint | Pass |
| V. Nothing Silent: only the ADR-0015 presets, one function in `iris/connection.py`, unit-tested, GAP-004/GAP-005 with upstream issues; no other workaround. Dictionary-step failure is a visible hint | Pass (narrow exception, conditions met) |
| VI. Tested on the Matrix: unit and integration tests ship with this spec; the full 3-track matrix is spec 001, this spec runs on the Community image and uses the shared fixtures only | Pass (matrix CI deferred to 001 by scope) |
| VII. Upstream-Ready: `make py_format` and `mvn spotless:apply` on touched modules inside `.om/` before `om-export` | Pass |
| VIII. English Artifacts | Pass |
| Licensing: license header on overlay Python files; ingestion LICENSE text under `overlay/ingestion/` | Pass (task) |
| Images: end-to-end uses `make om-image`; connector tests do not depend on it | Pass |
| Paths: `overlay/<path>` and `patches/<path with / as __>.patch`; `om-export` before commit | Pass |

No violations, so the Complexity Tracking table stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/000-connector-foundation/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── make-targets.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks, not created here
```

The connection fields, the Test connection steps and their expected results per login are defined in
`data-model.md`; the overlay layout and patch naming in ADR-0014 (`docs/adr/0014-repository-topology.md`);
the test-cell variables in ADR-0012 (`docs/adr/0012-shared-fixtures-and-matrix.md`).

### Source Code (repository root)

```text
.gitignore                                  # adds .om/
openmetadata.version                        # 2.1.1
Makefile                                    # om-import, om-export, om-check, om-image
README.md                                   # stub
scripts/                                    # small shell helpers behind the targets, antlr4 wrapper
overlay/
├── ingestion/
│   ├── LICENSE                             # Collate Community License 1.0 text
│   ├── src/metadata/ingestion/source/database/iris/
│   │   ├── __init__.py  connection.py  metadata.py  service_spec.py  queries.py  types.py
│   └── tests/
│       ├── unit/topology/database/test_iris.py
│       └── integration/iris/test_connection.py
├── openmetadata-spec/src/main/resources/json/schema/entity/services/connections/database/irisConnection.json
├── openmetadata-service/src/main/resources/json/data/testConnections/database/iris.json
└── openmetadata-ui/...                     # icon + generated TS, paths confirmed in research.md
patches/
├── ingestion__setup.py.patch               # iris extra
├── ingestion__uv.lock.patch                # or `uv lock` inside om-import (research decision 4)
├── openmetadata-spec__...__databaseService.json.patch   # enum + javaEnums + oneOf
└── openmetadata-ui__...__DatabaseServiceUtils.tsx.patch (+ locale), confirmed in research.md
```

**Structure Decision**: overlay-and-patches repository per ADR-0014. Everything under `overlay/` and
`patches/` mirrors OpenMetadata paths; `.om/` is a disposable, git-ignored working tree.

## Complexity Tracking

No constitution violations to justify.
