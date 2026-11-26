# Contract: unknown-type warning

Implements FR-008 (ADR-0006, constitution III and V).

| Item | Value |
|---|---|
| API | `self.status.warning(key, reason)` on the source's ingestion status |
| Key | the Database FQN: `<service>.<Namespace>`, e.g. `iris_test.USER` |
| Reason | `IRIS-UNKNOWN-TYPE: IRIS type '<type>' is not mapped; cataloged as UNKNOWN (first seen on <Schema>.<Table>.<Column>)` |
| `<type>` | the raw `DATA_TYPE` as the catalog reports it (case kept) |
| `<Schema>.<Table>.<Column>` | the first column the type was seen on in this run, names in stored case |
| Frequency | once per distinct type (case-insensitive) per run; a new run reports again |
| Column | cataloged with `dataType = UNKNOWN`, `dataTypeDisplay` = upper-case raw type |
| Run | never fails because of a type |

Tests assert on the `IRIS-UNKNOWN-TYPE` prefix, the key and the type, never on anything else in the
text.
