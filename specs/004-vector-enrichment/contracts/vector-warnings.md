# Contract: VECTOR warnings

Replaces the warnings contract's `IRIS-VECTOR-GRANT` text, which named `%Dictionary.CompiledProperty`
before SPIKE-03, and keeps `IRIS-VECTOR-PARAMS`.

| Code | Key | Reason | Emitted |
|---|---|---|---|
| `IRIS-VECTOR-GRANT` | `<service>.<Namespace>` | `IRIS-VECTOR-GRANT: if this Namespace has VECTOR columns, GRANT SELECT ON %Dictionary.PropertyDefinition TO <username> to catalog their element type and dimension` | once per run, on the first `varchar` column read, only when the dictionary check failed (no access, or the query failed) |
| `IRIS-VECTOR-PARAMS` | `<service>.<Namespace>.<Schema>.<Table>.<Column>` | `IRIS-VECTOR-PARAMS: could not parse VECTOR parameters '<raw>'; cataloged as VARCHAR` (unusable `DATATYPE` or `LEN`), or `IRIS-VECTOR-PARAMS: VECTOR element type '<type>' is not mapped; cataloged as ARRAY of UNKNOWN` | once per column per run |

## Rules

- **Username:** `<username>` is the connection's login (`IrisConnection.username`). No password, no
  URL.
- **Failed query:** when the dictionary query fails for a reason other than a missing privilege, the
  hint still names the grant, and the first line of the error is appended after ` — `. It is never an
  `IRIS-ACCESS` warning per table.
- **Parameters in the message:** the raw parameters are dictionary metadata, not row data, so they
  may appear in the message.
- **Conditional text:** a login without the grant cannot tell whether the Namespace has VECTOR
  columns, so the hint says "if" (review decision, 2026-11-26).
- **Tests:** they assert on the code prefix and the key.
