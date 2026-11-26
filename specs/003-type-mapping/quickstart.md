# Quickstart: Type mapping

Prerequisites: `make om-import` on the 003 branch; an IRIS container of each track with the fixtures
(spec 001: `make iris-up TAG=… PORT=…` and `make iris-seed`).

## Q1 — Fixture v2 on every track (FR-010)

```bash
for t in latest-em:11972 latest-cd:11974 latest-preview:11975; do
  IRIS_HOST=127.0.0.1 IRIS_PORT=${t#*:} .om/env/bin/python fixtures/iris/seed.py | tail -1   # FIXTURES OK v2
done
```

## Q2 — Discovery still matches the table (FR-002)

```bash
IRIS_PORT=11972 .om/env/bin/python fixtures/iris/discover_types.py --check
```

Expected: exit 0, "15 DATA_TYPE values, all mapped". A new value fails and names it.

## Q3 — Unit tests (FR-011, FR-012, FR-014)

```bash
cd .om/ingestion && ../env/bin/python -m pytest tests/unit/topology/database/test_iris_types.py -q
```

## Q4 — Every cell (FR-013, SC-001)

```bash
make test-cell TAG=latest-em LOGIN=reader
make test-cell TAG=latest-cd LOGIN=reader_dict PORT=11974
make test-cell TAG=latest-preview LOGIN=admin PORT=11975
```

Expected: `test_types.py` passes; no `IRIS-UNKNOWN-TYPE` warning.

## Q5 — An unknown type warns once (SC-003)

`test_types.py::test_an_unmapped_type_warns_once_per_run` removes the `numeric` row for the length of
the test and ingests `Types.AllTypes` and `Clinic.Patient` (both have `numeric` columns): one warning,
both columns `UNKNOWN`.

## Q6 — Regenerate the docs table (FR-014, SC-004)

```bash
cd .om/ingestion && ../env/bin/python -c 'from metadata.ingestion.source.database.iris.types import render_markdown_table; print(render_markdown_table())'
```

Paste the output between the markers of `contracts/type-mapping.md`, or run the unit test, which says
whether it is stale.
