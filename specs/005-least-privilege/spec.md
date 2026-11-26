# Feature Specification: Least privilege and access-gap reporting

**Feature Branch**: `005-least-privilege`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "Make IRIS ingestion work with an ordinary SQL login and never skip anything silently. Everything the connector offers — metadata, profiler, data-quality tests, dbt lineage — works with a login that only has SELECT on the objects to catalog, except VECTOR detail, which follows its own optional grant. The documentation lists the minimal grants per feature, as copy-paste SQL. Any object the login can list but not read, or any part of it it cannot read (columns, keys, view definition, description, sample data, profile), is reported as a warning in the ingestion status with the object's full name, the part that failed and the reason, and the run continues. Nothing about an access problem appears only in debug logs. Objects the login cannot see at all cannot be reported by that login; this is documented as a known limitation, unless IRIS offers a catalog view an ordinary login can query to detect them. The shared sample data gains a table the least-privilege logins can see but not read."

**Covers**: FR-14, FR-15 · **Architecture**: AD-8 · **ADRs**: [0007](../../docs/adr/0007-vector-optional-enrichment.md) (VECTOR grant), [0008](../../docs/adr/0008-access-gaps-as-warnings.md), [0012](../../docs/adr/0012-shared-fixtures-and-matrix.md) (fixtures), [0013](../../docs/adr/0013-gap-report.md) · **Spike**: SPIKE-03, decisions copied into [research.md](research.md) · **Builds on**: spec 001 (shared fixtures, the matrix, `iris_cell`), spec 002 (`IrisSource` and the `report_access_gap` helper), spec 003 (fixture catalog v2, the type map's column read)

## Clarifications

### Session 2026-11-26

- Q: How is a table made visible but unreadable? → A: SPIKE-03 answered it. A login without `SELECT` on a table does not see it at all, and a table-level `REVOKE` does not override a schema-level `GRANT`. A table becomes visible but unreadable when the login holds a privilege other than `SELECT` on it (`GRANT REFERENCES`), or `SELECT` on some of its columns only. The fixture uses both, in a schema the readers have no schema-level grant on.
- Q: Are invisible objects detected? → A: No. They stay a documented limitation (ADR-0008, GAP-003), agreed by both developers on 2026-11-26. SPIKE-03 found that a third optional grant (`%Dictionary.CompiledClass`) would make detection possible; it is a possible later extra, not part of this spec.
- Q: Where are the grants documented? → A: In this spec's `quickstart.md`, as a grants table with copy-paste SQL; spec 008 moves it into the docs page.
- Q: Profiler and data-quality grants? → A: `SELECT` is expected to be enough. Spec 006 confirms it when it lands; the table keeps those rows marked as expected until then.
- Q: Warning format? → A: `IRIS-ACCESS` from the warnings contract: key = the object's FQN, message `IRIS-ACCESS: cannot read <feature> of <Schema>.<Object>: <first line of SQL error>`, once per object and feature.
- Q: What does a metadata run do on a visible-but-unreadable table today? → A: Checked on 2026-11-26 (research R2): every catalog read succeeds (columns, keys, description, types), so the table is cataloged with no warning at all. With a column-level grant, the columns the login cannot read are missing from the catalog, also with no warning. Detecting this needs a read of the object itself, so the connector checks each cataloged table and view once per run.

## User Scenarios & Testing *(mandatory)*

Actors: the **IRIS administrator** who creates the ingestion login and decides its grants, the
**data steward** who reads the ingestion status in OpenMetadata, and the **connector developers** and
their coding agents (add reads that must not fail silently).

### User Story 1 - An ordinary SQL login ingests everything it can read (Priority: P1)

The IRIS administrator creates a login with `SELECT` on the schemas to catalog and nothing else.
Metadata ingestion catalogs every table and view of those schemas with their columns, types, keys,
descriptions and view definitions, as it would for the administrator. Only VECTOR detail needs its
own optional grant.

**Why this priority**: production IRIS sites do not hand an administrator login to a catalog tool
(constitution, Principle IV). If the plain login loses features, the connector is not usable there.

**Independent Test**: run the whole connector test suite as the least-privilege login on every
track; it passes, except the VECTOR detail that spec 004 gates on its grant.

**Acceptance Scenarios**:

1. **Given** the shared fixtures, **When** the connector's tests run as `omd_reader` on any track,
   **Then** they pass with the same expected catalog as the administrator for every schema the login
   can read.
2. **Given** a login with `SELECT` on the schemas only, **When** a metadata ingestion runs, **Then**
   it completes and produces no access warning for any object in those schemas.
3. **Given** the dictionary grant is missing, **When** ingestion runs, **Then** nothing core is lost
   and VECTOR columns follow ADR-0007 (cataloged as their SQL type, one hint).

---

### User Story 2 - What cannot be read is reported, and the run goes on (Priority: P1)

When the login can list an object but cannot read it, or cannot read one part of it, the ingestion
status shows one warning per object and part, with the object's full name, the part that failed and
the database's reason. The object is still cataloged with what could be read, and the run finishes.

**Why this priority**: an object cataloged with no sign that its data is unreadable, or with columns
silently missing, misleads the steward and every downstream feature (profiler, data quality). The
requirement is "reported, not skipped" (Principle V).

**Independent Test**: ingest the fixture schema `Restricted` as a least-privilege login and count the
access warnings: exactly one per restricted table, each naming its FQN; the run completes and every
other asset is intact.

**Acceptance Scenarios**:

1. **Given** `Restricted.Secret`, visible to the readers but not readable, **When** a metadata
   ingestion runs as `omd_reader` or `omd_reader_dict`, **Then** the status holds exactly one
   `IRIS-ACCESS` warning keyed on `iris_test.USER.Restricted.Secret`, the table is cataloged with its
   columns, and the run completes.
2. **Given** `Restricted.ColumnGrant`, where the readers hold `SELECT` on one column only, **When**
   it is ingested by a reader, **Then** the status holds exactly one `IRIS-ACCESS` warning for it,
   so the steward knows its cataloged columns may be incomplete.
3. **Given** the same tables, **When** the administrator ingests them, **Then** there is no access
   warning and every column is cataloged.
4. **Given** a read of one part of an object fails (columns, keys, description, view definition,
   types, data), **When** the run continues, **Then** the other parts of that object and all other
   objects are still cataloged.
5. **Given** listing the tables or the views of one schema fails, **When** the run continues,
   **Then** the status holds one `IRIS-ACCESS` warning keyed on that schema's FQN and the other
   schemas are still cataloged.
6. **Given** the readable fixtures (`Clinic`, `Billing`, `AI`, `Types`), **When** any matrix login
   ingests them, **Then** there is no access warning for them.

---

### User Story 3 - No silent path is left in the connector (Priority: P2)

Every place in the connector that reads from IRIS and can fail on privileges ends in a status warning
or lets the error stop the run. A developer who adds a read that catches an error and only logs it
gets a failing test.

**Why this priority**: the connector grows with every spec (004, 006, 007, 010). The guarantee of
User Story 2 has to hold for code written later, not only for today's reads.

**Independent Test**: add a read that catches a database error and only logs it; the guard test
fails and names the file and line.

**Acceptance Scenarios**:

1. **Given** each catalog read of the connector, **When** a unit test makes it raise a database
   error, **Then** the status holds an `IRIS-ACCESS` warning for that object and feature, not only a
   log record.
2. **Given** a handler in the connector's source code that catches a database error, **When** it
   neither records a status warning nor re-raises, and is not on the guard's short, reasoned allow
   list, **Then** the guard test fails naming the file and line.
3. **Given** an access warning, **When** its text is read, **Then** it holds no password, no
   connection URL and no row data.

---

### User Story 4 - The administrator knows exactly what to grant (Priority: P2)

The documentation has a minimal grants table: for each connector feature, the privilege it needs, as
SQL that can be pasted into IRIS, and what happens without it. It also states the limitation for
objects the login cannot see at all.

**Why this priority**: administrators grant what the docs say. A precise table avoids both
over-granting and support questions about missing objects.

**Independent Test**: create a fresh login with exactly the SQL from the table for "metadata", run
the metadata tests as that login, and they pass.

**Acceptance Scenarios**:

1. **Given** the grants table, **When** an administrator runs its "metadata" SQL for one schema,
   **Then** that login ingests the schema's tables and views without access warnings.
2. **Given** the grants table, **When** it is read, **Then** it has rows for metadata, view
   definitions, the profiler, data-quality tests, dbt lineage and VECTOR detail (optional), each
   with its SQL and its effect when missing; rows owned by later specs are marked as expected until
   those specs confirm them.
3. **Given** the docs, **When** they describe objects the login cannot see, **Then** they say that
   such objects are not cataloged and cannot be reported, and how to check for them as an
   administrator.

---

### Edge Cases

- A table the login holds no privilege on at all is invisible: not listed, not reported. This is the
  documented limitation (GAP-003); the fixture has one (`Restricted.Hidden`) to prove it.
- A table-level `REVOKE` does not override a schema-level `GRANT` in IRIS: revoking one table from a
  granted schema leaves it readable. The grants docs say so, because administrators expect the
  opposite.
- A column-level `SELECT` hides the other columns from the SQL catalog, and a read of all columns
  fails. The table is cataloged with the visible columns and one warning.
- Schemas the pipeline's filter excludes are not read, so they produce no warning.
- Views: a view the login can list but not read gets the same check and the same warning as a table.
- A failure that is not a privilege error (for example a broken view or an internal error) on the
  same reads is reported the same way, with the database's reason.
- The same object and feature failing several times in one run (keys are read in three steps): one
  warning.
- A failed read leaves the connection usable for the next object.
- The dictionary grants (`%Dictionary.*`) reveal class and property names of the whole Namespace,
  not data. The grants table says so next to the optional grant.

## Requirements *(mandatory)*

### Functional Requirements

**Least-privilege ingestion**

- **FR-001**: Metadata ingestion MUST catalog tables, views, columns, types, keys, descriptions and
  view definitions with only `SELECT` on the schemas (or tables) to catalog. No core feature MAY
  require a `%Dictionary` grant, `%Native_ClassExecution` or any write privilege (constitution IV).
- **FR-002**: VECTOR element type and dimension MAY need the optional grant
  `GRANT SELECT ON %Dictionary.PropertyDefinition` (ADR-0007, decided after SPIKE-03); without it the
  behavior is spec 004's.

**Access-gap reporting**

- **FR-003**: Every read of one object's feature MUST go through the `report_access_gap` helper
  (ADR-0008): columns, keys, description, view definition, column types, the readability check
  (FR-005), and, when their specs land, sample data and profile. A failure MUST produce one
  `IRIS-ACCESS` status warning per object and feature per run, with the message format of the
  warnings contract, and the run MUST go on.
- **FR-004**: A failure to list the tables or the views of one schema MUST produce one `IRIS-ACCESS`
  warning keyed on that schema's FQN (`<service>.<Namespace>.<Schema>`), feature `tables` or
  `views`, and the run MUST go on with the other schemas. Today the framework only logs it.
- **FR-005**: The connector MUST check once per run that each cataloged table and view can be read,
  with a query that returns no rows. A failure MUST produce one `IRIS-ACCESS` warning for that
  object, feature `data`. The object MUST still be cataloged with what the catalog reads returned.
- **FR-006**: Warnings MUST NOT contain passwords, connection URLs or row data, and MUST carry only
  the first line of the database's error.
- **FR-007**: Nothing about an access problem MAY be reported only in logs. A log line MAY add
  detail next to the status warning.

**Fixtures**

- **FR-008**: The shared fixtures MUST gain schema `Restricted`, with no schema-level grant to the
  readers, holding:
  - `Restricted.Secret`: `GRANT REFERENCES` to both readers (visible, unreadable);
  - `Restricted.ColumnGrant`: `SELECT` on one column only to both readers (visible, partly readable);
  - `Restricted.Hidden`: no grant to the readers (invisible).

  The loader's self-check MUST verify, for each reader, what it can list and that its reads of these
  tables are refused. The catalog version MUST go up by one with a history line. The change is
  additive.

**Tests**

- **FR-009**: Integration tests marked `iris` MUST check, on every matrix cell:
  - for the readers, exactly one `IRIS-ACCESS` warning for `Restricted.Secret` and one for
    `Restricted.ColumnGrant`, both cataloged, `Restricted.Hidden` absent and not reported;
  - for the administrator, all three cataloged with no access warning;
  - for every login, no access warning on the readable fixtures, and the run completes.
- **FR-010**: Unit tests MUST make each read of FR-003 to FR-005 raise a database error and assert
  the status warning (code, key, feature), not a log record; and assert one warning when the same
  object and feature fail more than once.
- **FR-011**: A guard test MUST fail when the connector's source code catches a database error
  without recording a status warning or re-raising, outside a short allow list where each entry
  states why it is not an access gap (for example the dialect-state probe of ADR-0015).

**Documentation**

- **FR-012**: `quickstart.md` MUST hold the minimal grants table: one row per feature (metadata,
  view definitions, profiler, data-quality tests, dbt lineage, VECTOR detail), the SQL to grant it,
  and what happens without it. It MUST state the invisible-objects limitation, that a table-level
  `REVOKE` does not override a schema-level `GRANT`, that column-level grants hide columns, and that
  the dictionary grants reveal names of the whole Namespace.
- **FR-013**: ADR-0008 MUST be updated in the same change: the readability check and the schema
  listing join the decision, invisible objects stay a limitation with SPIKE-03's evidence, and its
  validation describes the `GRANT REFERENCES` fixture instead of a revoke.
- **FR-014**: GAP-003 MUST get a reproduction on the three tracks (the invisible fixture table) and
  its actual behavior from SPIKE-03.

### Key Entities

- **Access gap**: one object (table, view or schema) FQN, one feature (`columns`, `keys`,
  `description`, `view definition`, `data`, `tables`, `views`, later `sample data`, `profile`), and
  the first line of the database's error; reported once per run.
- **Restricted fixtures**: schema `Restricted` with `Secret`, `ColumnGrant` and `Hidden`, and the
  privilege each reader holds on each.
- **Grants table**: feature → SQL grant → effect when missing → owning spec.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all blocking matrix cells, the connector's whole test suite passes as each
  least-privilege login (VECTOR detail apart, per spec 004).
- **SC-002**: Each visible-but-unreadable fixture table produces exactly one access warning naming its
  full name for each reader, and zero for the administrator; the run completes on every cell.
- **SC-003**: Zero access warnings appear for the readable fixtures on every cell.
- **SC-004**: 100% of the connector's per-object reads have a test proving a failure becomes a status
  warning, and a read that only logs an access error makes a test fail.
- **SC-005**: A login created with only the "metadata" SQL of the grants table ingests the readable
  fixtures with no access warning.
- **SC-006**: The invisible-objects limitation is stated in the grants docs and GAP-003 has a
  reproduction checked on the three tracks.

## Assumptions

- SPIKE-03's results hold on the three tracks (checked there on 2026.1 and 2026.3), and the probe of
  2026-11-26 (research R2) shows that catalog reads succeed on a visible-but-unreadable table.
- One query that returns no rows per cataloged table and view is cheap enough to run on every
  ingestion; it reads no data.
- The `report_access_gap` helper of spec 002 stays the single place that turns read failures into
  warnings; this spec hardens and tests it and adds calls, without a second mechanism.
- Sample data and profile reads belong to spec 006, which calls the same helper; this spec only
  makes sure the helper and the guard test are ready for them.
- Specs 000 → 001 → 002 → 003 merge first; this branch starts from 003 (fixture catalog v2).

## Out of Scope

- Detecting objects the login cannot see (needs a third optional grant, `%Dictionary.CompiledClass`;
  a possible later extra agreed by both developers, only if time allows).
- Write privileges of any kind.
- Recovering the columns hidden by a column-level grant (the warning says the table is not fully
  readable; the columns themselves cannot be known by that login).
- Profiler and data-quality behavior on unreadable tables beyond calling the helper (spec 006).
- The documentation site itself (spec 008 moves the grants table there).
