# ADR-0011 — dbt via OpenMetadata's native dbt ingestion

- **Status:** Accepted; the dbt-iris FQN output is confirmed in spec 007 (SPIKE-05) · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-11 · **Binds:** FR-18 · **Constitution:** I

## Context

OpenMetadata's dbt ingestion reads `manifest.json`, `catalog.json` and `run_results.json` and matches models to existing tables by FQN. `dbt-iris` 1.9.2 is community-maintained and was last released in February 2025. It may lag `dbt-core` and may pull the community dialect (`sqlalchemy-iris`).

## Decision

- **No dbt code** in `iris/`.
- **Compatibility comes from the FQNs.** [ADR-0004](0004-namespace-is-database.md) makes them match: the dbt-iris fixture project must produce `database = <Namespace>` and `schema = <Schema>`.
- **Isolated environment.** The fixture dbt project lives in the dev repo's `fixtures/dbt/` and runs in its **own** virtualenv, so it never shares an environment with the connector ([ADR-0002](0002-official-driver-only.md)).
- **dbt-iris defects** (version conflicts, wrong database name in artifacts) go to the Gap Report. If needed, the artifacts used by the test are committed as fixtures, so CI does not depend on dbt-iris installing.

## Consequences

- Spec 007 is mostly fixtures, configuration, tests and docs. Connector code changes only if FQN matching reveals a mapping bug, and that fix belongs to ADR-0004 / ADR-0005.
- Table-level lineage is the target. Column-level lineage is whatever OpenMetadata derives from the artifacts.

## Validation

Spec 007:
- the sample project's models match existing assets as `<service>.USER.<Schema>.<Table>`;
- lineage edges exist;
- dbt descriptions appear on the assets.
