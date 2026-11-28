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

## Success criteria (T041, final validation)

Quickstart Q1–Q9 run on 2026-11-27 on the branch's final commit (`b132f86`), WSL2 with Docker Engine, a
fresh `make om-import`, and CI run [45879186174](https://github.com/musketeers-br/openmetadata-intersystems-iris-connector/actions/runs/45879186174) on the same commit.

- [x] **SC-001.** Q1, fresh container per track: 7–8 s from start to `FIXTURES OK v1` on `latest-em`, `latest-cd` and `latest-preview`. A second run gives the same output with exit 0. Q2: `pytest fixtures` 53 passed; after dropping `Billing.Patient` the self-check fails with `C1 Billing.Patient: expected BASE TABLE, actual missing`. Q3: an instance without the unexpire step gives exit 2 and points to `start-iris.sh`.
- [x] **SC-002.** Every run on this pull request and on the pull requests stacked on it shows `overlay-roundtrip` and the nine `iris-<tag>-<login>` checks, each summary with digest and `$ZVERSION`. The workflow also runs on push to `main` (`push: branches: [main]`); the first such run is the merge of this pull request.
- [x] **SC-003.** Run 45879186174: the placeholder test passes on all nine cells, the six blocking ones included.
- [x] **SC-004.** Run 45879186174: 5 min 36 s wall clock, rebuild included (limit 15 min).
- [x] **SC-005.** Q4: `make test-cell TAG=latest-em LOGIN=reader` and `TAG=latest-cd LOGIN=reader_dict PORT=11974`: 10 passed, 1 skipped (`test_workflow.py`, no server). Q6, no IRIS address: the session starts `latest-em`, seeds it, 10 passed, and no container is left.
- [x] **SC-006.** Q5 locally: with `sqlalchemy-iris` installed the guard exits 1 and names it; in the clean environment it exits 0. In CI (T027, run 46021601333), `iris-latest-cd-admin` with `sqlalchemy-iris` installed fails at the guard, which names it (research, "Failure paths in CI").
- [x] **SC-007.** Q8: `test_gap_report.py` 11 passed (format, GAP-001..009). Every reproduction except GAP-003 (pending SPIKE-03) gives the documented actual result on `latest-em`.
- [x] **SC-008.** `test_repo_rules.py` (in Q2's 53) passes: no connector test creates users or grants, and tests write only in `Scratch`. Henry's review on 2026-11-27 found no divergence.

Q9: `make om-export && make om-check` and a second `make om-check`: no diff, no permission error. SPIKE-06 was reviewed and merged by Henry on 2026-11-26 (plan, Complexity Tracking).

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
  not listed in `INFORMATION_SCHEMA.SCHEMATA` (also after its last table is dropped). FR-023 adds
  GAP-009. Revised with spec 002 (2026-11-25): FR-002 adds the sentinel `Scratch.Keep` so `Scratch`
  stays listed for the mark-deleted test, and ADR-0012 is updated (FR-026).
- `/speckit-clarify`: not needed. The likely questions (loader location, 9 cells, preview
  non-blocking, runners, no OpenMetadata server, testcontainers only as fallback, conftest location,
  dependency on spec 000) were settled before specifying.
- Revision 2026-11-25, after spec 000's PR: the spec builds on 000's tooling instead of waiting for
  it (no two-phase delivery), completes the Gap Report 000 started, migrates 000's integration test
  to the shared fixture (FR-025), updates ADR-0012 (FR-026), and no longer refers to planning
  documents outside this repository (constitution 1.2.2).
