# Contract: `report_access_gap`

Defined by the shared warnings contract (`../is-omd/docs/contracts/warnings.md`); this spec creates it, spec 005 hardens and tests it.

```python
@contextmanager
def report_access_gap(self, fqn: str, feature: str, schema: str, name: str):
    """Catch DB errors for one object feature and record IRIS-ACCESS in the status; never re-raise."""
```

- Lives in `iris/metadata.py` on `IrisSource`.
- On a database error inside the block: `self.status.warning(fqn, "IRIS-ACCESS: cannot read <feature> of <schema>.<name>: <first line of error>")`, then return normally; the caller keeps the part empty and continues.
- `feature` ∈ `columns`, `keys`, `view definition`, `description`.
- The message never contains credentials, URLs with credentials or row data; a debug log may add detail but never replaces the warning.
- Non-database errors are not swallowed.
- Every per-object read in this spec goes through it; no other try/except logging for access problems.

Unit tests (no IRIS): warning recorded with exact key and prefix; run continues; first line only; no re-raise; non-DB errors propagate.
