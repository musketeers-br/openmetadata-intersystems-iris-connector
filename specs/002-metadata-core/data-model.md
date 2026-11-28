# Data Model: Metadata Core Ingestion

No stored data. These are the identities and shapes the connector reads and emits.

## Identity (ADR-0005)

| Object | Key |
|---|---|
| Schema | `TABLE_SCHEMA` |
| Table / view | `(TABLE_SCHEMA, TABLE_NAME)` |
| Column | `(TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME)` |
| Key / constraint | `(TABLE_SCHEMA, TABLE_NAME, CONSTRAINT_NAME)` |
| Foreign-key target | `(REFERENCED_SCHEMA, REFERENCED_TABLE)` taken from the constraint, never looked up by name alone |

Case is never changed. Any in-memory map keyed on a name alone is a defect.

## OpenMetadata entities produced

| Entity | FQN pattern | Source of fields |
|---|---|---|
| Database | `<service>.<Namespace>` | spec 000 |
| Database Schema | `<service>.<Namespace>.<Schema>` | schema list after filters |
| Table (`tableType` Regular) | `….<Schema>.<Table>` | tables; description; columns; constraints |
| Table (`tableType` View) | `….<Schema>.<View>` | views; `schemaDefinition` when readable |
| Column | `….<Table>.<Column>` | name, ordinal position, nullable, default, length, precision, scale, description, type from the type map |
| Constraint | on the table | PRIMARY_KEY, UNIQUE, FOREIGN_KEY (with `referredColumns` as full column FQNs) |
| Lineage edge | table/view → view | parsed view definition; only to existing assets |

## Status warning

`key` = object FQN; message `IRIS-ACCESS: cannot read <feature> of <Schema>.<Object>: <first line of SQL error>`;
`<feature>` ∈ columns, keys, view definition, description. One per object and feature per run.

## State transitions

- Table dropped between runs + mark deleted on → entity soft-deleted; re-created → active again.
- Description: IRIS value written only if none exists in OpenMetadata or the override option is on.
