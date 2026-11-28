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
| `fixtures/iris/` | Shared IRIS test fixtures: container start, loader entry point, fixture tests |
| `.github/workflows/` | The CI matrix (`iris-matrix.yml`) |
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

## Running tests

Tests run against IRIS Community containers (`containers.intersystems.com/intersystems/iris-community`)
loaded with one shared fixture set. CI runs every release track (`latest-em`, `latest-cd`,
`latest-preview`) with every login (`admin`, `reader`, `reader_dict`); locally you run one cell at a
time. The examples use host port 11972, because 1972 is often taken by another IRIS.

**One cell, one command** (needs `make om-import` once; it also installs the test dependencies, the
`iris` extra and `testcontainers`, into `.om/env`, the connector's interpreter):

```bash
make test-cell TAG=latest-em LOGIN=reader                  # start omd-test-iris-latest-em, load the fixtures, run the tests
make test-cell TAG=latest-cd LOGIN=reader_dict PORT=11974  # another track at the same time needs another port
make iris-down TAG=latest-em                               # remove the container
```

`test-cell` runs, from `.om/ingestion`, `../env/bin/python -m pytest tests/integration/iris -m iris -rs`
with `IRIS_HOST`, `IRIS_PORT`, `IRIS_TAG` and `IRIS_LOGIN` set. The connector's tests always run from
`.om/ingestion`, as OpenMetadata's own do. Unit tests need no IRIS:
`cd .om/ingestion && ../env/bin/python -m pytest tests/unit/topology/database/test_iris.py`.

**Automatic single instance.** Without `IRIS_HOST`, the integration tests start one `latest-em`
container themselves (or `IRIS_TAG`), load the fixtures, run, and remove it:

```bash
cd .om/ingestion && IRIS_LOGIN=reader ../env/bin/python -m pytest tests/integration/iris -m iris -rs
```

**The fixture loader and its tests** need only a plain Python 3.11 venv:

```bash
python -m venv .venv && .venv/bin/pip install -r fixtures/iris/requirements.txt
fixtures/iris/start-iris.sh latest-em 11972 omd-test-iris-latest-em   # start, wait, unexpire; prints digest and $ZVERSION
IRIS_PORT=11972 .venv/bin/python fixtures/iris/seed.py                # load, then self-check
IRIS_HOST=127.0.0.1 IRIS_PORT=11972 .venv/bin/python -m pytest fixtures -q
.venv/bin/python fixtures/iris/check_dialect.py                       # fails if the community sqlalchemy-iris is installed
```

`seed.py` exits 0 with `FIXTURES OK v<N>`, 1 when the self-check fails (it names the object, the
expected and the actual value), 2 when IRIS is unreachable or not prepared (run `start-iris.sh`), and
3 when a statement fails. It is idempotent. Its source is
`overlay/ingestion/tests/integration/iris/data/seed.py`, which also holds the catalog tests assert
on (`LOGINS`, `EXPECTED`); `fixtures/iris/seed.py` runs it.

Rules for tests: branch on `iris_cell.is_admin` and `iris_cell.has_dict_grant`, never on login names;
create objects only in the `Scratch` schema and never touch `Scratch.Keep`; never create users or
grants. A new case goes into the shared fixtures, reviewed by the fixture owner.

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
