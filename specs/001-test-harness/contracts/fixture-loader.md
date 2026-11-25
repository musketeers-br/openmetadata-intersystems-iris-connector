# Contract: fixture loader

Implements FR-001..FR-007. Catalog and checks: [data-model.md](../data-model.md).

## Command

```bash
python fixtures/iris/seed.py                 # dev repo, any venv with intersystems-irispython
python <tree>/ingestion/tests/integration/iris/data/seed.py   # same module, inside an OpenMetadata tree
```

`fixtures/iris/seed.py` runs the canonical module
`overlay/ingestion/tests/integration/iris/data/seed.py`. When `.om/` exists, it runs the copy in
`.om/` instead, so the copy being tested is the one that runs.

Python API (used by the integration conftest fallback):

```python
from .data.seed import load, self_check, CATALOG_VERSION  # from the iris integration package; import-safe (no side effects)
load(host, port, namespace="USER", admin_user="_SYSTEM", admin_password="SYS")  # runs cleanup → create → rows → grants → self_check
self_check(host, port, namespace="USER", admin_user=..., admin_password=..., expected=None)  # expected overridable for tests
```

## Configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `IRIS_HOST` | `127.0.0.1` | |
| `IRIS_PORT` | `1972` | CI default; local Makefile targets pass `11972` |
| `IRIS_NAMESPACE` | `USER` | |
| `IRIS_ADMIN_USER` / `IRIS_ADMIN_PASSWORD` | `_SYSTEM` / `SYS` | after the unexpire step |

There are no other inputs. The test-login credentials are part of the catalog.

## Behavior

1. Connect as admin. On failure, exit `2` with a message that names the host and port. When the
   error says the password must change, the message says "run the unexpire step (fixtures/iris/start-iris.sh)".
2. Cleanup (idempotent): drop the view, the tables, any table in `Scratch`, the `Scratch` schema and
   both users, ignoring "does not exist" errors (including `SQLCODE -473`).
3. Create the objects, insert the rows, create the users, grant. Commit.
4. Run the self-check (C1–C11).
5. Print one line per check (`PASS C3 constraints Billing.Patient`) and a final
   `FIXTURES OK v<CATALOG_VERSION> <ZVERSION>`. Never print passwords.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | loaded and every self-check passed |
| 1 | a self-check failed; stderr names the check id, the object and the expected vs actual value |
| 2 | cannot connect or not prepared (unexpire not run) |
| 3 | DDL, DML or grant failed; stderr shows the statement head and the IRIS error |

## Guarantees

- Running it twice gives the same end state (FR-001).
- Only the official driver (`import iris`) is used (FR-006).
- `CATALOG_VERSION` starts at `1`. Each additive change bumps it, and the fixtures contract lists
  what each version added (FR-007).
