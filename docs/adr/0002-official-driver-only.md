# ADR-0002 — Official Python driver and SQLAlchemy dialect only

- **Status:** Accepted · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-2 · **Binds:** FR-1, FR-2, NFR-3 · **Constitution:** II

## Context

Several IRIS client stacks exist:

| Stack | Licence | Problem |
|---|---|---|
| `intersystems-irispython` 5.4.1 + `sqlalchemy-intersystems-iris` 1.0.2 (official) | InterSystems External Repository Terms of Use | Not OSI, so handled by [ADR-0003](0003-driver-optional-extra.md) |
| `sqlalchemy-iris` 0.20.0 (community) | MIT | Pins `intersystems-irispython ~=5.3.2`, which conflicts with 5.4.1 |
| JDBC / ODBC bridges | various | Need a JVM or a native driver inside OpenMetadata's ingestion image |

OpenMetadata builds SQLAlchemy connectors with `create_generic_db_connection`, which needs a SQLAlchemy dialect.

## Decision

- Connections are built with `create_generic_db_connection` on the URL scheme registered by `sqlalchemy-intersystems-iris`, over `intersystems-irispython`.
- No Java, JDBC, ODBC or `sqlalchemy-iris` import appears anywhere in `iris/`, its tests or our fixtures.
- Fixtures and the seed script also use the official driver (`import iris`).

## Consequences

- One driver stack, with no conflicting version pins.
- Any gap in the official dialect becomes an entry in the Gap Report ([ADR-0013](0013-gap-report.md)). We do not patch it and we do not switch dialects. A direct `INFORMATION_SCHEMA` query in `queries.py` is allowed when it is documented.
- dbt-iris (spec 007) may pull the community dialect into *its own* environment. It must stay isolated from the connector's environment (separate virtualenv in the fixture).

## Open detail

The exact URL scheme (`iris://…` or a driver-qualified variant) and the connect arguments are confirmed in spec 000 (SPIKE-01) and recorded in the [connection contract](https://github.com/musketeers-br/is-omd/blob/main/docs/contracts/connection.md).

## Validation

Spec 000 adds a unit test that builds the URL. Spec 001's CI runs only with the official packages installed, and a check that `sqlalchemy_iris` is not importable fails the build if it appears.
