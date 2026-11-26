# Contract: `IRIS-ACCESS` warning

Extends the warnings contract's `IRIS-ACCESS` row (ADR-0008) with the features this spec adds.

## Key and text

| Object | Key (first argument of `status.warning`) | Reason (second argument) |
|---|---|---|
| table or view | `<service>.<Namespace>.<Schema>.<Table>` | `IRIS-ACCESS: cannot read <feature> of <Schema>.<Table>: <first line of SQL error>` |
| schema | `<service>.<Namespace>.<Schema>` | `IRIS-ACCESS: cannot read <feature> of <Schema>: <first line of SQL error>` |

`<feature>` ∈ `tables`, `views` (schema); `columns`, `keys`, `description`, `view definition`,
`data` (table or view); `sample data`, `profile` (spec 006).

## Rules

- **Once:** one warning per `(key, feature)` per run, however many reads of that feature fail.
- **The run goes on:** the object is cataloged with what was read. A failed listing yields no
  objects for that schema, and the other schemas go on.
- **No secrets:** the text holds no password, no connection URL and no row data, only the first line
  of the error. IRIS errors carry the SQLCODE and its message (`[SQLCODE: <-99>:<Privilege violation>]`).
- **Tests:** they assert on the prefix `IRIS-ACCESS: cannot read <feature> of <Schema>.<Table>: ` and
  the key, never on the SQL error text, which differs between IRIS versions.
- **Logs:** a debug log line may add detail; it never replaces the warning.
- **One mechanism:** every read goes through `report_access_gap(fqn, feature, schema, name)`; no other
  code catches database errors in `iris/` without warning or re-raising, which the guard test
  enforces.

## `data` feature

- **Query:** `SELECT TOP 0 * FROM "<Schema>"."<Table>"`, with identifiers quoted by the dialect. Once
  per cataloged table and view per run, after its columns are read.
- **Meaning:** the login cannot read the object's rows. With a column-level grant, the columns it
  cannot read are also missing from the catalog. The message is the same; the grants docs explain
  both.
