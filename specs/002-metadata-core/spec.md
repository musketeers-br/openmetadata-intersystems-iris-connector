# Feature Specification: Metadata Core Ingestion

**Feature Branch**: `002-metadata-core`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "Ingest the contents of an IRIS Namespace into OpenMetadata: Namespace as Database, SQL schemas as Database Schemas, tables and views with columns, primary/foreign/unique keys, view definitions, descriptions and view lineage; same-name tables in different schemas stay separate; names keep their case; system content excluded by default through user-changeable filter patterns; mark-deleted and description-override options; access problems become status warnings, never run failures."

## Clarifications

### Session 2026-11-25

- Q: Framework reflection or direct catalog queries? → A: Framework reflection by default; where it is wrong or incomplete for IRIS (keys, view definitions, descriptions), a direct `INFORMATION_SCHEMA` query keyed on `(schema, name)` is used and a Gap Report entry is added (ADR-0005, ADR-0013).
- Q: Are `Ens*` schemas system content? → A: Settled by evidence: they appear in a plain `USER` Namespace, so `^Ens` stays a default exclusion (ADR-0009); any new default pattern is recorded in ADR-0009 and the connection contract.
- Q: Generated or deprecated classes? → A: Excluded only if expressible as a name pattern; otherwise documented with a Gap Report entry (ADR-0009).
- Q: Source of column descriptions? → A: `INFORMATION_SCHEMA.COLUMNS.DESCRIPTION` when reflection does not return them (confirmed during planning).
- Q: Stored procedures? → A: Not ingested.
- Q: View lineage parsing? → A: OpenMetadata's default parsing for unknown dialects (ANSI); views it cannot parse are listed in the Gap Report.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ingest the structure of a Namespace (Priority: P1)

A data engineer runs a metadata ingestion on an IRIS service. OpenMetadata ends up with one Database named exactly like the Namespace, one Database Schema per SQL schema, and under each schema every table and view, each marked with its type (table or view). Each table or view lists its columns with name, ordinal position, nullability, default value, length, precision and scale.

**Why this priority**: Without the hierarchy and columns there is nothing to catalog; every other story builds on it.

**Independent Test**: Ingest the shared sample dataset and compare the resulting hierarchy, names, types and columns with the fixtures contract.

**Acceptance Scenarios**:

1. **Given** the shared sample dataset, **When** the ingestion runs, **Then** the Database, Database Schemas, tables, views and columns match the fixtures contract, including each asset's type and each column's position, nullability, default, length, precision and scale.
2. **Given** `Clinic.Patient` (4 columns) and `Billing.Patient` (2 columns), **When** the ingestion runs, **Then** two distinct assets exist, each with only its own columns, keys and descriptions.
3. **Given** names stored by IRIS in mixed or upper case, **When** the ingestion runs, **Then** every Database, schema, table and column name appears exactly as IRIS stores it, never upper- or lower-cased.
4. **Given** an Ingestion run that finishes, **When** its status is read, **Then** it is a success with no failure for the sample dataset.

---

### User Story 2 - Keys, constraints, definitions and descriptions (Priority: P1)

A data steward opens a table and sees its primary key, foreign keys and unique constraints. Each foreign key points to the referenced table in the right schema, even when another schema has a table with the same name. Views show their definition when the login can read it. Tables and columns show the descriptions stored in IRIS.

**Why this priority**: Keys, definitions and descriptions are what make the catalog useful for understanding data, not just listing it.

**Independent Test**: Ingest the sample dataset and compare each table's keys, each view's definition and every description with the fixtures contract.

**Acceptance Scenarios**:

1. **Given** the sample dataset, **When** ingestion runs, **Then** each table shows the primary key, foreign keys and unique constraints listed in the fixtures contract.
2. **Given** a foreign key whose referenced table name exists in two schemas, **When** ingestion runs, **Then** the key points to the table in the schema it really references.
3. **Given** a view whose definition the login can read, **When** ingestion runs, **Then** the view shows that definition.
4. **Given** tables and columns with descriptions in IRIS, **When** ingestion runs, **Then** each shows the same description, and objects without one show none.

---

### User Story 3 - Lineage from views to tables (Priority: P1)

A data steward opens a view and sees which tables it reads from.

**Why this priority**: Lineage is the main reason to catalog views and is explicitly required.

**Independent Test**: Ingest the sample dataset and open the lineage of `Clinic.ActivePatient`.

**Acceptance Scenarios**:

1. **Given** the view `Clinic.ActivePatient`, **When** ingestion runs, **Then** it has lineage from `Clinic.Patient` and `Clinic.Encounter`.
2. **Given** a view whose definition cannot be read, **When** ingestion runs, **Then** the view is still ingested without lineage and a warning is reported (see Story 6).

---

### User Story 4 - Choose what is ingested with filters (Priority: P2)

An administrator controls scope with schema and table filter patterns. By default system content is left out; the user can change the patterns, and include and exclude patterns behave as in other OpenMetadata database connectors.

**Why this priority**: Namespaces hold large amounts of system content; defaults must give a clean catalog while staying changeable.

**Independent Test**: Run ingestion three times on the sample Namespace: default filters, include pattern for `Clinic`, and defaults overridden.

**Acceptance Scenarios**:

1. **Given** the default filters, **When** ingestion runs, **Then** no system schema (names starting with `%`, `INFORMATION_SCHEMA`, and schemas starting with `Ens`) is ingested.
2. **Given** an include pattern for `Clinic`, **When** ingestion runs, **Then** only the `Clinic` schema and its contents are ingested.
3. **Given** the default exclusions are overridden, **When** ingestion runs, **Then** system schemas are ingested.
4. **Given** a table filter pattern, **When** ingestion runs, **Then** only matching tables and views (by name, within the allowed schemas) are ingested.

---

### User Story 5 - Keep the catalog in sync on re-runs (Priority: P2)

On a later run, tables dropped in IRIS are marked as deleted in OpenMetadata when the standard "mark deleted" option is on, and descriptions already curated in OpenMetadata are not overwritten unless the standard override option is set.

**Why this priority**: Scheduled re-runs are the normal mode of operation; the catalog must neither keep stale assets nor lose curated text.

**Independent Test**: Ingest, drop a table in IRIS, edit a description in OpenMetadata, ingest again with each option on and off.

**Acceptance Scenarios**:

1. **Given** a table dropped between two runs and "mark deleted" on, **When** the second run finishes, **Then** that table is marked deleted and the others are untouched.
2. **Given** the same drop and "mark deleted" off, **When** the second run finishes, **Then** the table is not marked deleted.
3. **Given** a description edited in OpenMetadata and the override option off, **When** the next run finishes, **Then** the edited description is kept.
4. **Given** the same edit and the override option on, **When** the next run finishes, **Then** the description from IRIS replaces it.

---

### User Story 6 - Access problems never fail the run (Priority: P1)

A login can list an object but not read one of its parts (columns, keys, view definition, description). The run still completes: the unreadable part is skipped, the object's full name and the part appear as a warning in the ingestion status, and everything else is ingested.

**Why this priority**: Least-privilege logins are a core use case; hidden gaps or failed runs would make the connector unusable or misleading.

**Independent Test**: Run ingestion as a login that cannot read parts of one fixture object and check the status.

**Acceptance Scenarios**:

1. **Given** a login that cannot read the columns, keys, view definition or description of one object, **When** ingestion runs, **Then** the run completes, the rest is ingested, and one warning names that object's full name, the part that was unreadable and the reason.
2. **Given** several unreadable parts on different objects, **When** ingestion runs, **Then** each appears as its own warning.
3. **Given** any such problem, **When** the run finishes, **Then** it is not reported as failed and no access problem appears only in debug logs.

---

### Edge Cases

- A Namespace with no non-system schemas or where filters exclude everything: the run succeeds with nothing to ingest and says so.
- A schema with no tables or views: the Database Schema is still created, empty.
- A table with no columns readable: the table is ingested without columns and a warning names it.
- A foreign key referencing a table the filters excluded or the login cannot see: the key is kept in the source table where possible and a warning is reported instead of failing.
- A view reading another view, or a table in a schema excluded by filters: lineage is created only to assets that exist in OpenMetadata; the rest is skipped without failing.
- Names with unusual characters, dots, spaces or mixed case: kept verbatim and still unique per `(schema, name)`.
- A table dropped and re-created between runs: it is active again after the next run.
- Objects invisible to the login cannot be detected; this is a documented limitation, not a warning.
- Column data types are whatever the type map returns; types it does not know follow spec 003.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: One IRIS service MUST map to exactly one Namespace, ingested as one Database named exactly like the Namespace.
- **FR-002**: Each SQL schema MUST be ingested as a Database Schema under that Database.
- **FR-003**: Tables and views MUST be ingested under their schema, each with its type (table or view).
- **FR-004**: Each table and view MUST be ingested with its columns: name, ordinal position, nullability, default value, length, precision and scale.
- **FR-005**: Primary keys, foreign keys and unique constraints MUST be ingested for tables.
- **FR-006**: A foreign key MUST point to the referenced table in the correct schema.
- **FR-007**: A view's definition MUST be ingested when the login can read it.
- **FR-008**: Table and column descriptions MUST be ingested.
- **FR-009**: Object identity MUST be `(schema, name)` (plus column name for columns); assets with the same name in different schemas MUST be separate assets with their own columns, keys and descriptions.
- **FR-010**: Names MUST keep exactly the case IRIS stores and MUST NOT be upper- or lower-cased.
- **FR-011**: System content MUST be excluded by default through schema and table filter patterns, not through code paths, and the user MUST be able to change them.
- **FR-012**: Include and exclude filter patterns MUST behave as in other OpenMetadata database connectors.
- **FR-013**: When the standard "mark deleted" option is on, tables dropped in IRIS MUST be marked deleted on the next run; when off, they MUST NOT be.
- **FR-014**: Existing descriptions in OpenMetadata MUST NOT be overwritten unless the standard override option is set.
- **FR-015**: Views MUST get lineage to the tables they read, limited to assets that exist in OpenMetadata.
- **FR-016**: If the login can list an object but cannot read one of its parts (columns, keys, view definition, description), the run MUST NOT fail; that part MUST be reported as a warning in the ingestion status with the object's full name, the part and the reason, and the rest MUST be ingested.
- **FR-017**: No access problem MUST appear only in debug logs.
- **FR-018**: Every capability MUST work with an ordinary SQL login holding only SELECT on the target schemas.
- **FR-019**: Column types MUST come from the connector's type map as it exists; type mapping rules are not defined here.
- **FR-020**: Credentials MUST NOT appear in logs, warnings or errors.
- **FR-021**: Wherever the framework's standard reflection is wrong or incomplete for IRIS, the connector MUST obtain the data from the catalog keyed on `(schema, name)` and record the gap in the Gap Report; table and column descriptions MUST come from the catalog when reflection does not return them.
- **FR-022**: Lineage MUST use OpenMetadata's default view parsing; a view it cannot parse MUST still be ingested and MUST be listed in the Gap Report, not fail the run.
- **FR-023**: Stored procedures MUST NOT be ingested.

### Key Entities

- **Database**: The OpenMetadata Database named after the service's Namespace.
- **Database Schema**: A SQL schema inside the Namespace.
- **Table / View**: An asset identified by `(schema, name)` with a type, columns, keys, optional description and (views) a definition.
- **Column**: Name, ordinal position, nullability, default value, length, precision, scale, optional description.
- **Key / Constraint**: Primary key, foreign key (with referenced schema and table) or unique constraint on a table.
- **Lineage edge**: A link from a table (or view) to a view that reads it.
- **Status warning**: An entry in the ingestion status naming an object's full name, the unreadable part and the reason.
- **Fixtures contract**: The shared description of the sample dataset's expected hierarchy, names, case, keys, descriptions and view definition.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every cell of the test matrix, the sample dataset ingests with 100% of the hierarchy, names, case, keys, descriptions and view definition listed in the fixtures contract and no failure.
- **SC-002**: `Clinic.Patient` shows exactly 4 columns and `Billing.Patient` exactly 2, as separate assets.
- **SC-003**: `Clinic.ActivePatient` shows lineage from exactly `Clinic.Patient` and `Clinic.Encounter`.
- **SC-004**: With default filters, zero system schemas are ingested; with an include pattern for `Clinic`, only `Clinic` is; with defaults overridden, system schemas appear.
- **SC-005**: A table dropped between two runs is marked deleted after the second run when the option is on, and only that table.
- **SC-006**: In every run with unreadable object parts, the run completes successfully and the number of warnings equals the number of unreadable parts, each naming its object's full name.
- **SC-007**: A curated description survives a re-run in 100% of cases when the override option is off.

## Assumptions

- The foundation (spec 000) exists: the IRIS service type, connection, Test connection and default system-schema exclusions are in place; this spec extends them.
- The fixtures contract and the shared sample dataset are provided by the shared fixture set; this spec does not create its own users or datasets. Its content is the reference for expected results.
- "Every matrix cell" means the IRIS release tracks and login types (administrator and least-privilege) of the project's test matrix.
- Default exclusions are `%`-prefixed schemas, `INFORMATION_SCHEMA` and `Ens`-prefixed schemas, per spec 000; this spec may add patterns. Generated or deprecated classes are excluded only if a name pattern can express it; otherwise they are documented, not excluded in code.
- The warning wording and the single helper that produces it follow the project's access-gaps decision; the full least-privilege matrix and documentation belong to spec 005.
- Objects invisible to the login are a documented limitation, not detected.
- Out of scope: data type mapping rules (spec 003), VECTOR detail (spec 004), the full least-privilege matrix and its documentation (spec 005), stored procedures, and more than one Namespace per service.
