# Data Model: Connector Foundation

No stored data. These are the configuration and result shapes the feature defines.

## IRIS service connection (`IrisConnection`)

Field list (decided in SPIKE-01):

| Field | Required | Rule |
|---|---|---|
| `type` | — | enum `Iris` |
| `scheme` | — | enum `iris` |
| `username` | yes | |
| `authType` | no | basicAuth; holds `password`, masked |
| `hostPort` | yes | `host:port`, default port 1972 |
| `namespace` | yes | default `USER`; case preserved; becomes the Database name |
| `sslConfig` | no | present; wired to the driver in spec 008 |
| `connectionOptions`, `connectionArguments` | no | standard |
| `schemaFilterPattern` | no | default excludes `^%`, `^INFORMATION_SCHEMA$`, `^Ens` |
| `tableFilterPattern`, `databaseFilterPattern` | no | standard |
| `supports*` flags | no | standard |

Validation: `additionalProperties: false`; no `databaseName` or `databaseSchema`. The URL is
`iris://<username>:<password>@<hostPort>/<namespace>[?options]`; the password never appears in logs.

## Database (OpenMetadata)

Exactly one per service; name = `namespace` verbatim.

## Test connection step

| Field | Notes |
|---|---|
| `name` | `CheckAccess`, `GetSchemas`, `GetTables`, `GetViews`, `GetClassDictionary` |
| `mandatory` | true for the first three; false for `GetViews` and `GetClassDictionary` |
| `shortCircuit` | `CheckAccess` only |
| result | passed / not passed; failure carries the step's `errorMessage` (likely fix or grant hint) |

Expected results per login (SPIKE-01, IRIS 2026.1):

| Login | CheckAccess | GetSchemas | GetTables | GetViews | GetClassDictionary |
|---|---|---|---|---|---|
| `admin` (`_SYSTEM`) | pass | pass | pass | pass | pass |
| `reader` (`omd_reader`) | pass (with the ADR-0015 presets) | pass | pass | pass | not passed (optional hint) |
| `reader_dict` (`omd_reader_dict`) | pass (with the presets) | pass | pass | pass | pass |
| wrong password / host / Namespace | fail | — | — | — | — |

Step messages (`iris.json`):
- `CheckAccess`: "Failed to connect to IRIS. Check host, superserver port, Namespace, username and password." The driver reports a bad password as `<COMMUNICATION LINK ERROR> … Invalid Message received`.
- `GetSchemas`: "Failed to fetch schemas. Grant SELECT on at least one schema to the user."
- `GetTables`: "Failed to fetch tables. Grant SELECT on the tables to ingest."
- `GetViews`: "Failed to fetch views."
- `GetClassDictionary` (probe `SELECT TOP 1 Name FROM %Dictionary.PropertyDefinition`): "Optional: GRANT SELECT ON %Dictionary.PropertyDefinition TO <user> for full reflection and VECTOR detail. Ingestion works without it."

## Overlay state (repository)

| Element | Rule |
|---|---|
| `overlay/<path>` | new OpenMetadata file, same relative path |
| `patches/<path with / as __>.patch` | one git diff per edited existing file |
| `openmetadata.version` | the pinned tag, `2.1.1` |
| `.om/` | git-ignored, disposable; never committed |

State transitions: `no .om` or stale → (om-import) → `.om current` → developer edits → (om-export) → repository updated → (om-import) → no change.
