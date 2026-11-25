<!--
Sync Impact Report
- Version change: 1.2.1 → 1.2.2 (PATCH: the repository is self-contained; references to external
  planning documents replaced by the decisions themselves)
- Previous: 1.2.0 → 1.2.1 (PATCH: ADRs moved to this repository's docs/adr/; paths updated)
- Previous: 1.1.0 → 1.2.0 (MINOR: one narrow exception to Principle V; new licensing, image and
  overlay/patch constraints; workflow rules for attribution, issue tracking and spikes; canonical copy)
- Modified principles: V. Nothing Silent, Nothing Hidden (dialect state-preset exception, ADR-0015).
  No principle renamed, renumbered or removed.
- Modified sections: Technical Constraints (licensing; end-to-end image vs. tests; overlay/patch path
  notation and `make om-export` gate); Development Workflow (no AI attribution; one issue per spec on
  the "IRIS connector" Project with fixed statuses; spike outcomes recorded in research.md);
  Governance (this repository's copy is canonical)
- Added sections: none
- Removed sections: none
- Templates:
  ✅ .specify/templates/plan-template.md — Constitution Check derives gates from this file; no change
  ✅ .specify/templates/spec-template.md — no conflicting mandatory sections
  ✅ .specify/templates/tasks-template.md — Principle VI references unchanged; no change
  ✅ .specify/templates/checklist-template.md — no constitution references; no change
- Deferred items:
  - Ratification of 1.1.0 and 1.2.0 is pending Henrique Dias's agreement (Governance requires both
    developers).
- Previous: 1.0.0 → 1.1.0 (repository model and spike rule; ADR-0014; base pinned to OpenMetadata
  2.1.1 and server-image requirement after SPIKE-01); template → 1.0.0 (initial ratification)
-->

# IRIS Connector for OpenMetadata Constitution

## Core Principles

### I. Framework First

The connector MUST extend OpenMetadata's `CommonDbSourceService`, profiler/data-quality registry and
native dbt ingestion. It MUST NOT reimplement entity creation, topology, sinks, profiling or dbt
parsing that the framework already provides. Overrides are allowed only for IRIS-specific behavior.

Rationale: what the framework does for every connector is what maintainers can accept and maintain.

### II. Official Driver Only

Connections MUST use InterSystems' official `intersystems-irispython` driver and
`sqlalchemy-intersystems-iris` dialect, shipped as the optional `iris` install extra and never
vendored. JDBC, ODBC, a JVM, and the community `sqlalchemy-iris` dialect MUST NOT be used in the
connector or its tests.

Rationale: one supported driver stack, no conflicting version pins, licence terms isolated in an extra.

### III. IRIS Fidelity

- One IRIS service connects to one Namespace; the OpenMetadata Database is named after it, and each
  SQL schema is a Database Schema.
- Object identity MUST always be `(schema, name)` (plus column name); joins and maps MUST NOT key on
  name alone.
- Names MUST keep the case IRIS stores; they are never normalized.
- IRIS → OpenMetadata types MUST come from one mapping module; unknown types become `UNKNOWN` with
  one warning per type per run.

### IV. Least Privilege by Default

Every feature MUST work with an ordinary SQL login holding only SELECT on the target objects.
Additional privileges (e.g. reading `%Dictionary.CompiledProperty` for VECTOR detail) are optional
enrichments, detected at runtime, never prerequisites. Credentials MUST never be logged, and
documented grants MUST be read-only.

### V. Nothing Silent, Nothing Hidden

- Any object or feature the login cannot read MUST appear as a warning in the OpenMetadata
  ingestion status with the object's full name and the reason; the run continues.
- Limitations of IRIS or the driver MUST be recorded in `GAP-REPORT.md` with a reproduction, and
  the connector degrades gracefully. Hidden workarounds or patches are forbidden.
- Sole exception (ADR-0015, `docs/adr/0015-dialect-state-presets.md`): the connector MAY
  preset state attributes the official dialect already defines (`server_version_info`,
  `_dictionary_access`) so least-privilege logins work. Conditions: no SQL rewriting; no
  monkey-patching or subclassing of the dialect; one function in `iris/connection.py`; unit-tested;
  listed in `GAP-REPORT.md` (GAP-004, GAP-005) with an upstream issue; removed when the dialect is
  fixed. No other workaround is allowed.

### VI. Tested on the Matrix (NON-NEGOTIABLE)

Every change MUST ship with tests. Integration tests MUST run in public CI against the IRIS
Community release tracks `latest-em`, `latest-cd` and `latest-preview`, each as administrator and
as least-privilege login, plus the VECTOR dictionary-grant toggle. Tests use only the shared fixture
set; specs MUST NOT create their own IRIS users or datasets.

### VII. Upstream-Ready

Code, schemas, UI changes and docs MUST follow OpenMetadata's connector development guide, code
style (`make py_format`, `mvn spotless:apply`) and `REVIEW.md`, so the connector can be proposed
upstream as-is. Docs follow OpenMetadata's connector page layout.

### VIII. English Artifacts

Specs, plans, tasks, ADRs, docs, commit messages and code comments MUST be in English.
Private correspondence with third parties MUST NOT be quoted or referenced in any project artifact.

## Technical Constraints

- Base: OpenMetadata 2.1.1 (pinned in `openmetadata.version`; SPIKE-01), Python 3.11. Model generation
  needs ANTLR 4.9.2 on Java 21, run in a container.
- Connector package: `ingestion/src/metadata/ingestion/source/database/iris/` in OpenMetadata's
  source tree, kept in the dev repository as `overlay/` (new files) and `patches/` (edits to existing
  files) on the OpenMetadata tag pinned in `openmetadata.version`; an OpenMetadata fork is created only
  for the upstream PR. Direct SQL lives only in `queries.py`.
- Test images: `containers.intersystems.com/intersystems/iris-community:{latest-em,latest-cd,latest-preview}`.
- Licensing: the repository root is Apache-2.0; everything under `overlay/ingestion/` and patches to
  `ingestion/` files follows the Collate Community License 1.0 (OpenMetadata's license header MUST be
  kept on every Python file there, and ingestion's LICENSE text MUST be included under
  `overlay/ingestion/`). The InterSystems driver and dialect are never vendored, only referenced
  through the optional `iris` extra.
- End-to-end runs (UI form, Test connection in the UI, demo, review checkpoint) MUST use OpenMetadata
  server/ingestion images built from the overlay (`make om-image`); a stock server rejects the `Iris`
  service type. Connector unit and integration tests against IRIS MUST NOT depend on that image.
- OpenMetadata paths in plans are written as `overlay/<path>` (new files) or
  `patches/<path with / as __>.patch` (edits). `make om-export` MUST run before every commit, and CI
  fails if `make om-import && make om-export` changes `overlay/` or `patches/`.
- Performance work (batching, concurrency) beyond the framework requires a measured problem first.

## Development Workflow

- This repository holds the ADRs (`docs/adr/`), Spec Kit specs, code, fixtures, CI, demo and the Gap
  Report, and is self-contained: documents state the decisions they depend on instead of pointing to
  external planning material. A changed decision gets a new or updated ADR here.
- A spec starts only after the spikes it depends on have reviewed findings; the spec's `research.md`
  records the decisions and the evidence that matters, instead of repeating the experiment.
- Planning artifacts (PRD, architecture, spec plan) come first; each spec references PRD `FR-n` and
  architecture `AD-n` IDs.
- Each spec has exactly one owner (Henry Pereira or Henrique Dias), who drives it end to end, mainly
  through coding agents. The other developer reviews.
- Flow per spec: `/speckit-specify` → `/speckit-clarify` (if needed) → `/speckit-plan` →
  `/speckit-tasks` → `/speckit-analyze` → `/speckit-implement`.
- Commits, pull requests and issues carry no AI attribution (no `Co-Authored-By` or "generated with"
  trailers); the developer is the author.
- Each spec is tracked by one issue on the "IRIS connector" GitHub Project; the issue moves Backlog →
  Spike → Ready → Spec & plan → Implement → Review → Done.
- A spec is done when its acceptance criteria pass on every matrix cell and the docs and gap report
  are updated.

## Governance

This constitution supersedes other practices for this project. Amendments require agreement of
both developers, an updated Sync Impact Report, and propagation to dependent templates. Versioning
follows semantic versioning: MAJOR for removed or redefined principles, MINOR for new principles or
materially expanded guidance, PATCH for clarifications. Every plan's Constitution Check and every
review MUST verify compliance; deviations are justified in the plan's Complexity Tracking table.

This repository's copy of the constitution is canonical.
Ratification of 1.1.0 and 1.2.0 is pending Henrique Dias's agreement.

**Version**: 1.2.2 | **Ratified**: 2026-11-18 | **Last Amended**: 2026-11-25
