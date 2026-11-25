# ADR-0012 — Test matrix and fixtures are shared contracts

- **Status:** Accepted · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-12 · **Binds:** NFR-1, FR-11, FR-12, FR-14 · **Constitution:** VI

## Context

Ten specs, two developers, coding agents: if each spec creates its own IRIS users, schemas or containers, the tests become inconsistent and slow, and they collide in CI. Three behaviors must be tested on every IRIS release track:
- the VECTOR grant toggle;
- least privilege;
- same-name tables.

OpenMetadata's REVIEW.md asks for a test with every change.

## Decision

- **One fixture set.** It is promoted from is-omd's `spikes/docker/iris/seed.py` into the dev repo's `fixtures/iris/` by spec 001 and creates:
  - the sample schemas;
  - the `omd_reader` and `omd_reader_dict` logins;
  - the grants.

  See the [fixtures contract](https://github.com/musketeers-br/is-omd/blob/main/docs/contracts/fixtures.md). Specs **must not** create their own users or datasets. A spec that needs a new case adds it to the shared fixture, in a change reviewed by the fixture owner (Henrique).
- **One matrix.** Integration tests run against `containers.intersystems.com/intersystems/iris-community` with tags `latest-em`, `latest-cd` and `latest-preview`. Each tag runs as `admin`, `reader` and `reader_dict`, which covers both logins and the grant toggle. See the [test-matrix contract](https://github.com/musketeers-br/is-omd/blob/main/docs/contracts/test-matrix.md).
- **`latest-preview` is informative:** a failure there is reported but does not block merging. The other two tracks block.
- **Every new behavior adds a test to this matrix.**

## Consequences

- Spec 001 is on the critical path of Wave 0. Every spec's acceptance means "green on every blocking cell".
- Fixture changes are additive. Removing or renaming a fixture object needs both developers' agreement, because other specs assert on it.

## Validation

Spec 001:
- one command recreates the fixtures from scratch;
- the CI matrix runs on every push and reports each cell separately;
- a placeholder test passes on every cell.
