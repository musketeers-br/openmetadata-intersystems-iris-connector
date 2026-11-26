# Contract: catalog queries (`queries.py`)

Rules for every constant added under `# --- 002: catalog ---`:

- Module-level string constants with bind parameters; no logic, no string formatting of names.
- Result rows always carry `TABLE_SCHEMA` and `TABLE_NAME` (and `COLUMN_NAME` where relevant); callers build maps keyed on those tuples.
- Joins between `INFORMATION_SCHEMA` views join on schema AND name (for foreign keys: constraint schema/name and referenced schema/table).
- No upper/lower-casing in SQL or Python.
- A constant exists only for a fact that research.md confirms the inspector gets wrong or incomplete, and has a Gap Report entry with reproduction.

Constants created: unique constraints (`IRIS_UNIQUE_CONSTRAINTS`, GAP-010). Everything else is read through reflection.
