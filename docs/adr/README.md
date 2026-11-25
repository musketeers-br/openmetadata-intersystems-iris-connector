# Architecture Decision Records

Each ADR records one decision from the [architecture spine](https://github.com/musketeers-br/is-omd/blob/main/docs/architecture.md) (AD-n) with its context, alternatives and how it is validated. ADR numbers match the AD numbers (ADR-0001 = AD-1). ADR-0014 and ADR-0015 were added after the spine (AD-14, AD-15).

ADRs live in this repository (moved from the analysis repository `is-omd` on 2026-11-25). Contracts, PRD, architecture spine and spike findings stay in `is-omd` and are linked from here.

| ADR | Decision | Status | Validated by | Used by specs |
|---|---|---|---|---|
| [0001](0001-in-tree-connector.md) | In-tree connector on `CommonDbSourceService` | Accepted | SPIKE-01 → spec 000 | all |
| [0002](0002-official-driver-only.md) | Official Python driver and SQLAlchemy dialect only | Accepted | SPIKE-01 → spec 000 | all |
| [0003](0003-driver-optional-extra.md) | Driver shipped as the optional `iris` extra | Accepted | spec 000, 009 | 000, 009 |
| [0004](0004-namespace-is-database.md) | Namespace = Database, SQL schema = Database Schema | Accepted | SPIKE-01 → spec 000, 002 | 000, 002, 007 |
| [0005](0005-identity-schema-name.md) | Metadata identity is always (schema, name) | Accepted, split pending | SPIKE-02 → spec 002 | 002, 003, 004, 005 |
| [0006](0006-single-type-map.md) | One type-mapping table owned by `iris/` | Accepted | SPIKE-02 → spec 003 | 002, 003, 004, 006, 008 |
| [0007](0007-vector-optional-enrichment.md) | VECTOR detail is an optional, capability-detected enrichment | Accepted, representation pending | SPIKE-03 → spec 004 | 000, 004 |
| [0008](0008-access-gaps-as-warnings.md) | Access gaps surface as ingestion-status warnings | Accepted | SPIKE-03 → spec 005 | 002, 004, 005, 006 |
| [0009](0009-exclusions-as-filter-patterns.md) | Default exclusions are filter patterns, not code paths (`^%`, `^INFORMATION_SCHEMA$`, `^Ens`) | Accepted; generated classes pending | SPIKE-01, SPIKE-02 → spec 002 | 000, 002 |
| [0010](0010-profiler-registry.md) | Profiler and DQ through the dialect registry and `@compiles` | Accepted | SPIKE-04 → spec 006 | 006 |
| [0011](0011-native-dbt-ingestion.md) | dbt via OpenMetadata's native dbt ingestion | Accepted | SPIKE-05 → spec 007 | 007 |
| [0012](0012-shared-fixtures-and-matrix.md) | Test matrix and fixtures are shared contracts | Accepted | spec 001 | all |
| [0013](0013-gap-report.md) | Limitations go to the Gap Report, never into workarounds | Accepted | spec 009 | all |
| [0015](0015-dialect-state-presets.md) | Preset the official dialect's version and dictionary-access state so least-privilege logins work (narrow exception to 0013) | Accepted | SPIKE-01 → spec 000 | 000, 002, 005 |
| [0014](0014-repository-topology.md) | `is-omd` for analysis and spikes; a clean dev repo for specs and code (overlay on OpenMetadata); fork only for the PR | Proposed | spec 000, 001 | all |

**Status values:** *Proposed* (to be confirmed in the first spec that uses it), *Accepted*, *Accepted, … pending* (decision stands; one detail is settled by the named spike, run in `is-omd` before its spec), *Superseded by ADR-NNNN*.

**Changing a decision:** write a new ADR that supersedes the old one, update the spine's AD entry and the affected [contracts](https://github.com/musketeers-br/is-omd/blob/main/docs/contracts/README.md) in the same change, and tell the other developer (constitution, Governance).
