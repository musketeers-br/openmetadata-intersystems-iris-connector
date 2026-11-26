# Feature Specification: Connector Foundation

**Feature Branch**: `000-connector-foundation`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "Add InterSystems IRIS as a new database service type in OpenMetadata, developed in this repository as an overlay on a pinned OpenMetadata release: rebuild/write-back of the source tree, service type with its own icon and connection form, step-by-step Test connection, YAML workflow support, least-privilege login, optional `iris` extra, default exclusion of system schemas."

## Clarifications

### Session 2026-11-25

- Q: Where does connector code live? → A: In `overlay/` (new files) and `patches/` (edits to existing files), using OpenMetadata's own paths (ADR-0014); the working tree is `.om/`.
- Q: Which OpenMetadata version? → A: 2.1.1 (SPIKE-01), recorded in `openmetadata.version`.
- Q: Which driver? → A: Only the official `intersystems-irispython` 5.4.1 and `sqlalchemy-intersystems-iris` 1.0.2 (ADR-0002).
- Q: One or many Namespaces per service? → A: One (ADR-0004).
- Q: What is the Database name? → A: The Namespace, verbatim and case-preserved.
- Q: Does a failing dictionary step make Test connection fail? → A: No; the step is non-mandatory (test-connection contract).
- Q: TLS? Help panel? → A: Spec 008. This spec only registers the icon and the form.
- Q: How are patches named? → A: The OpenMetadata path with `/` replaced by `__`, plus `.patch` (repository-layout contract).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rebuild and write back the OpenMetadata tree (Priority: P1)

A developer (or coding agent) runs one command to get a working OpenMetadata source tree built from this repository: the pinned OpenMetadata release is checked out, the connector's new files are added, the small edits to existing OpenMetadata files are applied, and the tree is prepared for running and testing. A second command writes the changes made in that tree back into the repository, so the repository holds only the connector's own files and edits.

**Why this priority**: Every other story is developed and tested inside that tree; without a reproducible round trip nothing else can be built or reviewed.

**Independent Test**: From a clean clone, run the rebuild command, then the write-back command; the connector imports, its unit tests pass, and the repository shows no changed file.

**Acceptance Scenarios**:

1. **Given** a clean clone, **When** the developer runs the rebuild command, **Then** a tree exists in which the IRIS connector imports and its unit tests pass.
2. **Given** a freshly rebuilt tree with no edits, **When** the developer runs the write-back command, **Then** no file in the repository changes.
3. **Given** a developer edited a new connector file and an existing OpenMetadata file in the tree, **When** they run the write-back command, **Then** the new file and the edit to the existing file are captured in the repository, and nothing else is.
4. **Given** the write-back command was just run, **When** the rebuild and write-back commands run again in a row, **Then** the repository is unchanged.

---

### User Story 2 - Choose and configure "InterSystems IRIS" as a service (Priority: P1)

An administrator opens the list of database services in OpenMetadata, picks "InterSystems IRIS" (shown with its own icon), and fills in a connection form: host and port, Namespace, username and password, plus the standard connection options, connection arguments and schema/table filter patterns. One service connects to exactly one IRIS Namespace; that Namespace is what OpenMetadata shows as the Database. Credentials are masked like on any other service.

**Why this priority**: This is the visible entry point of the whole connector.

**Independent Test**: Open the service list in an OpenMetadata deployment built from the overlay and verify the IRIS entry, its icon and every form field; save a service and verify the password is masked.

**Acceptance Scenarios**:

1. **Given** an OpenMetadata deployment built from the overlay, **When** an administrator adds a database service, **Then** "InterSystems IRIS" appears in the list with its own icon.
2. **Given** the IRIS connection form, **When** it is opened, **Then** it offers host and port, Namespace, username, password, connection options, connection arguments and schema/table filter patterns.
3. **Given** a saved IRIS service, **When** it is viewed or fetched, **Then** the password is masked.
4. **Given** a new IRIS service, **When** the filter patterns are shown, **Then** system schemas (names starting with `%`, `INFORMATION_SCHEMA`, and interoperability schemas starting with `Ens`) are excluded by default and the user can change them.

---

### User Story 3 - Test connection step by step (Priority: P1)

The administrator runs Test connection. It reports each step separately: connect, list schemas, list tables, list views, read the class dictionary. On error it names the failing step and the likely fix. The class-dictionary step is optional: if the login cannot read it, Test connection still succeeds and shows a hint naming the optional read-only grant that enables full reflection (calculated columns, index details) and VECTOR detail.

**Why this priority**: It is how administrators know a service is usable, and it defines the least-privilege behavior.

**Independent Test**: Run Test connection against the IRIS Community test image as an administrator and as a plain reader, and with deliberately wrong host, port, Namespace and password.

**Acceptance Scenarios**:

1. **Given** an administrator login, **When** Test connection runs, **Then** all five steps pass, including the class-dictionary step.
2. **Given** a least-privilege login with only SELECT on the target schemas, **When** Test connection runs, **Then** connect, list schemas, list tables and list views pass, the class-dictionary step shows a hint naming the optional read-only grant, and the overall result is success.
3. **Given** a wrong host, port, Namespace or password, **When** Test connection runs, **Then** the "connect" step fails with a clear message naming the likely fix and no later step is reported as passed.
4. **Given** any failure, **When** the result is shown, **Then** the failing step is named and the message does not contain the password.

---

### User Story 4 - Run the same configuration from a YAML workflow (Priority: P2)

A data engineer writes a YAML ingestion workflow with the same fields as the form and runs it. The run creates the service and the Database named after the Namespace.

**Why this priority**: It proves the configuration is usable outside the UI, but depends on the service type existing.

**Independent Test**: Run a YAML workflow against the test image and check the service and the Database in OpenMetadata.

**Acceptance Scenarios**:

1. **Given** a YAML workflow with host, port, Namespace, username and password, **When** it runs, **Then** the IRIS service is created and a Database named after the Namespace exists under it.
2. **Given** the run, **When** its logs are inspected, **Then** no credential appears.

---

### User Story 5 - Optional driver install (Priority: P2)

A user installs the ingestion package. The InterSystems driver is installed only when they ask for the optional `iris` extra.

**Why this priority**: Keeps the licence terms and dependency pins of the driver out of the core install.

**Independent Test**: Install the ingestion package with and without the extra and list installed packages.

**Acceptance Scenarios**:

1. **Given** the ingestion package installed without the `iris` extra, **When** installed packages are listed, **Then** the IRIS driver is absent.
2. **Given** the package installed with the `iris` extra, **When** the connector runs, **Then** it connects using the driver.

---

### Edge Cases

- The Namespace does not exist or the login has no access to it: fails on the "connect" step with a message naming the Namespace.
- The login can connect but sees no schemas, tables or views: the corresponding steps fail or warn with the likely fix (missing SELECT grants), not a generic error.
- The IRIS driver is not installed when a service is tested or run: the failure says to install the `iris` extra.
- Filter patterns excluding every schema: the run proceeds with nothing to ingest and says so.
- The write-back command runs on a tree that was never rebuilt, or the pinned release cannot be fetched: it stops with a clear message and changes nothing.
- A user edits a file in the tree that is neither a connector file nor a tracked edit: write-back captures it as a new edit rather than dropping it silently.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A single rebuild command MUST produce, from a clean clone, an OpenMetadata source tree at the pinned release containing the connector's new files and the repository's edits to existing files, ready for running and testing.
- **FR-002**: A single write-back command MUST record the tree's changes in the repository as the connector's new files and edits to existing files only.
- **FR-003**: Running the rebuild and write-back commands in a row MUST leave the repository unchanged.
- **FR-004**: "InterSystems IRIS" MUST appear in the database service list with its own icon.
- **FR-005**: The connection form MUST offer host and port, Namespace, username, password, standard connection options, connection arguments and schema/table filter patterns.
- **FR-006**: One service MUST connect to exactly one IRIS Namespace, and the Database shown in OpenMetadata MUST be named after that Namespace, verbatim and case-preserved.
- **FR-007**: Credentials MUST be masked like on any other OpenMetadata service and MUST NOT appear in logs or error messages.
- **FR-008**: Test connection MUST report separately the steps connect, list schemas, list tables, list views and read the class dictionary.
- **FR-009**: On error, Test connection MUST name the failing step and the likely fix.
- **FR-010**: The class-dictionary step MUST be optional: when the login cannot read it, the overall test succeeds and a hint names the optional read-only grant (full reflection and VECTOR detail).
- **FR-011**: A wrong host, port, Namespace or password MUST fail on the "connect" step with a clear message.
- **FR-012**: The same configuration MUST work from a YAML ingestion workflow, and a run MUST create the service and the Database named after the Namespace.
- **FR-013**: Every step MUST work with a plain SQL login holding only SELECT on the target schemas, with no extra system resources.
- **FR-014**: The IRIS driver MUST be installed only through the optional `iris` extra of the ingestion package, never as a core dependency.
- **FR-015**: By default, schemas whose names start with `%`, `INFORMATION_SCHEMA`, and schemas starting with `Ens` MUST be excluded through filter patterns the user can change.

### Key Entities

- **IRIS service**: An OpenMetadata database service of type IRIS; holds connection details, options, arguments and filter patterns.
- **Database**: The OpenMetadata Database named after the service's single Namespace.
- **Overlay**: The connector's new files and edits to existing OpenMetadata files, kept in this repository against a pinned OpenMetadata release.
- **Test connection step**: One reported check (connect, list schemas, list tables, list views, read class dictionary) with a status, and on failure a likely fix or hint.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a clean clone, one command yields a tree where the connector's unit tests pass, and one more command leaves the repository with zero changed files, in 100% of runs.
- **SC-002**: IRIS is selectable in the service list with its icon and every listed form field is present.
- **SC-003**: Test connection succeeds for both an administrator and a least-privilege login against the IRIS Community test image; the class-dictionary step is pass for the former and a hint for the latter.
- **SC-004**: For each of a wrong host, port, Namespace and password, Test connection fails on the "connect" step with a message that names the problem, in 100% of cases.
- **SC-005**: A YAML workflow with the same fields creates the service and the Database named after the Namespace on the first run.
- **SC-006**: Installing the ingestion package without the `iris` extra leaves the IRIS driver uninstalled.
- **SC-007**: No credential appears in any log or Test connection output across the above runs.

## Assumptions

- The pinned OpenMetadata release is 2.1.1, recorded in `openmetadata.version`.
- Only the official InterSystems driver (`intersystems-irispython` 5.4.1) and dialect (`sqlalchemy-intersystems-iris` 1.0.2) are used.
- Connector code is kept as `overlay/` (new files) and `patches/` (edits, named by OpenMetadata path with `/` → `__` plus `.patch`); the working tree is `.om/`.
- End-to-end checks (UI form, Test connection in the UI) run on OpenMetadata images built from the overlay; connector unit and integration tests against IRIS do not need those images.
- The IRIS Community image is the test target; the full matrix of release tracks belongs to the CI spec.
- The "least-privilege login" is an ordinary SQL login with SELECT on the fixture schemas only.
- Developers have the tools needed to fetch the pinned release and run the build locally.
- Ingesting schemas, tables and columns (spec 002), type mapping (003), VECTOR detail (004), TLS (008), the docs page (008) and the CI workflow (001) are out of scope; this spec only has to create the service and the Database.
