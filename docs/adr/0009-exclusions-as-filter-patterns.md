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

## Open detail

Spec 002 decides, from SPIKE-02 evidence, whether these become default excludes as well:
- classes whose `INFORMATION_SCHEMA.TABLES.DESCRIPTION` marks them as generated or deprecated.

If generated or deprecated classes cannot be expressed as a name pattern, they are **not** excluded by code. They are documented instead, and the case is a Gap Report entry.

## Consequences

The defaults live in `irisConnection.json` (`schemaFilterPattern.default.excludes`). Spec 000 creates them, and spec 002 may only add patterns to them.

## Validation

Spec 002:
- the seed ingests no `%` or `INFORMATION_SCHEMA` schemas by default;
- an include pattern for `Clinic` only yields `Clinic`;
- overriding the defaults brings system schemas back.
