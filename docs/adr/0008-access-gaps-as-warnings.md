# ADR-0008 — Access gaps surface as ingestion-status warnings

- **Status:** Accepted · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-8 · **Binds:** FR-14, FR-15, NFR-6 · **Constitution:** IV, V

## Context

A least-privilege login can usually *list* more objects than it can *read*: columns, rows, view definitions, descriptions. The default framework behavior on such an error ranges from failing the whole run to logging at debug level, which is effectively silent. The requirement is "reported, not skipped".

Objects the catalog does not show to the login at all cannot be detected from inside the connection.

## Decision

- **Catch at the smallest scope:** any privilege or read failure is caught at the smallest scope first (one object, then one feature of it: columns, keys, view definition, description, sample, profile).
- **Record and continue:** each failure is recorded as a **warning in OpenMetadata's ingestion status**, with the object FQN, the failed feature and the SQL error ([warnings contract](https://github.com/musketeers-br/is-omd/blob/main/docs/contracts/warnings.md)), and the run continues.
- **Never debug-only:** nothing about an access gap is reported only in debug logs.
- **Invisible objects:** objects invisible to the login are a documented limitation in the docs and the Gap Report. They are not guessed at. If SPIKE-03 finds a catalog view a non-admin can query to detect them, the decision is revisited.

## Consequences

- A single helper in `iris/metadata.py` wraps per-object reads and turns failures into status warnings with the fixed message format. Specs 002, 004, 005 and 006 use it; they do not write their own `try/except` logging.
- Spec 005 owns the helper's tests and the minimal-grants table in the docs. Spec 002 creates the helper early as a thin wrapper, so it does not wait for 005.

## Validation

Spec 005: revoking `SELECT` on one fixture table produces exactly one status warning naming its FQN, and the run completes. The full feature suite passes as `omd_reader`, apart from VECTOR detail, which follows ADR-0007.
