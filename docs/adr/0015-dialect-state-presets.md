# ADR-0015 — Preset the official dialect's state so least-privilege logins can connect

- **Status:** Accepted · **Date:** 2026-11-24 · **Deciders:** Henry Pereira, Henrique Dias
- **Spine:** AD-15 (new) · **Binds:** FR-1, FR-2, FR-14, NFR-3 · **Constitution:** II, IV, V
- **Refines:** [ADR-0013](0013-gap-report.md) (narrow, documented exception) · **Evidence:** is-omd `spikes/findings/SPIKE-01.md`

## Context

SPIKE-01 used IRIS 2026.1, `sqlalchemy-intersystems-iris` 1.0.2 and `intersystems-irispython` 5.4.1. It showed that the official dialect does not work with a least-privilege SQL login:

- **A. Connect fails.** `IRISDialect.on_connect` reads the server version with the Native API: `iris.createIRIS(conn).classMethodString("%SYSTEM.Version", "GetNumber")`. A login without the `%Native_ClassExecution` resource fails with `<PROTECT> *Resource %Native_ClassExecution required`. The plain driver connects fine, and `SELECT $ZVERSION` works for that login.
- **B. Every table fails to reflect.** `_check_dictionary_access` treats `cursor.execute("%CHECKPRIV SELECT ON %Dictionary.PropertyDefinition") == 0` as "has access", but the driver returns `0` for every login. The dialect then always joins `%Dictionary.PropertyDefinition`, so `get_columns`, `get_indexes` and `get_unique_constraints` fail with `SQLCODE -99` for any login without that grant.

Both points break constitution IV, *least privilege by default*. The alternatives are:
- require `%Native_ClassExecution` plus a dictionary grant on every login. That is an execute privilege, not read-only, so it is unacceptable for a catalog login.
- wait for a dialect release. That is outside our control before Dec 18.

## Decision

`iris/connection.py` sets two attributes of the dialect instance **once, when the engine is created, before its first pooled connection**. Both values come from one short-lived driver connection that uses the same credentials:

| Preset | Value | Source query | Effect |
|---|---|---|---|
| `engine.dialect.server_version_info` | `(year, minor, patch)` | `SELECT $ZVERSION` (parsed) | `on_connect` skips the Native API call |
| `engine.dialect._dictionary_access` | `True` / `False` | `SELECT TOP 1 Name FROM %Dictionary.PropertyDefinition` succeeds or raises | The dialect joins the dictionary only when the login can read it |

Rules for this exception:

- **Only state the dialect already has:** both attributes are initialised by the dialect itself. No monkey-patching of methods, no SQL rewriting, no subclassing of the dialect.
- **One place:** all of it lives in `iris/connection.py` in one function. It has a unit test with a fake DB-API connection, and the integration tests run it on every matrix cell.
- **Reported:** GAP-004 (A) and GAP-005 (B) in the Gap Report, each with its reproduction and an issue raised with the dialect maintainers. The PR description mentions the issue links.
- **Removable:** when a dialect release fixes A or B, the matching preset is deleted, the minimum dialect version is raised, and the GAP entry is closed. A version check in the unit tests flags when the pinned dialect version changes, so the presets get re-evaluated.
- **No other workarounds:** the dialect's other defects (GAP-006 stray `print`, GAP-007 repeated composite-PK columns) are reported, not patched. Wrong types are handled by the connector's own type map ([ADR-0006](0006-single-type-map.md)) from the raw `DATA_TYPE`, which is ordinary connector logic.

## Consequences

- A plain SQL login with `SELECT` on the target schemas ingests every feature, which keeps constitution IV.
- Opening the extra connection at engine creation costs one round-trip per engine.
- Maintainers see an explicit, tested, documented exception instead of a hidden one ([ADR-0013](0013-gap-report.md) stays the rule).
- If maintainers object upstream, the fallback is to document `%Native_ClassExecution` plus the dictionary grant as requirements until the dialect is fixed. That would be recorded as a constitution deviation in the spec's Complexity Tracking.

## Validation

- **Spec 000:** test connection passes as `reader` and `reader_dict` on all tracks. A unit test covers `$ZVERSION` parsing for the three tracks' version strings and the access probe (both outcomes).
- **Spec 002:** columns, keys and descriptions are ingested as `reader`.
