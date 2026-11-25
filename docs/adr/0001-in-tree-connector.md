# ADR-0001 — In-tree connector on CommonDbSourceService

- **Status:** Accepted · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-1 · **Binds:** all FRs · **Constitution:** I, VII

## Context

OpenMetadata offers two ways to add a database source:

1. **In-tree:** a package under `ingestion/src/metadata/ingestion/source/database/<name>/` that subclasses `CommonDbSourceService` and is registered through `DefaultDatabaseSpec`. It comes with its own connection JSON schema, test-connection definition and UI form.
2. **Out-of-tree:** a pip package loaded through the generic `CustomDatabase` service with `sourcePythonClass`.

The out-of-tree path has a light dev loop, but it has no dedicated UI form, no IRIS icon and no typed Test Connection. It likely has no profiler, data-quality or dbt support either, because Custom Database only exposes `supportsMetadataExtraction`. It cannot become the upstream PR without a rewrite. See [research](https://github.com/musketeers-br/is-omd/blob/main/docs/research/openmetadata-connector-patterns.md).

## Decision

The connector lives in `ingestion/src/metadata/ingestion/source/database/iris/` in OpenMetadata's source tree. During development it lives in the dev repo's `overlay/` and `patches/`, applied onto the pinned OpenMetadata tag, and it becomes a fork branch only for the upstream PR (see [ADR-0014](0014-repository-topology.md)).
- `IrisSource` subclasses `CommonDbSourceService` and registers through `DefaultDatabaseSpec` in `service_spec.py`.
- Overrides are allowed only for IRIS-specific behavior governed by ADR-0004 to ADR-0009.
- No `CustomDatabase` / `sourcePythonClass` variant is shipped.

## Consequences

- Profiler, data quality, dbt, view lineage, test connection, filter patterns and mark-deleted are inherited from the framework.
- The footprint is about 30–64 files across `ingestion/`, `openmetadata-spec/`, `openmetadata-service/` and `openmetadata-ui/`. The dev loop is heavier: `make install_dev generate`, plus a UI and Java build to see the form.
- The overlay applied onto a fork branch *is* the upstream PR (spec 009).

## Alternatives rejected

- **Out-of-tree `CustomDatabase` package:** no form, no profiler/DQ/dbt, and the upstream PR would need a port.
- **Hand-written `Source` creating entities via REST:** reimplements the framework, so maintainers would reject it (constitution I).

## Validation

SPIKE-01 (findings in is-omd `spikes/findings/SPIKE-01.md`), then spec 000: the scaffold (`metadata scaffold-connector`) produces `iris/`, and `metadata ingest` runs against IRIS Community. The plan's Constitution Check of every spec verifies no framework behavior is reimplemented.
