# InterSystems IRIS connector for OpenMetadata

Adds InterSystems IRIS as a database service type in [OpenMetadata](https://open-metadata.org),
developed here as an overlay on a pinned OpenMetadata release (`openmetadata.version`, currently 2.1.1).
The repository holds only the connector's own files and edits; nothing from OpenMetadata is copied
except its licence text.

Status: work in progress (spec 000, connector foundation). This README is a stub; the full
documentation arrives with spec 009.

## Layout

| Path | What it holds |
|---|---|
| `overlay/` | New OpenMetadata files, at their OpenMetadata paths |
| `patches/` | Edits to existing OpenMetadata files, one git patch per file, named by path with `/` as `__` |
| `openmetadata.version` | The pinned OpenMetadata release |
| `scripts/`, `Makefile` | The commands below |
| `specs/`, `.specify/`, `docs/adr/` | Spec Kit specs, constitution and architecture decisions |
| `GAP-REPORT.md` | Limitations of IRIS, its driver and dialect, with reproductions |
| `.om/` | Git-ignored working tree, rebuilt by `make om-import` |

## Working on the connector

Requirements: git, GNU make, `uv`, Docker (a containerized ANTLR generates the models, so no local JDK),
Python 3.11 (provisioned by `uv`).

```bash
make om-import    # clone OpenMetadata at the pinned tag into .om/, add overlay/, apply patches/, install and generate
make om-export    # write your edits in .om/ back to overlay/ and patches/ (run before every commit)
make om-check     # om-import then om-export must change nothing
make om-ui-codegen  # regenerate the committed UI schema and TypeScript files in a Node container (after a schema change)
make om-image     # build the OpenMetadata server and ingestion images that know Iris (Docker needs 10-12 GB of memory; stop other containers first)
```

Edit inside `.om/`. A commit without `make om-export` loses the work on the next `om-import`, and
`om-import` refuses to run over changes that were not exported (`FORCE=1` discards them).

Before exporting, format the touched modules inside `.om/` (`make py_format` in `.om/ingestion`,
`mvn spotless:apply` and the UI formatters for Java and UI files).

Unit tests (no IRIS needed), from `.om/ingestion`:

```bash
python -m pytest tests/unit/topology/database/test_iris.py
```

Integration tests need an IRIS Community container with the shared fixtures. They read `IRIS_HOST`,
`IRIS_PORT`, `IRIS_NAMESPACE` and `IRIS_LOGIN` (`admin`, `reader` or `reader_dict`) and need the
`iris` extra installed in `.om/env`.

## Licensing

- The repository root is Apache-2.0 (`LICENSE`).
- Everything under `overlay/ingestion/` and the patches to `ingestion/` files follow the Collate
  Community License 1.0 (text in `overlay/ingestion/LICENSE`); Python files there keep OpenMetadata's
  license header.
- The InterSystems driver and dialect are never vendored. The connector only references them through
  the optional `iris` extra of the ingestion package (`pip install "openmetadata-ingestion[iris]"`),
  which is under InterSystems' own terms.
- The service icon (`service-icon-iris.svg`) is an original placeholder drawn for this repository
  (Apache-2.0); source and licence are recorded in `service-icon-iris.LICENSE.md` next to it. It is not the InterSystems logo.
