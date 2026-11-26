# ADR-0008 — Access gaps surface as ingestion-status warnings

- **Status:** Accepted · **Date:** 2026-11-24 · **Revised:** 2026-11-26 (spec 005) · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-8 · **Binds:** FR-14, FR-15, NFR-6 · **Constitution:** IV, V

## Context

A least-privilege login can usually *list* more objects than it can *read*: columns, rows, view definitions, descriptions. The default framework behavior on such an error ranges from failing the whole run to logging at debug level, which is effectively silent. The requirement is "reported, not skipped".

Objects the catalog does not show to the login at all cannot be detected from inside the connection.

SPIKE-03 and spec 005 measured both sides on the three IRIS tracks:

- **Invisible:** IRIS lists a table only to a login that holds some privilege on it. There is no privileges view (`INFORMATION_SCHEMA.TABLE_PRIVILEGES` and `COLUMN_PRIVILEGES` answer `SQLCODE -30`). Only `SELECT` on `%Dictionary.CompiledClass`, a further dictionary grant, would list the missing tables (GAP-003).
- **Visible but unreadable:** a login that holds only `REFERENCES`, `INSERT` or `UPDATE` on a table sees it in the catalog with all its columns. With a column-level `SELECT`, it sees only the granted columns. Every catalog read succeeds, so the run reported nothing; only a read of the rows fails (`SQLCODE -99`).
- **Silent listing:** the framework catches a failed table or view listing of a schema and only logs it, so the schema was cataloged empty with no status entry.

## Decision

- **Catch at the smallest scope:** any privilege or read failure is caught at the smallest scope first: one object, then one feature of it. The features are columns, keys, view definition, description, data, sample and profile; for a schema, its table and view listings.
- **Record and continue:** each failure is recorded as a **warning in OpenMetadata's ingestion status**, and the run continues. The warning carries the object FQN, the failed feature and the SQL error:
  - status warning key: the object FQN, or the schema FQN for a listing;
  - message: `IRIS-ACCESS: cannot read <feature> of <Schema>.<Object>: <first line of SQL error>`, or `… of <Schema>: …` for a listing;
  - `<feature>`: `tables`, `views`, `columns`, `keys`, `view definition`, `description`, `data`, `sample data` or `profile`;
  - one warning per object and feature per run.
- **Readability check (spec 005):** each cataloged table and view gets one no-row read, `SELECT TOP 0 * FROM "<Schema>"."<Table>"`. A refusal is the `data` warning. It is the only way to report a visible but unreadable object, and a column-level grant that hides columns.
- **Never debug-only:** nothing about an access gap is reported only in debug logs. A unit test parses the connector package and fails on any error handler that neither re-raises nor records a status warning, unless it is allow-listed with a reason.
- **Invisible objects:** objects invisible to the login are a documented limitation in the docs and the Gap Report. They are not guessed at.
  - SPIKE-03 found no catalog view that a login without privileges can query.
  - On 2026-11-26 both deciders kept the limitation.
  - Detection through `%Dictionary.CompiledClass` remains a possible later, optional extra.

## Consequences

- A single helper in `iris/metadata.py` wraps per-object reads and turns failures into status warnings with the fixed message format. Specs 002, 004, 005 and 006 use it; they do not write their own `try/except` logging.
- Spec 005 owns the helper's tests and the minimal-grants table in the docs. Spec 002 created the helper early as a thin wrapper, so it did not wait for 005.
- One extra prepare per table and view: 3–5 ms per object on the fixtures (spec 005 research).
- An administrator who wants to know what a login misses compares `INFORMATION_SCHEMA.TABLES`, run as an administrator, with the catalog.

## Validation

Spec 005, on every IRIS track:

- **Fixtures:** in schema `Restricted`, which the readers hold no schema grant on, the readers get `GRANT REFERENCES` on `Restricted.Secret` and `GRANT SELECT (Id)` on `Restricted.ColumnGrant`; `Restricted.Hidden` gets no grant. The fixtures use this setup instead of a table-level revoke, because a table-level `REVOKE` does not override a schema-level `GRANT`.
- **Readers:** each restricted table the readers can see produces exactly one `data` status warning naming its FQN, and the run completes. `Secret` is cataloged with its 3 columns, `ColumnGrant` with `Id` only, and `Hidden` is not listed.
- **Administrator:** no warning.
- **Ordinary login:** the full feature suite passes as `omd_reader`, apart from VECTOR detail, which follows ADR-0007.
