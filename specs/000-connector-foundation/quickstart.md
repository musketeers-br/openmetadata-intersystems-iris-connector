# Quickstart: validating the connector foundation

Prerequisites: git, GNU make, Python 3.11, `uv`, Docker, and an IRIS Community container
(`containers.intersystems.com/intersystems/iris-community:latest-em`) seeded with the shared fixtures
(in Namespace `USER`: tables `Clinic.Patient`, `Clinic.Encounter`, `Billing.Patient`, `AI.Embedding` (`VECTOR(DOUBLE, 3)`) and view `Clinic.ActivePatient`; logins `admin` = `_SYSTEM`/`SYS`, `reader` = `omd_reader`/`Reader123` (`SELECT` on schemas `Clinic`, `Billing`, `AI`), `reader_dict` = `omd_reader_dict`/`Reader123` (same, plus `SELECT` on `%Dictionary.PropertyDefinition` and `%Dictionary.CompiledProperty`); throwaway test credentials. On a fresh container, unexpire passwords first: `docker exec <c> iris session IRIS -U %SYS '##class(Security.Users).UnExpireUserPasswords("*")'`).

## 1. Round trip (User Story 1)

```bash
make om-import
make om-check
git status --short overlay patches    # expect no output
```

Expected: the IRIS connector imports from `.om/ingestion`; no file changes.

## 2. Unit tests (no IRIS, no image)

```bash
cd .om/ingestion && python -m pytest tests/unit/topology/database/test_iris.py
```

Expected: pass (config parsing, Namespace in URL, masked password, missing extra, dialect presets).

## 3. Test connection against IRIS (User Story 3)

```bash
IRIS_HOST=127.0.0.1 IRIS_PORT=1972 IRIS_LOGIN=admin  python -m pytest .om/ingestion/tests/integration/iris/test_connection.py -m iris
IRIS_HOST=127.0.0.1 IRIS_PORT=1972 IRIS_LOGIN=reader python -m pytest .om/ingestion/tests/integration/iris/test_connection.py -m iris
```

Expected: `admin` passes all five steps; `reader` passes the first four and `GetClassDictionary` is
reported with the grant hint, overall success; wrong host, port, Namespace or password fails on
`CheckAccess`.

## 4. UI and workflow on overlay-built images (User Stories 2 and 4)

```bash
make om-image
```

Start the images, then:
- in the UI, add a database service: "InterSystems IRIS" appears with its icon and the form fields; run Test connection as `admin` and `reader`;
- run a YAML workflow (`type: iris`, `127.0.0.1` not `localhost`, because OpenMetadata rewrites `localhost` to `host.docker.internal` in service connections): the service and a Database named after the Namespace exist; logs contain no credentials.

## 5. Optional extra (User Story 5)

```bash
python -m venv /tmp/iris-noextra && /tmp/iris-noextra/bin/pip install ./.om/ingestion
/tmp/iris-noextra/bin/pip list | grep -i intersystems    # expect no output
```
