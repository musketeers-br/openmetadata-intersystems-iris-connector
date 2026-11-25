# ADR-0014 — Two repositories: `is-omd` for analysis, a clean dev repo for specs and code

- **Status:** Proposed (confirmed in spec 000 / 001) · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-14 · **Binds:** FR-22, FR-23, NFR-1 · **Constitution:** VII

## Context

Two kinds of work have different audiences:

- **Analysis and definition** is internal, exploratory and messy: PRD, architecture, ADRs, contracts, demands, spikes and throwaway experiments.
- **Development** produces what is published: Spec Kit specs, connector code, fixtures, CI, demo, docs, Gap Report. It becomes the public repository on GitHub and Open Exchange, and its code becomes the upstream PR.

Keeping both in one repository makes the published one noisy. The connector code must also end up inside OpenMetadata's repository for the upstream PR ([ADR-0001](0001-in-tree-connector.md)). Working inside a fork from day one mixes our specs with OpenMetadata's history, and the repository is very large.

## Decision

| Repository | Holds | Published |
|---|---|---|
| **`musketeers-br/is-omd`** (analysis) | `docs/` (PRD, architecture, contracts, demands, GitHub card texts), `spikes/` (environment, experiments, `findings/SPIKE-NN.md`) | internal |
| **Dev repo: `musketeers-br/openmetadata-intersystems-iris-connector`** (new) | `.specify/` + `specs/` (Spec Kit), `docs/adr/` (ADRs, moved here 2026-11-25), `overlay/` (connector code), `patches/`, `fixtures/`, `demo/`, `docs/connector/`, `GAP-REPORT.md`, CI | public: GitHub + Open Exchange |
| **OpenMetadata fork** | created only for the upstream PR (spec 009), from the dev repo's overlay and patches | PR to `open-metadata/OpenMetadata` |

### Overlay model (dev repo)

- **`overlay/`:** holds every **new** file the connector adds to OpenMetadata, at the same relative path. Examples: `overlay/ingestion/src/metadata/ingestion/source/database/iris/…`, `overlay/openmetadata-spec/…/irisConnection.json`.
- **`patches/`:** holds edits to **existing** OpenMetadata files as `git diff` patches, one per file. Examples: `ingestion/setup.py` (the `iris` extra), `databaseService.json` (the enum), the profiler registry, UI registration.
- **`openmetadata.version`:** pins the OpenMetadata tag: `2.1.1` (SPIKE-01).
- **`make om-import`:** clones that tag into `.om/` (git-ignored), copies `overlay/`, applies `patches/`, refreshes `ingestion/uv.lock` (the `iris` extra changes it), and runs `make install_dev` there. Model generation needs **ANTLR 4.9.2 on Java 21**. It runs the pinned, checksum-verified jar in an `eclipse-temurin:21-jre` container, so developers and CI need no local JDK (SPIKE-01). Developers and agents work and test inside `.om/`.
- **`make om-export`:** writes the changes made in `.om/` back to `overlay/` and `patches/`. Only `overlay/` and `patches/` are committed; they are the source of truth.
- **CI:** runs `make om-import` and then the tests, so a clean clone always rebuilds the same tree.
- **`make om-image`:** builds OpenMetadata server and ingestion images from `.om/` with Maven and yarn in Docker. A stock OpenMetadata server rejects `serviceType: Iris` and has no `Iris` test-connection definition, because both are compiled into the server (SPIKE-01). End-to-end runs (demo, review checkpoint, optional end-to-end CI) use this image. Unit and integration tests against IRIS do not need it.
- **`make om-branch`** (spec 009): applies `overlay/` and `patches/` onto a fork branch off upstream `main` for the PR.

### Spikes and definitions

- Spikes, experiments and definitions are produced in `is-omd` (`spikes/findings/SPIKE-NN.md`) **before** the spec that needs them starts.
- The spec's `research.md` in the dev repo copies the decisions and links back. It does not redo the experiment.
- If a spike changes a decision, the ADR (here, `docs/adr/`) and the contract (in `is-omd`) are updated first.

### Constitution and Spec Kit

The dev repo is initialized with Spec Kit, and the constitution is copied from `is-omd/.specify/memory/constitution.md`. From then on, the dev repo's copy is canonical, and amendments are made there and mirrored back.

## Consequences

- The dev repo stays small and readable: specs and code only, with no OpenMetadata history.
- Every `plan.md` writes OpenMetadata paths as `overlay/…` (new files) or `patches/<file>.patch` (edits).
- There is one extra step on the critical path: spec 000 builds the `om-import` / `om-export` tooling, and spec 001 uses it in CI.
- Patches can conflict when the OpenMetadata tag moves. Keep patches small, one per file. Spec 009 rebases them once, on the PR branch.

## Alternatives rejected

- **Specs and code inside the OpenMetadata fork:** the upstream PR would carry our planning artifacts, and the repository is heavy for agents.
- **Specs in `is-omd`, code in a fork clone:** mixes analysis with development, which is what this decision avoids.

## Validation

- **Spec 000:** `make om-import && make om-export` round-trips with no diff, and the IRIS connector imports from `.om/`.
- **Spec 001:** CI rebuilds `.om/` from a clean clone and runs one IRIS test.
