# Quickstart: Least privilege and access-gap reporting

Two parts: the minimal grants table, which is written for IRIS administrators and which spec 008
moves into the docs page; and how a developer checks the feature.

## Minimal grants

Create one login for OpenMetadata, then grant what the features you use need. The examples use
login `omd_ingest` and schema `Sales`; repeat a grant for each schema to catalog.

```sql
CREATE USER omd_ingest IDENTIFIED BY "<password>"
```

| Feature | Grant | Without it | Confirmed by |
|---|---|---|---|
| Metadata: schemas, tables, views, columns, types, keys, descriptions | `GRANT SELECT ON SCHEMA Sales TO omd_ingest` | the schema's objects are not listed (invisible, see below) | spec 005, all tracks |
| View definitions and view lineage | the same `SELECT` | — | spec 002, all tracks |
| Profiler | the same `SELECT` (expected) | the table is cataloged with an `IRIS-ACCESS` warning and is not profiled | spec 006 |
| Data-quality tests | the same `SELECT` (expected) | the test cannot run on that table | spec 006 |
| dbt lineage | none in IRIS (expected; dbt artifacts are read outside IRIS) | — | spec 007 |
| VECTOR element type and dimension (optional) | `GRANT SELECT ON %Dictionary.PropertyDefinition TO omd_ingest` | VECTOR columns are cataloged as `VARCHAR`, with one `IRIS-VECTOR-GRANT` hint per run | spec 004, all tracks; see its [VECTOR columns note](../004-vector-enrichment/quickstart.md#vector-columns-docs-note-for-spec-008) |

The `SELECT` can also be granted table by table (`GRANT SELECT ON Sales.Orders TO omd_ingest`); then
only those tables are cataloged.

Nothing else is needed: no role, no `%Native_ClassExecution`, no write privilege. A login created
with `CREATE USER` needs no password-unexpire step.

### What administrators should know

- **Invisible objects are not reported.** IRIS lists a table only to a login that holds some
  privilege on it. A table the login has no privilege on does not appear in the catalog, and the
  connector cannot warn about it (GAP-003). To check, run this as an administrator and compare the
  list with the catalog:
  `SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'Sales'`.
- **Visible but unreadable objects are reported.** A table the login holds another privilege on
  (`INSERT`, `UPDATE`, `REFERENCES`) is cataloged with its columns, plus one warning:
  `IRIS-ACCESS: cannot read data of Sales.Orders: …`.
- **A column-level `SELECT` hides the other columns.** The table is cataloged with the granted
  columns only, plus the same warning. Grant `SELECT` on the whole table to catalog every column.
- **A table-level `REVOKE` does not override a schema-level `GRANT`.** After
  `GRANT SELECT ON SCHEMA Sales` then `REVOKE SELECT ON Sales.Payroll`, the login still reads
  `Sales.Payroll`. To keep a table out, grant table by table, or move it to a schema the login has no
  grant on.
- **Dictionary grants reveal names.** `%Dictionary.*` grants show the class and property names of the
  whole Namespace (not data), including classes the login cannot read.

## Developer check

Prerequisite: spec 001's local cell (`make iris-up`, `make iris-seed`), fixtures at catalog v3
(`FIXTURES OK v3`).

1. **Unit tests**, no IRIS:

   ```bash
   cd .om/ingestion
   ../env/bin/python -m pytest tests/unit/topology/database/test_iris_access.py \
     tests/unit/topology/database/test_iris_access_guard.py -q
   ```

2. **Integration**, one cell per login:

   ```bash
   make test-cell TAG=latest-em LOGIN=reader     # then reader_dict, admin
   ```

   `test_access.py` expects:
   - for each reader, one `IRIS-ACCESS … data …` warning for `Restricted.Secret` and one for
     `Restricted.ColumnGrant`, `Restricted.Hidden` not listed, and no warning for the readable
     fixtures;
   - for `admin`, no warning.

3. **Guard**: add `try: … except SQLAlchemyError: logger.debug(...)` around any read in
   `metadata.py`, rerun step 1, and see `test_iris_access_guard.py` fail with the file and line. Undo.

4. **Grants table**: the fixtures create `omd_reader` with exactly the "Metadata" SQL above
   (`CREATE USER`, then `GRANT SELECT ON SCHEMA` for `Clinic`, `Billing`, `AI`, `Types`). Its cells
   passing, with no access warning outside `Restricted`, is the check of that row.
