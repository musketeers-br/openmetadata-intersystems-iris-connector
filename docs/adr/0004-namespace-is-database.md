# ADR-0004 — Namespace = Database, SQL schema = Database Schema

- **Status:** Accepted · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-4 · **Binds:** FR-4, FR-5, FR-18 · **Constitution:** III

## Context

OpenMetadata's hierarchy is Service → Database → Database Schema → Table. IRIS has no "database" in the SQL sense:
- a connection targets one **Namespace**;
- inside it, SQL **schemas** (packages) hold tables and views.

If one unit names the Database `IRIS` or after the host while another (dbt, tests, docs) uses the Namespace, fully qualified names (FQNs) stop matching. That breaks dbt lineage (ADR-0011) and every test assertion.

## Decision

- One IRIS service connects to exactly one Namespace, through the required `namespace` connection field (default `USER`; `databaseName` and `databaseSchema` are not used).
- The OpenMetadata Database name is the Namespace name, verbatim. Each SQL schema is a Database Schema.
- **FQN:** `<service>.<Namespace>.<Schema>.<Table>`, with names in the case IRIS stores them ([ADR-0005](0005-identity-schema-name.md)).
- `IrisSource` overrides only the database-name hooks of `CommonDbSourceService` to return the Namespace.

## Consequences

- The fixture FQNs are fixed now. For the test service `iris_test` on Namespace `USER`: Database `iris_test.USER`; schemas `iris_test.USER.Clinic`, `.Billing`, `.AI`; tables such as `iris_test.USER.Clinic.Patient` and `iris_test.USER.Billing.Patient`.
- More than one Namespace means more than one service in v1. A multi-Namespace service is deferred and could later follow OpenMetadata's multi-database pattern.
- The dbt-iris fixture project must produce `database = <Namespace>` and `schema = <Schema>` in its artifacts.

## Validation

Spec 000 creates the service and checks the Database name on the test connection. Spec 002 tests the hierarchy and FQNs on every matrix cell. Spec 007 tests the dbt FQN match.
