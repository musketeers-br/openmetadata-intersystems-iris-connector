#  Copyright 2025 OpenMetadata
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/LICENSE
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""
Shared IRIS fixtures for the connector's tests: the fixture catalog, its loader and its self-check.

The loader drops and recreates every fixture object, row, login and grant in one Namespace, then
verifies the result (checks C1-C11). Running it twice gives the same state. It uses only the official
driver (`import iris`), imported inside functions, so importing this module has no side effects and
needs no driver (the integration conftest reads `LOGINS` from it).

Script use: `python seed.py`, configured by IRIS_HOST (127.0.0.1), IRIS_PORT (1972), IRIS_NAMESPACE
(USER), IRIS_ADMIN_USER (_SYSTEM), IRIS_ADMIN_PASSWORD (SYS) and IRIS_WAIT_SECONDS (60).
Exit codes: 0 loaded and verified; 1 a check failed; 2 cannot connect or not prepared; 3 a statement
failed. Passwords are never printed.

The catalog is additive only: a change bumps CATALOG_VERSION and adds a VERSION_HISTORY entry.
"""

import copy
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

CATALOG_VERSION = 2
VERSION_HISTORY = {
    1: "spec 001: Clinic, Billing, AI, Scratch (sentinel Scratch.Keep); omd_reader, omd_reader_dict",
    2: "spec 003: Types.AllTypes, one column per DATA_TYPE the IRIS SQL catalog reports",
}


@dataclass(frozen=True)
class Login:
    user: str
    password: str
    is_admin: bool
    has_dict_grant: bool


# Test-only credentials for throwaway containers. The admin password can be overridden at run time.
LOGINS: dict[str, Login] = {
    "admin": Login("_SYSTEM", "SYS", is_admin=True, has_dict_grant=True),
    "reader": Login("omd_reader", "Reader123", is_admin=False, has_dict_grant=False),
    "reader_dict": Login("omd_reader_dict", "Reader123", is_admin=False, has_dict_grant=True),
}

DDL: list[str] = [
    "CREATE TABLE Clinic.Patient ("
    "%DESCRIPTION 'Patients registered in the clinic', "
    "PatientId INT PRIMARY KEY %DESCRIPTION 'Patient identifier', "
    "FullName VARCHAR(120) NOT NULL, BirthDate DATE, Weight NUMERIC(5,2))",
    "CREATE TABLE Clinic.Encounter ("
    "EncounterId INT PRIMARY KEY, "
    "PatientId INT NOT NULL REFERENCES Clinic.Patient(PatientId), "
    "StartedAt TIMESTAMP, Notes LONGVARCHAR, Active BIT)",
    "CREATE TABLE Billing.Patient ("
    "Code VARCHAR(20) PRIMARY KEY, Balance DOUBLE, CONSTRAINT UqBillingCode UNIQUE (Code))",
    "CREATE TABLE AI.Embedding (Id INT PRIMARY KEY, Content VARCHAR(500), Vec VECTOR(DOUBLE, 3))",
    # Spec 003: one column per DATA_TYPE the catalog reports (Id covers integer), plus VARCHAR(1) (GAP-008).
    "CREATE TABLE Types.AllTypes ("
    "Id INT PRIMARY KEY, BigIntCol BIGINT, BitCol BIT, DateCol DATE, DoubleCol DOUBLE, "
    "GuidCol UNIQUEIDENTIFIER, LongVarBinaryCol LONGVARBINARY, LongVarCharCol LONGVARCHAR, "
    "NumericCol NUMERIC(7,3), SmallIntCol SMALLINT, TimeCol TIME, TimestampCol TIMESTAMP, "
    "TinyIntCol TINYINT, VarBinaryCol VARBINARY(16), VarCharCol VARCHAR(40), VarChar1Col VARCHAR(1))",
    "CREATE VIEW Clinic.ActivePatient AS SELECT p.PatientId, p.FullName FROM Clinic.Patient p "
    "JOIN Clinic.Encounter e ON e.PatientId = p.PatientId WHERE e.Active = 1",
    "CREATE SCHEMA Scratch",
    # IRIS stops listing a schema once it has no tables (GAP-009); the sentinel keeps Scratch listed
    # while tests create and drop their own tables there. Tests never drop it.
    "CREATE TABLE Scratch.Keep (Id INT PRIMARY KEY)",
]

ROWS: list[tuple[str, tuple]] = [
    (
        "INSERT INTO Clinic.Patient (PatientId, FullName, BirthDate, Weight) VALUES (?, ?, ?, ?)",
        (1, "Ana Souza", "1985-03-02", 61.50),
    ),
    (
        "INSERT INTO Clinic.Patient (PatientId, FullName, BirthDate, Weight) VALUES (?, ?, ?, ?)",
        (2, "Bruno Lima", "1990-11-20", 82.00),
    ),
    (
        "INSERT INTO Clinic.Encounter (EncounterId, PatientId, StartedAt, Notes, Active) VALUES (?, ?, ?, ?, ?)",
        (10, 1, "2026-11-01 09:00:00", "checkup", 1),
    ),
    ("INSERT INTO Billing.Patient (Code, Balance) VALUES (?, ?)", ("B-1", 120.5)),
    (
        "INSERT INTO AI.Embedding (Id, Content, Vec) VALUES (?, ?, TO_VECTOR(?, DOUBLE))",
        (1, "hello", "0.1,0.2,0.3"),
    ),
    (
        "INSERT INTO Types.AllTypes (Id, BigIntCol, BitCol, DateCol, DoubleCol, GuidCol, LongVarBinaryCol, "
        "LongVarCharCol, NumericCol, SmallIntCol, TimeCol, TimestampCol, TinyIntCol, VarBinaryCol, VarCharCol, "
        "VarChar1Col) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            9007199254740993,
            1,
            "2026-11-26",
            3.5,
            "6F9619FF-8B86-D011-B42D-00C04FC964FF",
            b"\x00\x01\x02",
            "a long text",
            1234.567,
            32000,
            "12:34:56",
            "2026-11-26 12:34:56",
            7,
            b"\x01\x02",
            "forty characters at most",
            "Y",
        ),
    ),
]

READERS = ("reader", "reader_dict")
DICTIONARY_TABLES = ("%Dictionary.CompiledProperty", "%Dictionary.PropertyDefinition")
READER_SCHEMAS = ("Clinic", "Billing", "AI", "Types")

GRANTS: list[str] = [
    f"GRANT SELECT ON SCHEMA {schema} TO {LOGINS['reader'].user}, {LOGINS['reader_dict'].user}"
    for schema in READER_SCHEMAS
] + [f"GRANT SELECT ON {table} TO {LOGINS['reader_dict'].user}" for table in DICTIONARY_TABLES]

# Dropped in this order (view first, then FK-safe); Scratch tables are found at run time.
CLEANUP_VIEWS = ("Clinic.ActivePatient",)
CLEANUP_TABLES = ("Clinic.Encounter", "Clinic.Patient", "Billing.Patient", "AI.Embedding", "Types.AllTypes")

PK = "PRIMARY KEY"
FK = "FOREIGN KEY"
UNIQUE = "UNIQUE"

# What the self-check verifies. Constraint tuples are (type, columns, detail): detail is the
# referenced table for a foreign key, the name for UqBillingCode, else None. Generated constraint
# names are never compared (research R9).
EXPECTED: dict = {
    "objects": {
        ("Clinic", "Patient"): "BASE TABLE",
        ("Clinic", "Encounter"): "BASE TABLE",
        ("Billing", "Patient"): "BASE TABLE",
        ("AI", "Embedding"): "BASE TABLE",
        ("Clinic", "ActivePatient"): "VIEW",
        ("Scratch", "Keep"): "BASE TABLE",
        ("Types", "AllTypes"): "BASE TABLE",
    },
    "columns": {
        ("Clinic", "Patient"): [
            ("PatientId", "integer"),
            ("FullName", "varchar"),
            ("BirthDate", "date"),
            ("Weight", "numeric"),
        ],
        ("Clinic", "Encounter"): [
            ("EncounterId", "integer"),
            ("PatientId", "integer"),
            ("StartedAt", "timestamp"),
            ("Notes", "longvarchar"),
            ("Active", "bit"),
        ],
        ("Billing", "Patient"): [("Code", "varchar"), ("Balance", "double")],
        ("AI", "Embedding"): [("Id", "integer"), ("Content", "varchar"), ("Vec", "varchar")],
        ("Clinic", "ActivePatient"): [("PatientId", "integer"), ("FullName", "varchar")],
        ("Scratch", "Keep"): [("Id", "integer")],
        ("Types", "AllTypes"): [
            ("Id", "integer"),
            ("BigIntCol", "bigint"),
            ("BitCol", "bit"),
            ("DateCol", "date"),
            ("DoubleCol", "double"),
            ("GuidCol", "guid"),
            ("LongVarBinaryCol", "longvarbinary"),
            ("LongVarCharCol", "longvarchar"),
            ("NumericCol", "numeric"),
            ("SmallIntCol", "smallint"),
            ("TimeCol", "time"),
            ("TimestampCol", "timestamp"),
            ("TinyIntCol", "tinyint"),
            ("VarBinaryCol", "varbinary"),
            ("VarCharCol", "varchar"),
            ("VarChar1Col", "varchar"),
        ],
    },
    "constraints": {
        ("Clinic", "Patient"): [(PK, ("PatientId",), None)],
        ("Clinic", "Encounter"): [
            (PK, ("EncounterId",), None),
            (FK, ("PatientId",), "Clinic.Patient"),
        ],
        ("Billing", "Patient"): [(PK, ("Code",), None), (UNIQUE, ("Code",), "UqBillingCode")],
        ("AI", "Embedding"): [(PK, ("Id",), None)],
        ("Scratch", "Keep"): [(PK, ("Id",), None)],
        ("Types", "AllTypes"): [(PK, ("Id",), None)],
    },
    "table_descriptions": {("Clinic", "Patient"): "Patients registered in the clinic"},
    "column_descriptions": {("Clinic", "Patient", "PatientId"): "Patient identifier"},
    "rows": {
        ("Clinic", "Patient"): 2,
        ("Clinic", "Encounter"): 1,
        ("Billing", "Patient"): 1,
        ("AI", "Embedding"): 1,
        ("Types", "AllTypes"): 1,
    },
    "view_sources": {("Clinic", "ActivePatient"): ("Clinic.Patient", "Clinic.Encounter")},
    "scratch_tables": ["Keep"],
    "reader_tables": ("Clinic.Patient", "Billing.Patient", "AI.Embedding", "Types.AllTypes"),
    "refused_writes": (
        "INSERT INTO Clinic.Patient (PatientId, FullName) VALUES (99, 'Refused')",
        "CREATE TABLE Scratch.ReaderProbe (Id INT)",
    ),
    "vector_type": (("AI", "Embedding", "Vec"), "varchar"),
}

# "Does not exist" during cleanup: table or view (-30), schema (-473), user (-118 with this text).
_ABSENT_CODES = (-30, -473)
_RETRYABLE = ("Error code: -1", "refused", "timed out", "timeout")
_SQLCODE = re.compile(r"SQLCODE: <(-?\d+)>")
_PASSWORD = re.compile(r"(IDENTIFIED\s+BY\s+)\S+", re.IGNORECASE)


class FixtureError(Exception):
    exit_code = 1


class NotPreparedError(FixtureError):
    """The instance cannot be reached or is not prepared (exit 2)."""

    exit_code = 2


class LoadError(FixtureError):
    """A DDL, DML or grant statement failed (exit 3)."""

    exit_code = 3

    def __init__(self, statement: str, error: BaseException):
        self.statement = _head(statement)
        self.error = _first_line(error)
        super().__init__(f"statement failed: {self.statement!r}: {self.error}")


class SelfCheckError(FixtureError):
    """A fixture object or behavior is not as expected (exit 1)."""

    exit_code = 1

    def __init__(self, check: str, obj: str, expected, actual):
        self.check, self.obj, self.expected, self.actual = check, obj, expected, actual
        super().__init__(f"{check} {obj}: expected {expected}, actual {actual}")


def _first_line(error: BaseException) -> str:
    text = str(error).strip()
    return text.splitlines()[0] if text else type(error).__name__


def _head(statement: str) -> str:
    """First 60 characters of a statement, one line, with any password masked."""
    return _PASSWORD.sub(r"\1***", " ".join(statement.split()))[:60]


def sqlcode(error: BaseException) -> int | None:
    """The SQLCODE carried by a driver error, or None."""
    found = _SQLCODE.search(str(error))
    return int(found.group(1)) if found else None


def _connect(host: str, port: int, namespace: str, user: str, password: str, wait_seconds: float = 0):
    """Connect with the driver, retrying while the superserver refuses or times out."""
    import iris  # pylint: disable=import-outside-toplevel

    started = time.monotonic()
    while True:
        try:
            return iris.connect(host, int(port), namespace, user, password)
        except Exception as exc:  # pylint: disable=broad-except
            message = str(exc)
            where = f"{user}@{host}:{port}/{namespace}"
            if "Password change required" in message:
                raise NotPreparedError(
                    f"{where}: the password must be changed; run the unexpire step (fixtures/iris/start-iris.sh)"
                ) from None
            if "Access Denied" in message:
                raise NotPreparedError(f"{where}: access denied (wrong user or password)") from None
            if not any(marker in message for marker in _RETRYABLE):
                raise NotPreparedError(f"cannot connect to {where}: {_first_line(exc)}") from None
            waited = time.monotonic() - started
            if waited >= wait_seconds:
                raise NotPreparedError(
                    f"cannot connect to {host}:{port} after waiting {waited:.0f}s "
                    f"(IRIS_WAIT_SECONDS={wait_seconds:g}): {_first_line(exc)}"
                ) from None
            time.sleep(2)


def _execute(cursor, statement: str, params: tuple | None = None) -> None:
    try:
        if params is None:
            cursor.execute(statement)
        else:
            cursor.execute(statement, list(params))
    except Exception as exc:  # pylint: disable=broad-except
        raise LoadError(statement, exc) from None


def _drop_if_exists(cursor, statement: str) -> None:
    try:
        cursor.execute(statement)
    except Exception as exc:  # pylint: disable=broad-except
        code = sqlcode(exc)
        if code in _ABSENT_CODES or (code == -118 and "does not exist" in str(exc)):
            return
        raise LoadError(statement, exc) from None


def _cleanup(cursor) -> None:
    """Remove every fixture object, any leftover Scratch object, the Scratch schema and the users."""
    for view in CLEANUP_VIEWS:
        _drop_if_exists(cursor, f"DROP VIEW {view}")
    for table in CLEANUP_TABLES:
        _drop_if_exists(cursor, f"DROP TABLE {table}")
    _execute(
        cursor,
        "SELECT TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = ?",
        ("Scratch",),
    )
    for name, kind in list(cursor.fetchall() or []):
        verb = "VIEW" if kind == "VIEW" else "TABLE"
        _drop_if_exists(cursor, f'DROP {verb} Scratch."{name}"')
    _drop_if_exists(cursor, "DROP SCHEMA Scratch")
    for login in READERS:
        _drop_if_exists(cursor, f"DROP USER {LOGINS[login].user}")


def _create(cursor) -> None:
    for statement in DDL:
        _execute(cursor, statement)
    for statement, params in ROWS:
        _execute(cursor, statement, params)
    for login in READERS:
        _execute(cursor, f"CREATE USER {LOGINS[login].user} IDENTIFIED BY {LOGINS[login].password}")
    for statement in GRANTS:
        _execute(cursor, statement)


def _query(cursor, statement: str, params: tuple = ()) -> list:
    if params:
        cursor.execute(statement, list(params))
    else:
        cursor.execute(statement)
    return [tuple(row) for row in (cursor.fetchall() or [])]


def _columns(cursor, schema: str, name: str) -> list[tuple[str, str]]:
    rows = _query(
        cursor,
        "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
        (schema, name),
    )
    # The catalog may compare names case-insensitively; keep exact matches only (Principle III).
    return [(column, data_type) for s, n, column, data_type in rows if (s, n) == (schema, name)]


def _constraints(cursor, schema: str, name: str) -> list[tuple[str, tuple[str, ...], str | None]]:
    constraints = [
        (constraint_schema, constraint_name, kind)
        for constraint_schema, constraint_name, s, n, kind in _query(
            cursor,
            "SELECT CONSTRAINT_SCHEMA, CONSTRAINT_NAME, TABLE_SCHEMA, TABLE_NAME, CONSTRAINT_TYPE "
            "FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
            (schema, name),
        )
        if (s, n) == (schema, name)
    ]
    key_columns = _query(
        cursor,
        "SELECT CONSTRAINT_SCHEMA, CONSTRAINT_NAME, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME "
        "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
        "ORDER BY ORDINAL_POSITION",
        (schema, name),
    )
    references = {
        (constraint_schema, constraint_name): f"{target_schema}.{target_table}"
        for constraint_schema, constraint_name, target_schema, target_table in _query(
            cursor,
            "SELECT CONSTRAINT_SCHEMA, CONSTRAINT_NAME, UNIQUE_CONSTRAINT_SCHEMA, UNIQUE_CONSTRAINT_TABLE "
            "FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = ? "
            "AND CONSTRAINT_TABLE_NAME = ?",
            (schema, name),
        )
    }
    found = []
    for constraint_schema, constraint_name, kind in constraints:
        columns = tuple(
            column
            for cs, cn, s, n, column in key_columns
            if (cs, cn, s, n) == (constraint_schema, constraint_name, schema, name)
        )
        if kind == FK:
            detail = references.get((constraint_schema, constraint_name))
        elif kind == UNIQUE and constraint_name == "UqBillingCode":
            detail = constraint_name
        else:
            detail = None
        found.append((kind, columns, detail))
    return sorted(found, key=repr)


def _scratch_tables(cursor) -> list[str]:
    rows = _query(
        cursor,
        "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = ?",
        ("Scratch",),
    )
    return sorted(name for schema, name in rows if schema == "Scratch")


def _is_listed(cursor, schema: str) -> bool:
    rows = _query(cursor, "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = ?", (schema,))
    return any(row[0] == schema for row in rows)


def reader_outcome(cursor, expected: dict) -> dict[str, object]:
    """What a login can do: read the reader tables, read each dictionary table, write (C8-C10)."""
    outcome: dict[str, object] = {}
    for table in expected["reader_tables"]:
        outcome[f"read {table}"] = _attempt(cursor, f"SELECT TOP 1 * FROM {table}")
    for table in DICTIONARY_TABLES:
        outcome[f"read {table}"] = _attempt(cursor, f"SELECT TOP 1 Name FROM {table}")
    for statement in expected["refused_writes"]:
        outcome[f"write {_head(statement)}"] = _attempt(cursor, statement)
    return outcome


def _attempt(cursor, statement: str) -> str:
    try:
        cursor.execute(statement)
        if statement.lstrip().upper().startswith("SELECT"):
            cursor.fetchall()
    except Exception as exc:  # pylint: disable=broad-except
        return f"SQLCODE {sqlcode(exc)}"
    return "ok"


def _catalog_value(cursor, view: str, column: str, key: tuple[str, ...]):
    """One INFORMATION_SCHEMA value for an exact (schema, name[, column]) key, or "missing"."""
    names = ("TABLE_SCHEMA", "TABLE_NAME", "COLUMN_NAME")[: len(key)]
    where = " AND ".join(f"{name} = ?" for name in names)
    rows = _query(cursor, f"SELECT {', '.join(names)}, {column} FROM INFORMATION_SCHEMA.{view} WHERE {where}", key)
    return next((row[-1] for row in rows if row[:-1] == key), "missing")


class _Checker:
    """Runs the checks, records the passes and stops at the first mismatch."""

    def __init__(self, report: Callable[[str], None] | None):
        self.report = report
        self.passes: list[tuple[str, str, str]] = []

    def __call__(self, check_id: str, what: str, obj: str, want, measure: Callable[[], object]) -> None:
        try:
            got = measure()
        except Exception as exc:  # pylint: disable=broad-except
            got = f"error {_first_line(exc)}"
        if got != want:
            raise SelfCheckError(check_id, obj, want, got)
        self.passes.append((check_id, what, obj))
        if self.report:
            self.report(f"PASS {check_id} {what} {obj}")


def _check_catalog(check: _Checker, cur, expected: dict) -> None:
    """C1-C6: objects, columns, constraints, descriptions, rows and the view, as the admin sees them."""
    for (schema, name), kind in expected["objects"].items():
        check(
            "C1",
            "object",
            f"{schema}.{name}",
            kind,
            lambda k=(schema, name): _catalog_value(cur, "TABLES", "TABLE_TYPE", k),
        )
    for (schema, name), columns in expected["columns"].items():
        check("C2", "columns", f"{schema}.{name}", columns, lambda s=schema, n=name: _columns(cur, s, n))
    for (schema, name), constraints in expected["constraints"].items():
        want = sorted(constraints, key=repr)
        check("C3", "constraints", f"{schema}.{name}", want, lambda s=schema, n=name: _constraints(cur, s, n))
    for key, text in expected["table_descriptions"].items():
        check("C4", "description", ".".join(key), text, lambda k=key: _catalog_value(cur, "TABLES", "DESCRIPTION", k))
    for key, text in expected["column_descriptions"].items():
        check("C4", "description", ".".join(key), text, lambda k=key: _catalog_value(cur, "COLUMNS", "DESCRIPTION", k))
    for (schema, name), count in expected["rows"].items():
        check(
            "C5",
            "rows",
            f"{schema}.{name}",
            count,
            lambda t=f"{schema}.{name}": _query(cur, f"SELECT COUNT(*) FROM {t}")[0][0],
        )
    for key, sources in expected["view_sources"].items():

        def view_reads(key=key, sources=sources):
            text = _catalog_value(cur, "VIEWS", "VIEW_DEFINITION", key) or ""
            return [source for source in sources if source in text]

        check("C6", "view definition", ".".join(key), list(sources), view_reads)


def _check_scratch(check: _Checker, cur, expected: dict) -> None:
    """C7: Scratch holds only the sentinel, stays listed, and the admin can create and drop in it."""
    check("C7", "tables", "Scratch", expected["scratch_tables"], lambda: _scratch_tables(cur))
    check("C7", "rows", "Scratch.Keep", 0, lambda: _query(cur, "SELECT COUNT(*) FROM Scratch.Keep")[0][0])
    check("C7", "listed in SCHEMATA", "Scratch", True, lambda: _is_listed(cur, "Scratch"))

    def admin_probe():
        cur.execute("CREATE TABLE Scratch.Probe (Id INT)")
        cur.execute("DROP TABLE Scratch.Probe")
        return "ok"

    check("C7", "admin create and drop", "Scratch.Probe", "ok", admin_probe)


def _check_readers(check: _Checker, connect: Callable[[str, str], object], expected: dict) -> None:
    """C8-C10: each reader reads its schemas, gets the dictionary iff granted, and cannot write."""
    for check_id, login in (("C8", "reader"), ("C9", "reader_dict")):
        account = LOGINS[login]
        reader = connect(account.user, account.password)
        try:
            outcome = reader_outcome(reader.cursor(), expected)
        finally:
            reader.close()
        for table in expected["reader_tables"]:
            check(check_id, "read", f"{account.user} {table}", "ok", lambda k=f"read {table}", o=outcome: o[k])
        dictionary = "ok" if account.has_dict_grant else "SQLCODE -99"
        for table in DICTIONARY_TABLES:
            check(
                check_id, "dictionary", f"{account.user} {table}", dictionary, lambda k=f"read {table}", o=outcome: o[k]
            )
        for statement in expected["refused_writes"]:
            head = _head(statement)
            check(
                "C10",
                "write refused",
                f"{account.user} {head}",
                "SQLCODE -99",
                lambda k=f"write {head}", o=outcome: o[k],
            )


def self_check(  # pylint: disable=too-many-arguments
    host: str,
    port: int,
    namespace: str = "USER",
    admin_user: str = LOGINS["admin"].user,
    admin_password: str = LOGINS["admin"].password,
    expected: dict | None = None,
    report: Callable[[str], None] | None = None,
) -> list[tuple[str, str, str]]:
    """Verify checks C1-C11 and return the passes as (check, what, object); raise SelfCheckError."""
    expected = EXPECTED if expected is None else expected
    check = _Checker(report)
    conn = _connect(host, port, namespace, admin_user, admin_password)
    try:
        cur = conn.cursor()
        _check_catalog(check, cur, expected)
        _check_scratch(check, cur, expected)
        _check_readers(check, lambda user, password: _connect(host, port, namespace, user, password), expected)
        (schema, name, column), data_type = expected["vector_type"]
        check(
            "C11",
            "catalog DATA_TYPE",
            f"{schema}.{name}.{column}",
            data_type,
            lambda: dict(_columns(cur, schema, name)).get(column, "missing"),
        )
    finally:
        conn.close()
    return check.passes


def zversion(host: str, port: int, namespace: str, admin_user: str, admin_password: str) -> str:
    conn = _connect(host, port, namespace, admin_user, admin_password)
    try:
        return _query(conn.cursor(), "SELECT $ZVERSION")[0][0]
    finally:
        conn.close()


def load(  # pylint: disable=too-many-arguments
    host: str,
    port: int,
    namespace: str = "USER",
    admin_user: str = LOGINS["admin"].user,
    admin_password: str = LOGINS["admin"].password,
    wait_seconds: float = 60,
    report: Callable[[str], None] | None = None,
) -> list[tuple[str, str, str]]:
    """Drop and recreate the fixture catalog, then run the self-check. Returns the passes."""
    conn = _connect(host, port, namespace, admin_user, admin_password, wait_seconds)
    try:
        cursor = conn.cursor()
        _cleanup(cursor)
        _create(cursor)
        conn.commit()
    finally:
        conn.close()
    return self_check(host, port, namespace, admin_user, admin_password, report=report)


def _say(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main() -> int:
    env = os.environ
    host = env.get("IRIS_HOST", "127.0.0.1")
    port = int(env.get("IRIS_PORT", "1972"))
    namespace = env.get("IRIS_NAMESPACE", "USER")
    admin_user = env.get("IRIS_ADMIN_USER", LOGINS["admin"].user)
    admin_password = env.get("IRIS_ADMIN_PASSWORD", LOGINS["admin"].password)
    wait_seconds = float(env.get("IRIS_WAIT_SECONDS", "60"))
    try:
        load(host, port, namespace, admin_user, admin_password, wait_seconds, report=_say)
        version = zversion(host, port, namespace, admin_user, admin_password)
    except FixtureError as exc:
        sys.stderr.write(f"FIXTURES FAILED: {exc}\n")
        return exc.exit_code
    _say(f"FIXTURES OK v{CATALOG_VERSION} {version}")
    return 0


def expected_copy() -> dict:
    """A deep copy of EXPECTED, for tests that make the self-check fail on purpose."""
    return copy.deepcopy(EXPECTED)


if __name__ == "__main__":
    sys.exit(main())
