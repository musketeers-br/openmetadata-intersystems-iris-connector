# ADR-0009 — Default exclusions are filter patterns, not code paths

- **Status:** Accepted; `Ens*` settled by SPIKE-01; the generated-class rule is settled in spec 002 (SPIKE-02) · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-9 · **Binds:** FR-4, FR-10

## Context

An IRIS Namespace exposes system content:
- `%`-prefixed schemas;
- `INFORMATION_SCHEMA`;
- in interoperability-enabled Namespaces, `Ens*` and `EnsLib*` packages.

The catalog can also describe some classes as generated or deprecated. Hard-coded skips in code cannot be overridden by users who do want those objects.

## Decision

- System content is excluded through **default values** of `schemaFilterPattern` (and, if needed, `tableFilterPattern`) in `irisConnection.json`: excludes `^%`, `^INFORMATION_SCHEMA$` and `^Ens`.
- SPIKE-01 found that the `USER` Namespace of IRIS Community is interoperability-enabled. It has about 100 `Ens*` / `EnsLib*` / `EnsPortal*` schemas, so `^Ens` is a default exclude.
- Users can override every default in the UI or YAML.
- No skip logic exists in Python code.
- The defaults live in `irisConnection.json`, and the IRIS source applies them when the ingestion pipeline has no `schemaFilterPattern`; a pipeline pattern replaces them completely (no merge). This holds for UI, YAML and CLI runs, because the framework itself filters with the pipeline's pattern only.

## Outcome (spec 002)

The catalog (`INFORMATION_SCHEMA.TABLES.DESCRIPTION`) was checked for the fixture objects: no table or schema carries a generated or deprecated marker, so no name pattern exists to express it. No default pattern is added, nothing is excluded in code, and the case stays open until a Namespace shows one (the spec-002 integration tests assert the three defaults only).

## Consequences

The defaults live in `irisConnection.json` (`schemaFilterPattern.default.excludes`). Spec 000 creates them, and spec 002 may only add patterns to them.

## Validation

Spec 002:
- the seed ingests no `%` or `INFORMATION_SCHEMA` schemas by default;
- an include pattern for `Clinic` only yields `Clinic`;
- overriding the defaults brings system schemas back.
