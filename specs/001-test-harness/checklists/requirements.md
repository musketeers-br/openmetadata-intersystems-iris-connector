# Specification Quality Checklist: Test harness (shared fixtures + CI matrix)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-25
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Validation run 1 (2026-11-25): two issues found and fixed.
  - SC-007 required a runnable reproduction for every gap entry, but GAP-003 has none until
    SPIKE-03; reworded to "reproduction, or pending with the spike that provides it".
  - FR-004 did not verify that the least-privilege logins cannot write; added (refusal verified on
    `latest-em`: `SQLCODE -99` for INSERT and CREATE TABLE).
- Validation run 2: all items pass.
- Audience and technical terms: this feature is test infrastructure whose users are developers,
  reviewers and upstream maintainers, so domain terms (IRIS release tracks, logins, class dictionary,
  CI cell, SQL catalog) are the user vocabulary, not implementation choices. No language, test
  framework, CI product or file layout is prescribed in requirements; those go to `/speckit-plan`.
  Mentions of GitHub-hosted runners and Actions minutes are confined to Assumptions.
- Finding while specifying (probe on `latest-em` and `latest-cd`): an IRIS schema without tables is
  not listed in `INFORMATION_SCHEMA.SCHEMATA` (also after its last table is dropped). FR-002 defines
  `Scratch` accordingly, and FR-023 adds GAP-009. Spec 002 (mark-deleted) needs to know this, and
  ADR-0012 is updated (FR-026).
- `/speckit-clarify`: not needed. The likely questions (loader location, 9 cells, preview
  non-blocking, runners, no OpenMetadata server, testcontainers only as fallback, conftest location,
  dependency on spec 000) were settled before specifying.
- Revision 2026-11-25, after spec 000's PR: the spec builds on 000's tooling instead of waiting for
  it (no two-phase delivery), completes the Gap Report 000 started, migrates 000's integration test
  to the shared fixture (FR-025), updates ADR-0012 (FR-026), and no longer refers to planning
  documents outside this repository (constitution 1.2.2).
