# ADR-0013 — Limitations go to the Gap Report, never into workarounds

- **Status:** Accepted · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-13 · **Binds:** FR-24, NFR-4 · **Constitution:** V

## Context

Some behavior will be missing or wrong in IRIS SQL metadata, in the official dialect or in dbt-iris. We already know of two cases:
- VECTOR is reported as `varchar`;
- the class dictionary needs an extra grant.

Hidden patches inside the connector, such as monkey-patching the dialect or post-processing wrong values, are hard to review upstream. They also break silently when the driver changes.

## Decision

- A missing or wrong behavior is documented in `GAP-REPORT.md` in the dev repository. Each entry has:
  - component;
  - IRIS release tracks affected;
  - reproduction;
  - expected vs actual;
  - connector behavior;
  - workaround for users, if any.
- The connector degrades gracefully, as ADR-0007, ADR-0008 and ADR-0010 define.
- **One narrow exception:** [ADR-0015](0015-dialect-state-presets.md) presets two state attributes of the official dialect, its server version and its dictionary access, so least-privilege logins work. It is documented, tested, reported as GAP-004/005 and removable. No other dialect workaround is allowed.
- A documented direct `INFORMATION_SCHEMA` query in `queries.py` is allowed when the inspector lacks a fact ([ADR-0005](0005-identity-schema-name.md)). It is not a hidden workaround, because it is visible, tested and listed in the Gap Report.

## Consequences

- Every spec's definition of done includes "Gap Report updated" (constitution, Development Workflow).
- Spec 009 checks that every limitation mentioned in the docs has a Gap Report entry.

## Validation

Spec 009 cross-checks the docs' limitations section against the `GAP-REPORT.md` entries, and each reproduction runs against the fixture.
