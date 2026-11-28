# Implementation Plan: Metadata Core Ingestion

**Branch**: `002-metadata-core` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-metadata-core/spec.md`

## Summary

Fill the `--- 002: catalog ---` sections of the IRIS connector so a metadata ingestion produces the
Namespace → schema → table/view → column hierarchy with keys, view definitions, descriptions and view
lineage, exactly as the fixtures contract lists. The framework's reflection (SQLAlchemy inspector of the
official dialect) is the default source; for each fact where it is wrong or incomplete for IRIS the
connector uses a named `INFORMATION_SCHEMA` query in `queries.py` keyed on `(schema, name)` and adds a
Gap Report entry. Which facts fall on which side is decided by a first, evidence-producing task
(inspector vs `INFORMATION_SCHEMA` on the fixture objects, all three tracks) and recorded in
[research.md](research.md); until then the table there is provisional. Every per-object feature read is
wrapped by `report_access_gap`, which turns an access failure into one `IRIS-ACCESS` status warning and
lets the run continue. That helper ships first, alone, because spec 005 depends on it. View lineage is a
new `lineage.py` (`LineageSource` subclass, as `sqlite/`) registered in `service_spec.py`. Filters,
mark-deleted and description override use framework options and defaults in `irisConnection.json`; this
spec only tests them.

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**: OpenMetadata 2.1.1 ingestion framework (`CommonDbSourceService`, `LineageSource`); `sqlalchemy-intersystems-iris==1.0.2` and `intersystems-irispython==5.4.1` via the `iris` extra; SQLAlchemy 2.0.x

**Storage**: N/A (reads IRIS, writes OpenMetadata through the framework sink)

**Testing**: pytest. Unit: `overlay/ingestion/tests/unit/topology/database/test_iris.py` (new `Test002…` classes, no IRIS). Integration: `overlay/ingestion/tests/integration/iris/test_metadata_core.py` using `iris_cell` / `iris_service_connection`, asserting the "Expected OpenMetadata entities" table of the fixtures contract on every matrix cell; workflow run in-process with a test sink or against a local OpenMetadata, as spec 000 established

**Target Platform**: macOS/Linux dev machines and CI (matrix cells owned by spec 001)

**Project Type**: connector overlay on a pinned OpenMetadata tree (work in `.om/`, commit only `overlay/` and `patches/` after `make om-export`, ADR-0014)

**Performance Goals**: none beyond the framework (constitution: measured problem first)

**Constraints**: SELECT-only login must work (IV); direct SQL only in `queries.py`; identity `(schema, name[, column])`, never name alone, no case change (III, ADR-0005); no Python skip logic for filters (ADR-0009); type conversion only through the existing type map, `types.py` untouched (spec 003); no credentials in warnings or logs

**Scale/Scope**: touches `metadata.py`, `queries.py`, new `lineage.py`, `service_spec.py`, `irisConnection.json` (only if a default pattern is added), `test_iris.py`, new `test_metadata_core.py`, `GAP-REPORT.md`; fixtures additions (`Scratch` schema first use) by contract

## Constitution Check

*Constitution v1.2.2. Gate before Phase 0; re-checked after Phase 1 design.*

| Gate | Result |
|---|---|
| I. Framework First: extend `CommonDbSourceService`; override only where reflection is wrong for IRIS; lineage via `LineageSource`; mark-deleted, override and filters are framework options | Pass |
| II. Official Driver Only | Pass (no new driver use) |
| III. IRIS Fidelity: `(schema, name)` keys, joins on both, case kept, type map only called; regression test fails on name-only maps | Pass |
| IV. Least Privilege: every read works with SELECT only; gaps become warnings | Pass |
| V. Nothing Silent: `report_access_gap` per object feature, `IRIS-ACCESS` format fixed by the warnings contract; each reflection workaround gets a Gap Report entry; no hidden patches | Pass |
| VI. Tested on the Matrix: unit tests plus integration on every cell with shared fixtures only; the one new fixture object (`Scratch` use) is added through the fixtures contract | Pass |
| VII. Upstream-Ready: `make py_format` in `.om/` before `om-export`; license header on new Python files | Pass (task) |
| VIII. English Artifacts | Pass |
| Workflow: "A spec starts only after the spikes it depends on have reviewed findings" — SPIKE-02 findings (`spikes/findings/SPIKE-02.md`) are **not present** (only SPIKE-01 exists) | **Conditional**: see Complexity Tracking |

Post-design re-check: unchanged; the one conditional stays open until research.md's comparison table is
confirmed by evidence.

## Project Structure

### Documentation (this feature)

```text
specs/002-metadata-core/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── access-gap-helper.md
│   └── catalog-facts.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
overlay/ingestion/src/metadata/ingestion/source/database/iris/
├── metadata.py      # + report_access_gap, per-feature reads, description/key/view-definition overrides
├── queries.py       # + INFORMATION_SCHEMA constants (bind parameters, keyed on schema+name)
├── lineage.py       # NEW: IrisLineageSource(LineageSource), view lineage
├── service_spec.py  # + lineage_source_class=IrisLineageSource
└── types.py         # untouched (spec 003)

overlay/ingestion/tests/
├── unit/topology/database/test_iris.py          # + Test002… (helper, identity regression, lineage wiring)
└── integration/iris/test_metadata_core.py       # NEW: fixtures-contract assertions per cell

patches/ …irisConnection.json (only if a default pattern is added; then connection contract + ADR-0009 updated)
GAP-REPORT.md                                    # + one entry per inspector workaround and unparsable view
```

**Structure Decision**: extend the existing connector package only; no new modules besides `lineage.py`.

### Delivery order

1. `report_access_gap` + unit tests, alone (own commit/PR; spec 005 needs it by Dec 2).
2. Inspector-vs-catalog comparison on fixtures, all tracks → fill research.md.
3. Hierarchy, columns, keys, descriptions, view definitions (inspector or catalog per research.md).
4. View lineage (`lineage.py`, `service_spec.py`).
5. Filter/mark-deleted/override/access-gap integration tests; Gap Report entries.

Commits happen only when the developer asks.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| SPIKE-02 findings missing (workflow gate) | The user asked the plan to proceed; the comparison is made the first implementation task and its result decides which facts use catalog queries | Blocking the plan would also block step 1 (helper), which does not depend on the comparison. Steps 3–4 MUST NOT start before research.md's table is confirmed |
