# Feature Specification: Type mapping

**Feature Branch**: `003-type-mapping`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "Map every IRIS SQL data type to the right OpenMetadata data type, through one mapping table that metadata ingestion, profiling, tests and documentation all use. Columns are cataloged with the OpenMetadata data type that matches their IRIS type, keeping length, precision and scale where they apply, and with a display type that shows the original IRIS type when it carries more information. Any IRIS type not in the table is cataloged as OpenMetadata's unknown type, and the run reports it once per type per run as a warning in the ingestion status naming the type and the first column where it was seen; the run never fails because of a type. The mapping table is available in a form the documentation can publish without retyping it. The shared sample data gains one table with one column of each IRIS SQL type the catalog reports, so every mapping is tested on every release track."

**Covers**: FR-7 · **Architecture**: AD-6 · **ADRs**: [0006](../../docs/adr/0006-single-type-map.md), [0007](../../docs/adr/0007-vector-optional-enrichment.md) (VECTOR stays out), [0012](../../docs/adr/0012-shared-fixtures-and-matrix.md) (fixtures), [0013](../../docs/adr/0013-gap-report.md) · **Spike**: none; the type list comes from discovery on the three tracks (research) · **Builds on**: spec 000 (`iris/types.py` with its section markers, `IrisConnection`), spec 001 (shared fixtures, the matrix, `iris_cell`), spec 002 (`IrisSource`, its column reading and the `IRIS-ACCESS` helper)

## Clarifications

### Session 2026-11-26

- Q: Where does the table live? → A: in `iris/types.py`, section `--- 003: type map ---`, as ADR-0006 decides. Ingestion, tests and the docs renderer all read it.
- Q: Which types get a row? → A: every value `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE` reports on `latest-em`, `latest-cd` and `latest-preview`, for the fixture table that has one column per IRIS SQL type and for the system tables of the `USER` Namespace. The draft in ADR-0006 is only a starting point.
- Q: `BIT`? → A: `BOOLEAN`.
- Q: Streams (`LONGVARCHAR`, `LONGVARBINARY`)? → A: `TEXT` and `BLOB`.
- Q: `%List` projections? → A: decided from what the catalog reports: `ARRAY` if the element type can be known, otherwise `UNKNOWN`.
- Q: Warning format? → A: `IRIS-UNKNOWN-TYPE: IRIS type '<type>' is not mapped; cataloged as UNKNOWN (first seen on <Schema>.<Table>.<Column>)`, keyed on the Database (Namespace) FQN, once per type per run (ADR-0006).

## User Scenarios & Testing *(mandatory)*

Actors: the **data steward** who browses IRIS tables in OpenMetadata, the **connector developers**
and their coding agents (add types, write tests), and the **documentation** (spec 008) that publishes
the type table.

### User Story 1 - Columns show the right type (Priority: P1)

After a metadata ingestion, every column of an IRIS table or view shows the OpenMetadata data type
that matches its IRIS type. Character and binary columns keep their length, exact numerics keep
precision and scale, and the display type shows the IRIS type as IRIS declares it (for example
`VARCHAR(120)`, `NUMERIC(5,2)`, `LONGVARCHAR`).

**Why this priority**: wrong types mislead every downstream use (search, data quality, lineage, the
profiler). Today `LONGVARCHAR` is cataloged as `VARCHAR(1)` and `VARCHAR(1)` as `CHAR` (GAP-008).

**Independent Test**: ingest the fixture table that has one column per IRIS SQL type and compare each
cataloged column (data type, length, precision, scale, display type) with the mapping table.

**Acceptance Scenarios**:

1. **Given** the shared fixtures, **When** a metadata ingestion runs as any matrix login, **Then**
   every column of every fixture table and view has the data type the mapping table gives for its
   IRIS type, with length, precision and scale where the table says they are kept.
2. **Given** a column declared `VARCHAR(1)`, **When** it is ingested, **Then** it is `VARCHAR` with
   length 1, not `CHAR`.
3. **Given** a column declared `LONGVARCHAR`, **When** it is ingested, **Then** it is `TEXT` and its
   display type says `LONGVARCHAR`.
4. **Given** the VECTOR column of the fixtures, **When** it is ingested, **Then** it is `VARCHAR`, as
   the SQL catalog reports it (spec 004 enriches it later).

---

### User Story 2 - An unknown type never breaks a run (Priority: P1)

When IRIS reports a type the table does not know, the column is still cataloged, with OpenMetadata's
unknown type, and the run reports the type once, naming the first column where it was seen. The run
finishes.

**Why this priority**: IRIS releases and customer schemas can carry types nobody listed. A single
unknown type must not stop the catalog of a whole Namespace (constitution, Principles III and V).

**Independent Test**: make the mapping table forget one type that a fixture column uses, ingest, and
count the warnings for that type: exactly one, and the column is `UNKNOWN`.

**Acceptance Scenarios**:

1. **Given** a type missing from the table and used by three columns in two tables, **When** one run
   ingests them, **Then** the ingestion status holds exactly one `IRIS-UNKNOWN-TYPE` warning for that
   type, naming the first column seen, and all three columns are `UNKNOWN`.
2. **Given** two distinct unmapped types, **When** one run meets both, **Then** there are two
   warnings, one per type.
3. **Given** a second run of the same pipeline, **When** it meets the same unmapped type, **Then** it
   reports it again once (the count is per run).
4. **Given** the shared fixtures, **When** any matrix cell ingests them, **Then** there are zero
   `IRIS-UNKNOWN-TYPE` warnings.

---

### User Story 3 - Every mapping is tested on every track (Priority: P2)

The shared fixtures gain one table with one column of each IRIS SQL type the catalog reports. Unit
tests check every row of the mapping table; integration tests on all nine matrix cells check how the
fixture table is cataloged.

**Why this priority**: the acceptance bar of every spec is "green on every blocking cell"
(Principle VI); a type that behaves differently on one release track must show up there.

**Independent Test**: run the matrix; the type tests pass on every cell, and removing a row from the
mapping table makes a test fail.

**Acceptance Scenarios**:

1. **Given** the fixture loader, **When** it runs on any track, **Then** the type table exists, both
   least-privilege logins can read it, and the self-check verifies it.
2. **Given** the mapping table, **When** a row is removed or changed, **Then** a unit test fails
   (the table cannot shrink silently).
3. **Given** a type reported on only some tracks, **When** the matrix runs, **Then** the test expects
   it only where the track reports it, and says which track in its result.

---

### User Story 4 - The docs table comes from the mapping (Priority: P3)

The documentation publishes the IRIS → OpenMetadata type table without retyping it: it is rendered
from the mapping module.

**Why this priority**: a hand-written docs table drifts from what ingestion does (ADR-0006). Spec 008
needs it, so it only has to exist and stay in sync now.

**Independent Test**: render the table and compare it with the committed copy; change a row in the
module and the comparison fails.

**Acceptance Scenarios**:

1. **Given** the mapping module, **When** the renderer runs, **Then** it produces a Markdown table
   with one row per IRIS type: OpenMetadata type, what is kept (length, precision and scale), and a
   note.
2. **Given** the committed rendered table, **When** the module changes without regenerating it,
   **Then** a test fails and says how to regenerate.

---

### Edge Cases

- A type's raw catalog name differs in case from the table key (`varchar` vs `VARCHAR`): matching is
  case-insensitive.
- Character types whose length the catalog reports as very large or absent (`LONGVARCHAR` reports
  2147483647): mapped to types that carry no length (`TEXT`, `BLOB`); the display type shows the IRIS
  type without the length.
- `VARCHAR(1)`: stays `VARCHAR` with length 1 (the dialect's `CHAR` is a defect, GAP-008).
- DDL synonyms (`INT` and `INTEGER`, `DATETIME` and `TIMESTAMP`, `TEXT` and `LONGVARCHAR`): the
  catalog reports one `DATA_TYPE` for each family; the table is keyed on what the catalog reports, so
  synonyms need no rows of their own.
- Views: their columns are mapped the same way as table columns.
- A login that cannot read a table's columns in `INFORMATION_SCHEMA.COLUMNS`: the column read already
  reports `IRIS-ACCESS` (spec 002); the type mapping adds no second warning for it.
- The same unmapped type in many columns or schemas: one warning per run, naming the first column
  seen.
- VECTOR: the catalog reports `varchar` with a length; it is mapped as `VARCHAR` here and enriched by
  spec 004 through its own section of `types.py`.

## Requirements *(mandatory)*

### Functional Requirements

**Mapping table**

- **FR-001**: The connector MUST have exactly one IRIS → OpenMetadata type table, in `iris/types.py`
  (section `--- 003: type map ---`). Each row maps one `INFORMATION_SCHEMA.COLUMNS.DATA_TYPE` value
  (matched case-insensitively) to one OpenMetadata `DataType`, says whether length, or precision and
  scale, are kept, and carries a short note. No other module MAY define or translate IRIS types.
- **FR-002**: The table MUST have a row for every `DATA_TYPE` value the IRIS SQL catalog reports on
  `latest-em`, `latest-cd` and `latest-preview`, for the fixture type table (FR-010) and for the
  system tables of the `USER` Namespace, as recorded in [research.md](research.md). A type reported on
  only some tracks keeps its row.
- **FR-003**: These rows MUST follow the decisions already taken: `bit` → `BOOLEAN`, `longvarchar` →
  `TEXT`, `longvarbinary` → `BLOB`, and `%List`-style projections → `ARRAY` when the element type is
  known, otherwise `UNKNOWN`.

**Cataloging columns**

- **FR-004**: The type of every ingested column (tables and views) MUST be resolved from the raw
  `DATA_TYPE`, `CHARACTER_MAXIMUM_LENGTH`, `NUMERIC_PRECISION` and `NUMERIC_SCALE` that
  `INFORMATION_SCHEMA.COLUMNS` reports for that column, read by `(schema, table, column)`, not from
  the type the dialect reflects (GAP-008).
- **FR-005**: The cataloged column MUST carry the mapped `dataType`, the length (`dataLength`) for
  rows that keep it, `precision` and `scale` for rows that keep them, and a `dataTypeDisplay` that
  shows the IRIS type with its parameters as the catalog reports them (for example `VARCHAR(120)`,
  `NUMERIC(5,2)`, `LONGVARCHAR`).
- **FR-006**: The VECTOR column (reported as `varchar`) MUST be cataloged as `VARCHAR` with its
  reported length. Spec 004 enriches it through the section `--- 004: VECTOR enrichment ---`; this
  spec MUST leave that section free.
- **FR-007**: The mapping MUST be applied at one place in `IrisSource`: where spec 002 reads a
  table's columns. It MUST NOT change how columns are read, their names, order, descriptions or keys.

**Unknown types**

- **FR-008**: A `DATA_TYPE` with no row MUST be cataloged as `UNKNOWN` and MUST produce one
  ingestion-status warning per distinct type per run, keyed on the Database FQN
  (`<service>.<Namespace>`), with the message
  `IRIS-UNKNOWN-TYPE: IRIS type '<type>' is not mapped; cataloged as UNKNOWN (first seen on <Schema>.<Table>.<Column>)`.
  The run MUST NOT fail because of a type.
- **FR-009**: The shared fixtures MUST produce zero `IRIS-UNKNOWN-TYPE` warnings on every matrix
  cell.

**Fixtures**

- **FR-010**: The shared fixtures MUST gain schema `Types` with table `Types.AllTypes`: a primary key
  and one column for each IRIS SQL type family the catalog reports separately, using parameters
  that show length, precision and scale. Both least-privilege logins get `SELECT` on schema `Types`.
  The loader's self-check MUST verify the table's columns and their `DATA_TYPE`, and the catalog
  version MUST go up by one with a history line. The change is additive (fixture rules).

**Tests**

- **FR-011**: Unit tests MUST check every row of the table, parametrized from the table itself, and
  MUST compare the table's keys with an explicit expected list so a row cannot disappear silently.
- **FR-012**: A unit test MUST show that an unmapped type yields `UNKNOWN` and exactly one warning per
  type per run, however many columns use it.
- **FR-013**: Integration tests marked `iris` MUST check, on every matrix cell, the cataloged type of
  every column of `Types.AllTypes` and of the other fixture tables, and that no `IRIS-UNKNOWN-TYPE`
  warning is produced. Expectations that differ by track MUST branch on `iris_cell.tag`.

**Documentation**

- **FR-014**: The module MUST provide a renderer that produces the Markdown type table from the
  mapping table. The rendered table MUST be committed in this spec's `contracts/type-mapping.md`, and
  a test MUST fail when the committed copy differs from a fresh rendering.
- **FR-015**: ADR-0006 MUST be updated in the same change: the starting table is replaced by a
  pointer to the generated table, and its GAP-008 sentence says what the reproductions showed (the
  `LONGVARCHAR` half comes from OpenMetadata's generic type parser, the `CHAR` half from the dialect).

### Key Entities

- **Type row**: one IRIS `DATA_TYPE` → OpenMetadata `DataType`, what is kept (length, or precision and
  scale, or nothing), and a note.
- **Column type facts**: per `(schema, table, column)`: raw `DATA_TYPE`, character length, numeric
  precision and scale, as the SQL catalog reports them.
- **Unknown-type report**: per run, the set of unmapped types already warned about, with the first
  column each was seen on.
- **Type fixture**: `Types.AllTypes`, one column per IRIS SQL type family.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all nine matrix cells, every column of the fixtures is cataloged with the data type,
  length, precision, scale and display type the mapping table gives, and zero unknown-type warnings
  appear.
- **SC-002**: 100% of the `DATA_TYPE` values the catalog reports on the three tracks (research) have a
  row and a test.
- **SC-003**: A type removed from the table, used by several columns, produces exactly one warning in
  one run and never fails the run.
- **SC-004**: The documentation table is regenerated from the module with one command, and a test
  catches a stale copy.
- **SC-005**: `VARCHAR(1)` and `LONGVARCHAR` columns are cataloged as `VARCHAR` (length 1) and `TEXT`
  (GAP-008 no longer affects the catalog).

## Assumptions

- OpenMetadata 2.1.1's `DataType` enumeration has every target used by the table (`BOOLEAN`, `TEXT`,
  `BLOB`, `TIMESTAMP`, `UUID`, `UNKNOWN`, and the numeric and character types).
- `INFORMATION_SCHEMA.COLUMNS` is readable for a table by any login that can read that table (checked
  for the fixtures in spec 001), so least-privilege logins get the same types as the administrator.
- The metadata core of spec 002 merges before this spec (agreed order 000 → 001 → 002); this spec
  adds one call where 002 reads columns.
- The profiler (spec 006) and the docs (spec 008) consume the same module later; this spec only
  exposes what they need (the table and the renderer).

## Out of Scope

- VECTOR element type and dimension (spec 004); the VECTOR column stays as the SQL catalog reports it.
- Which profiler metrics run on which types (spec 006).
- The documentation site itself (spec 008); this spec only produces the rendered table.
- Fixing the dialect's type reflection (GAP-008 stays reported, not patched).
