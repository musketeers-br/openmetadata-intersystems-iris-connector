# Quickstart: validating Metadata Core Ingestion

Prerequisites: spec 000 done; shared fixtures loaded in an IRIS Community container (see the fixtures contract); `make om-import` done.

1. **Unit tests** (no IRIS): run `Test002…` in `test_iris.py` inside `.om/`. Expect the helper, identity-regression and lineage-wiring tests to pass.
2. **Integration, admin**: with `IRIS_HOST`, `IRIS_PORT`, `IRIS_LOGIN=admin`, run `test_metadata_core.py`. Expect every row of "Expected OpenMetadata entities" to hold (`Clinic.Patient` 4 columns, `Billing.Patient` 2, FK on `Clinic.Encounter`, view definition and lineage on `Clinic.ActivePatient`).
3. **Integration, reader**: same with `IRIS_LOGIN=reader`. Expect the same entities; any unreadable part appears as one `IRIS-ACCESS` warning and the run succeeds.
4. **Lineage**: run the lineage workflow with `processQueryLineage: false` and `processStoredProcedureLineage: false` (set both in the sample YAML) until spec 010 adds query-log lineage; with the defaults the run reports one error for the unsupported query-log part, though view lineage is created.
5. **Filters**: a run with no pipeline `schemaFilterPattern` uses the connection defaults and has no `%*`/`INFORMATION_SCHEMA`/`Ens*` schemas; include `Clinic` yields only `Clinic`; clearing excludes brings system schemas back.
6. **Re-runs**: create a table in `Scratch`, ingest, drop it, ingest with mark deleted on → deleted; off → not. Edit a description in OpenMetadata, re-ingest with override off → kept; on → replaced.
7. **Round trip**: `make om-export` then `make om-check` leaves the repository with only intended `overlay/`/`patches/` changes.

Repeat steps 2–5 on `latest-em`, `latest-cd` and `latest-preview` (matrix, spec 001).
