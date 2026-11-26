# Research: Metadata Core Ingestion

Status: **confirmed on `latest-em`** (IRIS Community 2026.1, dialect 1.0.2, driver 5.4.1) as `admin` (`_SYSTEM`),
`omd_reader` and `omd_reader_dict`, on the shared fixture objects. no earlier spike result covered this, so
the comparison was run directly (T002). **`latest-cd` and `latest-preview` are not checked yet**; the matrix (spec 001)
runs the same tests there and any difference goes to the Gap Report.

## Decisions already fixed (no research needed)

| Topic | Decision | Rationale | Alternatives |
|---|---|---|---|
| Default source | Inspector of the official dialect | Principle I; fewest overrides | Direct SQL everywhere (rejected: reimplements the framework) |
| Workaround form | Named constant in `queries.py` keyed on `(TABLE_SCHEMA, TABLE_NAME[, COLUMN_NAME])` plus Gap Report entry | ADR-0005, ADR-0013 | Post-processing the inspector output (forbidden by ADR-0005) |
| Access gaps | `report_access_gap` context manager, one `IRIS-ACCESS` warning per object and feature, never re-raise | ADR-0008, warnings contract | try/except with debug logging (silent, forbidden) |
| System content | Filter-pattern defaults in `irisConnection.json`: `^%`, `^INFORMATION_SCHEMA$`, `^Ens`; `^Ens` stays because `USER` is interoperability-enabled (SPIKE-01) | ADR-0009 | Python skips (forbidden) |
| Generated/deprecated classes | Excluded only if a name pattern can express it; otherwise documented plus Gap entry | ADR-0009 | Skipping in code |
| Lineage | `LineageSource` subclass (as `sqlite/`), OpenMetadata default ANSI view parsing; unparsable views listed in Gap Report | Principle I | Custom SQL parser |
| Mark deleted, description override | Framework options; this spec only tests them | Principle I | Reimplementation |
| Stored procedures | Not ingested | Out of scope | — |
| Types | Whatever the type map returns; `types.py` not edited | Spec 003 owns it | — |

## Fact-by-fact source (to confirm in task 1)

Compare, on the fixture objects and all three tracks (`latest-em`, `latest-cd`, `latest-preview`), the
inspector methods against `INFORMATION_SCHEMA` views. "Provisional" reflects ADR-0005's own hint (keys,
view definitions, descriptions are the suspects), not evidence.

| Fact | Inspector call | `INFORMATION_SCHEMA` source | Provisional | Confirmed (T002, `latest-em`) |
|---|---|---|---|---|
| Schema names | `get_schema_names` | `SCHEMATA` / `TABLES` | inspector | **inspector**: same on all logins (also lists 221 schemas incl. system ones; filters apply) |
| Table names | `get_table_names` | `TABLES` (`TABLE_TYPE`) | inspector | **inspector**: `Clinic`: Encounter, Patient; `Billing`: Patient; `AI`: Embedding |
| View names | `get_view_names` | `TABLES` (`TABLE_TYPE='VIEW'`) | inspector | **inspector**: `Clinic.ActivePatient` only |
| Columns (name, position, nullability, default, length, precision, scale) | `get_columns` | `COLUMNS` | inspector (note GAP-005 needs `_dictionary_access` preset) | **inspector**: identical to `COLUMNS` for all three logins (NOT NULL, VARCHAR(120), NUMERIC(5,2)); no fixture has a default value, so defaults are unverified |
| Primary key | `get_pk_constraint` | `TABLE_CONSTRAINTS` + `KEY_COLUMN_USAGE` | catalog if inspector wrong | **inspector**: correct for all logins. Note PK constraint names repeat across schemas (`PATIENT_PKEY1` in `Clinic` and `Billing`), so constraint names are never an identity |
| Foreign keys (referenced schema and table) | `get_foreign_keys` | `REFERENTIAL_CONSTRAINTS` + `KEY_COLUMN_USAGE`, join on schema AND name | catalog if inspector wrong | **inspector**: `Clinic.Encounter` → `referred_schema=Clinic`, `referred_table=Patient` for all logins |
| Unique constraints | `get_unique_constraints` | `TABLE_CONSTRAINTS` + `KEY_COLUMN_USAGE` | catalog if inspector wrong | **catalog** (`IRIS_UNIQUE_CONSTRAINTS`, GAP-011): inspector is correct for `admin` and `omd_reader` but fails with SQLCODE -99 for `omd_reader_dict` (needs `%Dictionary.IndexDefinition`) |
| View definition | `get_view_definition` | `VIEWS.VIEW_DEFINITION` | catalog if inspector wrong | **inspector**: identical text to `VIEWS`, readable by all three logins; stored form has a column-list prefix and an `/*#OPTIONS*/` suffix (GAP-012); the lineage parser reads it correctly, so no post-processing |
| Table description | `get_table_comment` | `TABLES.DESCRIPTION` | catalog if inspector wrong | **inspector**: "Patients registered in the clinic" for all logins |
| Column description | (not returned) | `COLUMNS.DESCRIPTION` | catalog | **catalog** (`IRIS_COLUMN_DESCRIPTIONS`, GAP-010): inspector returns no comment; `COLUMNS` has "Patient identifier" for `PatientId` for all logins |

For each row the task records: result on each track and each login (`admin`, `reader`), SQLCODE on
failure, and the chosen source with the reason. A catalog choice creates a Gap entry with reproduction.

## Data types seen

`INFORMATION_SCHEMA.COLUMNS.DATA_TYPE` for the fixture objects (admin and reader agree), for spec 003:
`BIT`, `DATE`, `DOUBLE`, `INTEGER`, `LONGVARCHAR`, `NUMERIC`, `TIMESTAMP`, `VARCHAR` (the SQL catalog reports `AI.Embedding.Vec` as `varchar`, length 1037; VECTOR detail is spec 004). The dialect reports `Notes` as `LONGVARCHAR` with length 2147483647. `Types.AllTypes` does not exist yet (spec 003).

## Other findings

- The framework swallows access errors in three places (table description, view definition, key reads), logging at debug or warning level only; the connector overrides them so each failure becomes an `IRIS-ACCESS` status warning (once per object and feature).
- A table the login cannot see is not listed at all (no `Scratch.Locked` for `omd_reader`); a table that is listed but unreadable cannot be built with the current fixtures. The `Restricted.Secret` fixture belongs to spec 005.
- Generated/deprecated classes: no marker in `INFORMATION_SCHEMA.TABLES.DESCRIPTION` for the fixture objects, so no name pattern was added (ADR-0009 outcome).

- Workflow run on the overlay server (admin, `latest-em`): hierarchy, columns, keys, descriptions, view definition, lineage (exactly `Clinic.Patient` and `Clinic.Encounter`), include filter, mark-deleted (on and off) and description override pass. The local stack needs its Elasticsearch container running (lineage and the server's search depend on it).
- **GAP-013 (resolved):** the framework ignores the connection-level default filters, so the source applies them when the pipeline has no `schemaFilterPattern` (decided; ADR-0009).
- A lineage workflow with default settings reports one error because query-log lineage (`processQueryLineage`, spec 010) needs `sql_stmt`; view lineage works with `processQueryLineage: false`.
- IRIS stops listing a schema when its last table is dropped, so mark-deleted only visits the schema if another table remains; tables of a vanished schema depend on `markDeletedSchemas`.

## Open items

- `latest-cd` and `latest-preview` comparison (spec 001 matrix).
- Column default values are unverified: no fixture column has a default.
- `Scratch` schema: first use is by the mark-deleted test; the shared fixtures (spec 001) create `Scratch` with a sentinel table `Scratch.Keep` that is never dropped, because IRIS stops listing a schema once its last table is dropped.
- `iris_cell` / `iris_service_connection` / `iris_admin_engine` do not exist yet (spec 001): the tests use an ad-hoc environment like spec 000's.
