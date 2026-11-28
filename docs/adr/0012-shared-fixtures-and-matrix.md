# ADR-0012 — Test matrix and fixtures are shared contracts

- **Status:** Accepted; revised 2026-11-26 by spec 001 (loader location, `Scratch.Keep`, CI triggers and round-trip check) · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-12 · **Binds:** NFR-1, FR-11, FR-12, FR-14 · **Constitution:** VI

## Context

Ten specs, two developers, coding agents: if each spec creates its own IRIS users, schemas or containers, the tests become inconsistent and slow, and they collide in CI. Three behaviors must be tested on every IRIS release track:
- the VECTOR grant toggle;
- least privilege;
- same-name tables.

OpenMetadata's REVIEW.md asks for a test with every change.

## Decision

- **One fixture set.** Spec 001 creates it with one loader (idempotent, official driver only, self-check at the end), in the `USER` Namespace. The loader's source is `overlay/ingestion/tests/integration/iris/data/seed.py`, inside the OpenMetadata tree, so the integration tests can load the fixtures upstream without this repository; `fixtures/iris/seed.py` is the entry point that runs it. The same module holds the catalog that tests assert on. It creates:
  - the sample schemas;
  - the `omd_reader` and `omd_reader_dict` logins;
  - the grants.

  Objects: `Clinic.Patient` (PK, table and column descriptions, mixed case), `Clinic.Encounter` (FK to `Clinic.Patient`, `LONGVARCHAR`, `BIT`), `Billing.Patient` (same table name, unique constraint), `AI.Embedding` (`VECTOR(DOUBLE, 3)`), view `Clinic.ActivePatient`, and a `Scratch` schema for tests that create and drop objects. `Scratch` holds one empty sentinel table, `Scratch.Keep`, that tests never drop: IRIS stops listing a schema once its last table is dropped (GAP-009), and a test that drops its table and ingests again must still find the schema. Logins: `admin` = `_SYSTEM`; `reader` = `omd_reader` with `SELECT` on the sample schemas; `reader_dict` = `omd_reader_dict` with the same plus `SELECT` on `%Dictionary.PropertyDefinition` (the one optional dictionary grant, ADR-0007; until fixture catalog v3 it also held `%Dictionary.CompiledProperty`, which SPIKE-03 showed is not needed). Test-only passwords, throwaway containers. Specs **must not** create their own users or datasets. A spec that needs a new case adds it to the shared fixture, in a change reviewed by the fixture owner (Henrique).
- **One matrix.** Integration tests run against `containers.intersystems.com/intersystems/iris-community` with tags `latest-em`, `latest-cd` and `latest-preview`. Each tag runs as `admin`, `reader` and `reader_dict`, which covers both logins and the grant toggle. Tests read the cell from `IRIS_HOST`, `IRIS_PORT`, `IRIS_NAMESPACE`, `IRIS_TAG` and `IRIS_LOGIN`; when `IRIS_HOST` is unset, the integration `conftest.py` starts `latest-em` with testcontainers. Pytest fixtures: `iris_cell`, `iris_engine`, `iris_admin_engine`, `iris_service_connection`, `iris_admin_service_connection`, `seeded`; marker `iris`.
- **CI** (`.github/workflows/iris-matrix.yml`) runs on pull requests, on pushes to `main` and by hand. A check `overlay-roundtrip` rebuilds the OpenMetadata tree and fails if `overlay/` or `patches/` would change; the nine cells, one job each named `iris-<tag>-<login>`, need it.
- **`latest-preview` is informative:** a failure there is reported but does not block merging. The other two tracks block: once the repository is public, branch protection on `main` requires `overlay-roundtrip` and the six `latest-em` and `latest-cd` cells.
- **Every new behavior adds a test to this matrix.**

## Consequences

- Spec 001 is on the critical path of Wave 0. Every spec's acceptance means "green on every blocking cell".
- Fixture changes are additive. Removing or renaming a fixture object needs both developers' agreement, because other specs assert on it.

## Validation

Spec 001:
- one command recreates the fixtures from scratch;
- the CI matrix runs on every pull request and every push to `main`, and reports each cell separately;
- a placeholder test passes on every cell.
