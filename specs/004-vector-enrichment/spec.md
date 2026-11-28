# Feature Specification: VECTOR enrichment

**Feature Branch**: `004-vector-enrichment`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "Catalog IRIS VECTOR columns with their real type. IRIS's SQL catalog reports VECTOR columns as text; their element type and dimension exist only in the class dictionary. When the ingestion login can read the class dictionary, VECTOR columns are cataloged as vectors showing their element type and dimension, for example "VECTOR(DOUBLE, 3)". When it cannot, they stay cataloged as text, and the run reports one warning, once per run, naming the read-only grant that enables the detail. Reading the class dictionary is never required for anything else, and the check happens at most once per run. If a future IRIS release reports VECTOR directly in its SQL metadata, that information is used instead of the class dictionary. The documentation states the optional grant and what it enables."

**Covers**: FR-11, FR-12, FR-13 · **Architecture**: AD-7 · **ADRs**: [0006](../../docs/adr/0006-single-type-map.md), [0007](../../docs/adr/0007-vector-optional-enrichment.md), [0012](../../docs/adr/0012-shared-fixtures-and-matrix.md) (fixtures), [0015](../../docs/adr/0015-dialect-state-presets.md) (the dictionary probe) · **Spike**: SPIKE-03, decisions copied into [research.md](research.md) · **Builds on**: spec 003 (the type map and its column hook), spec 005 (fixture catalog v3, the access-gap guard), spec 000 (the dictionary probe and the optional Test Connection step)

**Cut priority**: first cut inside the MVP. If it is parked, VECTOR columns stay `VARCHAR`, which is
what the SQL catalog reports, and GAP-001 and GAP-002 say why.

## Clarifications

### Session 2026-11-26

- Q: Which grant? → A: `GRANT SELECT ON %Dictionary.PropertyDefinition` (SPIKE-03, agreed by both developers on 2026-11-26). It is the table the dialect and Test Connection already probe, so one optional grant covers VECTOR detail, the dialect's full reflection and the Test Connection hint. `%Dictionary.CompiledProperty` is not needed.
- Q: Which query, and how many? → A: One read per run of every `%Library.Vector` property in the Namespace, joined to the SQL tables through `INFORMATION_SCHEMA.TABLES.CLASSNAME` (research R2). The column's SQL name is the property's `SqlFieldName` when set, else its `Name`.
- Q: How is the missing grant detected? → A: The dialect-state preset of ADR-0015 already reads `%Dictionary.PropertyDefinition` once per engine. Without access, the query is not run and the hint is recorded. A `SQLCODE -99` from the query itself also gives the hint.
- Q: OpenMetadata representation? → A: `dataType = ARRAY`, `arrayDataType = <element type>`, `dataTypeDisplay = VECTOR(<TYPE>, <dim>)`. SPIKE-03 checked that the ingestion framework carries all three for five element types. pgvector and MariaDB give nothing better (`NULL`, or a failed read). The UI check needs an OpenMetadata server built from the overlay.
- Q: Element types? → A: `DOUBLE`, `FLOAT`, `DECIMAL`, `INT` (and `INTEGER`), `STRING` map to the same-named OpenMetadata types (`INT` for both integer spellings). Any other element type gives `arrayDataType = UNKNOWN` and one warning for that column.
- Q: Narrower grant than the whole dictionary table? → A: SPIKE-03 found a column-level grant on `CompiledProperty`, which is not needed now. The documented grant is the single table above.
- Q: When is the hint emitted for a login without the grant? → A: Once per run, on the first `varchar` column read (any of them may be a VECTOR). A login without the grant cannot tell a VECTOR column from a `VARCHAR` one, so it cannot wait for "the first VECTOR column". Reviewed with Henry on 2026-11-26: once per run is accepted, with conditional text (it says "if this Namespace has VECTOR columns"), and only when the dictionary check fails.

## User Scenarios & Testing *(mandatory)*

Actors: the **data steward** and the **ML engineer** who look for embedding columns in OpenMetadata,
and the **IRIS administrator** who decides whether to give the optional grant.

### User Story 1 - VECTOR columns show their element type and dimension (Priority: P1)

With the optional grant, every VECTOR column is cataloged as a vector: an array of its element type,
displayed as IRIS declares it, for example `VECTOR(DOUBLE, 3)`.

**Why this priority**: IRIS's vector search is a main reason to use IRIS for AI workloads. A
catalog that calls embedding columns "text" hides them from the people looking for them.

**Independent Test**: ingest `AI.Embedding` as the dictionary-granted login and read the cataloged
columns `Vec`, `Vec4` and `vec_low`.

**Acceptance Scenarios**:

1. **Given** the shared fixtures, **When** `omd_reader_dict` or the administrator ingests them on any
   track, **Then** `AI.Embedding.Vec` has data type `ARRAY`, array data type `DOUBLE` and display
   `VECTOR(DOUBLE, 3)`.
2. **Given** `AI.Embedding.Vec4 VECTOR(INT, 4)`, **When** it is ingested with the grant, **Then** it
   is `ARRAY` of `INT`, displayed `VECTOR(INT, 4)`.
3. **Given** a VECTOR column whose SQL name differs from its property name (`"vec_low"`), **When** it
   is ingested with the grant, **Then** it is enriched under its SQL name.
4. **Given** the grant, **When** any non-VECTOR column is ingested, **Then** its type is the one spec
   003's table gives, unchanged.

---

### User Story 2 - Without the grant, nothing breaks and one hint says what to grant (Priority: P1)

Without the grant, VECTOR columns stay `VARCHAR` with the length the SQL catalog reports, and the run
reports one hint, once per run, with the exact grant to add.

**Why this priority**: the grant must never be a prerequisite (constitution IV), and a missing
optional grant must not flood the status (one hint per run).

**Independent Test**: ingest the fixtures as `omd_reader` and count the hints: exactly one for the
run; the VECTOR columns are `VARCHAR`.

**Acceptance Scenarios**:

1. **Given** `omd_reader`, **When** a metadata ingestion runs, **Then** `AI.Embedding.Vec` is
   `VARCHAR(1037)` and the status holds exactly one `IRIS-VECTOR-GRANT` warning naming
   `GRANT SELECT ON %Dictionary.PropertyDefinition TO omd_reader`.
2. **Given** `omd_reader`, **When** many tables are ingested in one run, **Then** there is still
   exactly one hint.
3. **Given** a login with the grant, **When** a run completes, **Then** there is no hint.
4. **Given** any login, **When** the run completes, **Then** nothing else is lost: every other column,
   key and description is as without this spec.

---

### User Story 3 - Odd dictionary values do not break the column (Priority: P2)

A VECTOR column whose dictionary parameters cannot be parsed, or whose element type is not known,
is still cataloged, and one warning names that column.

**Why this priority**: the dictionary is free text (`DATATYPE,DOUBLE,LEN,3`); a future IRIS release
or a hand-written class can put anything there.

**Independent Test**: feed the enrichment a parameter string without `LEN`, and one with an element
type the table does not know; each gives one warning for its column and a cataloged column.

**Acceptance Scenarios**:

1. **Given** parameters that cannot be parsed, **When** the column is ingested, **Then** it stays
   `VARCHAR` with its catalog length, and the status holds one `IRIS-VECTOR-PARAMS` warning keyed on
   that column's FQN.
2. **Given** an element type with no row (DDL accepts only the five of FR-003, so this comes from a
   hand-written class or a future release), **When** the column is ingested,
   **Then** it is `ARRAY` with array data type `UNKNOWN`, its display shows the IRIS type, and one
   `IRIS-VECTOR-PARAMS` warning names the column.

---

### User Story 4 - Native SQL metadata wins when IRIS provides it (Priority: P3)

If a future IRIS release reports VECTOR in `INFORMATION_SCHEMA.COLUMNS`, the column is cataloged
from that, and the dictionary is not read for it.

**Why this priority**: the dictionary is a workaround for GAP-001. When IRIS fixes it, the connector
should follow without a release.

**Independent Test**: a unit test feeds a catalog row whose `DATA_TYPE` says `vector`; the column is
`ARRAY`, and no dictionary result is used for it.

**Acceptance Scenarios**:

1. **Given** a column the SQL catalog reports as `vector`, **When** it is ingested, **Then** it is
   `ARRAY`, its display is the catalog's text, and the dictionary result is not used for it.
2. **Given** a run where no column needs the dictionary (every VECTOR is native), **When** it runs as
   a login without the grant, **Then** no hint is recorded.

### Edge Cases

- A class-defined table whose VECTOR property is inherited is not in `PropertyDefinition` (it holds
  only the properties a class defines). Its column stays `VARCHAR`, with no warning. The docs say
  so. Not seen in the fixtures; recorded in research.
- A VECTOR property of a class whose table the login cannot see: the join through
  `INFORMATION_SCHEMA.TABLES` leaves it out.
- Two schemas with the same table name: matched by `(schema, table, column)` from the join, never by
  table name alone (Principle III).
- Dimension `LEN` missing or not a positive integer: one `IRIS-VECTOR-PARAMS` warning; the column
  stays `VARCHAR`.
- Element type spelled in another case (`double`): matched case-insensitively; the display uses
  upper case.
- A failed dictionary query for a reason other than privileges (for example a timeout): one hint for
  the run, with the reason's first line. VECTOR columns stay `VARCHAR`, and the run goes on.
- Views over VECTOR columns: the dictionary has no property for a view's column, so it stays
  `VARCHAR` (the SQL catalog's type). Documented.

## Requirements *(mandatory)*

### Functional Requirements

**Enrichment**

- **FR-001**: When the login can read `%Dictionary.PropertyDefinition`, every column of a table whose
  class defines it as `%Library.Vector` MUST be cataloged with `dataType = ARRAY`,
  `arrayDataType = <element type>` and `dataTypeDisplay = VECTOR(<TYPE>, <dim>)`, where `<TYPE>` and
  `<dim>` come from the property's `DATATYPE` and `LEN` parameters.
- **FR-002**: The dictionary MUST be read at most once per run, in one query for the whole Namespace.
  Its result MUST be kept for the run and matched by `(schema, table, column)`.
- **FR-003**: The element type table MUST be in `iris/types.py`, section
  `--- 004: VECTOR enrichment ---`: `DOUBLE`, `FLOAT`, `DECIMAL`, `INT`, `INTEGER`, `STRING`. Any other
  value MUST give `arrayDataType = UNKNOWN` and one `IRIS-VECTOR-PARAMS` warning for the column.
- **FR-004**: Columns that are not VECTOR MUST keep spec 003's type. The enrichment MUST run after
  spec 003's type map, at the same per-table hook, and MUST NOT change names, order, descriptions or
  keys.

**Without the grant**

- **FR-005**: Without access, VECTOR columns MUST stay as spec 003 catalogs them (`VARCHAR` with the
  catalog length), and the status MUST hold exactly one warning per run, keyed on the Database FQN:
  `IRIS-VECTOR-GRANT: if this Namespace has VECTOR columns, GRANT SELECT ON %Dictionary.PropertyDefinition TO <username> to catalog their element type and dimension`.
  It MUST be emitted only when the dictionary check fails (no access, or the query fails), never
  when the dictionary was read.
  The username MUST be the connection's login; nothing else from the connection (no password, no URL).
- **FR-006**: Access MUST be taken from the dialect-state preset of ADR-0015 when it is known, so a
  login without the grant runs no dictionary query at all. A `SQLCODE -99` or any other database
  error from the query MUST also give the hint, never fail the run, and never an `IRIS-ACCESS`
  warning per table.
- **FR-007**: No feature other than VECTOR detail MAY depend on this read (constitution IV).

**Parsing**

- **FR-008**: The parameter string MUST be parsed as comma-separated key/value pairs, with keys
  matched case-insensitively. A missing or unusable `DATATYPE` or `LEN` MUST give one
  `IRIS-VECTOR-PARAMS` warning keyed on the column FQN, with the raw parameters in the message, and
  the column MUST stay `VARCHAR`.

**Native metadata**

- **FR-009**: A column whose `DATA_TYPE` the SQL catalog reports as a vector type MUST be cataloged as
  `ARRAY` from the catalog's own text, and the dictionary result MUST NOT be used for it. A run in
  which no column needs the dictionary MUST NOT emit the hint.

**Fixtures**

- **FR-010**: `AI.Embedding` MUST gain `Vec4 VECTOR(INT, 4)` and `"vec_low" VECTOR(FLOAT, 2)`, with
  values in its row. The self-check MUST verify their `DATA_TYPE` (`varchar`). The catalog version
  MUST go up by one with a history line. The change is additive.

**Tests**

- **FR-011**: Integration tests marked `iris` MUST check, on every matrix cell, branching on
  `iris_cell.has_dict_grant`:
  - with the grant: the three VECTOR columns as FR-001, and no hint;
  - without it: `VARCHAR` with catalog lengths, and exactly one hint for a run over all fixtures.
- **FR-012**: Unit tests MUST cover the parser (good, missing keys, bad dimension, unknown element
  type, case), the once-per-run read and hint, the native-metadata branch, and that a failing query
  gives one hint.

**Documentation**

- **FR-013**: `quickstart.md` MUST hold a short "VECTOR columns" note for the docs (spec 008): the
  grant, what it enables, what happens without it, the inherited-property and view limits. Spec 005's
  grants table MUST point at it.
- **FR-014**: In the same change:
  - ADR-0007 MUST become plain *Accepted*, with the grant, the representation and its evidence;
  - GAP-001 and GAP-002 MUST name `PropertyDefinition` and carry per-track results;
  - the Test Connection step message MUST name `PropertyDefinition` (already so in spec 000).

### Key Entities

- **VECTOR property**: `(schema, table, column)` → raw `Parameters`, from one dictionary read per run.
- **VECTOR facts**: element type, dimension, parsed from `Parameters`.
- **Element type row**: IRIS `DATATYPE` → OpenMetadata `DataType`.
- **Grant hint**: one per run, keyed on the Database FQN, naming the login.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all three tracks, the three fixture VECTOR columns show element type and dimension
  for the administrator and the dictionary-granted login.
- **SC-002**: For the plain login, exactly one grant hint per run, whatever the number of tables, and
  the VECTOR columns are cataloged as text with their catalog length.
- **SC-003**: The dictionary is read at most once per run (counted in a test).
- **SC-004**: A VECTOR column with unusable parameters gives exactly one warning naming it, and the
  run completes.
- **SC-005**: Zero changes to any non-VECTOR column of the fixtures, for every login.

## Assumptions

- `INFORMATION_SCHEMA.TABLES.CLASSNAME` gives the projecting class for every visible table, for any
  login that sees the table (research R2, two tracks; SPIKE-03 for the dictionary itself on three).
- The dictionary grants reveal class and property names of the whole Namespace (SPIKE-03). Spec 005's
  grants table says so next to this grant.
- OpenMetadata 2.1.1's UI shows `ARRAY` columns with their `dataTypeDisplay`. This is checked when an
  OpenMetadata server built from the overlay is available (research R5); until then the evidence is
  the ingestion framework's output.
- Specs 003 and 005 merge first; this branch starts from 005 (fixture catalog v3).

## Out of Scope

- Profiling vector contents, similarity search, embedding models.
- Inherited VECTOR properties (`CompiledProperty` would be needed; not seen in practice).
- VECTOR columns of views.
- The documentation site itself (spec 008 takes the note).
