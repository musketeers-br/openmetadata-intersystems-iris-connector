# Quickstart: VECTOR enrichment

## VECTOR columns (docs note for spec 008)

IRIS's SQL catalog reports `VECTOR` columns as `VARCHAR`. Their element type and dimension are in
the class dictionary. To catalog them as vectors, give the ingestion login one optional, read-only
grant:

```sql
GRANT SELECT ON %Dictionary.PropertyDefinition TO omd_ingest
```

| | With the grant | Without it |
|---|---|---|
| `Embedding VECTOR(DOUBLE, 384)` | data type `ARRAY`, array data type `DOUBLE`, shown as `VECTOR(DOUBLE, 384)` | `VARCHAR` with the length IRIS reports |
| Ingestion status | — | one `IRIS-VECTOR-GRANT` hint per run, naming the grant |
| Everything else | unchanged | unchanged |

The same grant also gives the official dialect its full reflection and passes the optional "class
dictionary" step of Test Connection.

Limits:

- **Inherited properties:** a VECTOR property a class inherits instead of defining is not in
  `PropertyDefinition`, so that column stays `VARCHAR`. Tables created with SQL DDL are not
  affected.
- **Views:** a view's VECTOR columns stay `VARCHAR`, because a view's columns have no dictionary
  property.
- **Name disclosure:** the grant shows class and property names of the whole Namespace, not data.

## Developer check

Prerequisite: fixtures at catalog v4 (`FIXTURES OK v4`).

1. **Unit tests**, no IRIS:

   ```bash
   cd .om/ingestion
   ../env/bin/python -m pytest tests/unit/topology/database/test_iris_vector.py -q
   ```

2. **Integration**: `make test-cell TAG=latest-em LOGIN=reader_dict`, then `reader`, then `admin`.
   `test_vector.py` expects:
   - `reader_dict` and `admin`:
     - `AI.Embedding.Vec` is `ARRAY` / `DOUBLE` / `VECTOR(DOUBLE, 3)`;
     - `Vec4` is `ARRAY` / `INT` / `VECTOR(INT, 4)`;
     - `vec_low` is `ARRAY` / `FLOAT` / `VECTOR(FLOAT, 2)`;
     - no hint.
   - `reader`:
     - `Vec` is `VARCHAR(1037)`, `Vec4` is `VARCHAR(83)`, `vec_low` is `VARCHAR(691)`;
     - exactly one `IRIS-VECTOR-GRANT` naming `omd_reader`.

3. **UI** (needs `make om-image` and a running server): ingest the fixtures as `omd_reader_dict` and
   open `AI.Embedding`. The schema tab shows the three columns as `vector(…)`, in lowercase, because
   the server lowercases every `dataTypeDisplay`. Record a screenshot in ADR-0007 (done 2026-11-28).
