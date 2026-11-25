# ADR-0014 — Repository layout: an overlay on a pinned OpenMetadata release

- **Status:** Accepted (confirmed by SPIKE-01) · **Date:** 2026-11-24, revised 2026-11-25 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-14 · **Binds:** FR-22, FR-23, NFR-1 · **Constitution:** VII

## Context

The connector code must end up inside OpenMetadata's source tree ([ADR-0001](0001-in-tree-connector.md)), because that is what becomes the upstream PR. This repository is also what users see on GitHub and on InterSystems Open Exchange: the specs, connector code, fixtures, CI, demo, docs, Gap Report and ADRs.

Working inside a fork of OpenMetadata from day one would mix our specs with OpenMetadata's history, and that repository is very large for coding agents.

## Decision

| Where | Holds |
|---|---|
| **This repository** | `.specify/` + `specs/` (Spec Kit), `docs/adr/` (ADRs), `overlay/` (connector code), `patches/`, `fixtures/`, `demo/`, `docs/connector/`, `GAP-REPORT.md`, CI |
| **OpenMetadata fork** | created only for the upstream PR (spec 009), from `overlay/` and `patches/` |

Planning artifacts and spike experiments are kept outside this repository. Their outcomes arrive here as ADRs and as the decisions recorded in each spec's `research.md`.

### Overlay model

- **`overlay/`:** every **new** file the connector adds to OpenMetadata, at the same relative path. Examples: `overlay/ingestion/src/metadata/ingestion/source/database/iris/…`, `overlay/openmetadata-spec/…/irisConnection.json`.
- **`patches/`:** edits to **existing** OpenMetadata files, as `git diff` patches, one per file. Patch names are the OpenMetadata path with `/` replaced by `__`, plus `.patch`. The edits (spec 000):
  - `openmetadata-spec/.../entity/services/databaseService.json`: `Iris` in `enum` and in `javaEnums`, plus the `oneOf` `$ref`;
  - `ingestion/setup.py`: the `iris` extra;
  - `ingestion/uv.lock`: refreshed after the extra changes;
  - `openmetadata-service/.../secrets/converter/ClassConverterFactory.java`: registers `IrisConnection`, because the server masks credentials through a static class map with no plugin hook;
  - UI registration: `DatabaseServicePureUtils.ts`, `EntityUtils.interface.ts`, `ServiceIconUtils.ts`.
- **Generated files are never patched.** The UI's generated sources (`src/generated/`, `src/jsons/ingestionSchemas/`, `public/jsons/connectionSchemas/`) are rebuilt by `make om-ui-codegen`. `scripts/om-export-ignore` keeps them out of `make om-export`.
- **`openmetadata.version`:** pins the OpenMetadata tag, `2.1.1`.
- **`make om-import`:**
  1. clones that tag into `.om/` (git-ignored);
  2. copies `overlay/` and applies `patches/`;
  3. refreshes `ingestion/uv.lock`;
  4. regenerates the UI's generated files (`scripts/om-ui-codegen.sh`, in a `node:22-bookworm` container; `OM_SKIP_UI_CODEGEN=1` skips it);
  5. runs `make install_dev` there.

  Model generation needs **ANTLR 4.9.2 on Java 21**. It runs the pinned, checksum-verified jar in an `eclipse-temurin:21-jre` container, so neither developers nor CI need a local JDK. Developers and agents work and test inside `.om/`.
- **`make om-export`:** writes the changes made in `.om/` back to `overlay/` and `patches/`. Only `overlay/` and `patches/` are committed; they are the source of truth.
- **`make om-image`:** builds the OpenMetadata server and ingestion images from `.om/`, with Maven and yarn in Docker. A stock OpenMetadata server rejects `serviceType: Iris` and has no `Iris` test-connection definition, because both are compiled into the server. End-to-end runs (UI form, demo, review checkpoint, optional end-to-end CI) use this image. Connector unit and integration tests against IRIS do not need it.
- **CI:** runs `make om-import` and then the tests, so a clean clone always rebuilds the same tree.
- **`make om-branch`** (spec 009): applies `overlay/` and `patches/` onto a fork branch off upstream `main`, then regenerates the generated files, because upstream expects them committed in the PR.

### Constitution and Spec Kit

This repository is initialized with Spec Kit (0.12.0). Its constitution (`.specify/memory/constitution.md`) is the canonical copy.

## Consequences

- The repository stays small and readable: specs, decisions and code only, with no OpenMetadata history.
- Every `plan.md` writes OpenMetadata paths as `overlay/…` (new files) or `patches/<file>.patch` (edits).
- Spec 000 builds the `om-import` / `om-export` / `om-image` tooling, and spec 001 uses it in CI.
- Patches can conflict when the OpenMetadata tag moves. Keep them small, one per file, and rebase them once, on the PR branch, in spec 009.

## Alternatives rejected

- **Specs and code inside the OpenMetadata fork:** the upstream PR would carry our specs, and the repository is heavy for agents.
- **Git submodule of OpenMetadata:** pins well, but it is heavy and clumsy for agents. `openmetadata.version` pins the tag just as well.

## Validation

- **Spec 000:** `make om-import && make om-export` round-trips with no diff, and the IRIS connector imports from `.om/`.
- **Spec 001:** CI rebuilds `.om/` from a clean clone and runs one IRIS test.
