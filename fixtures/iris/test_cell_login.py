"""Driver-level check of the cell's login, before the connector tests run (spec 001, FR-016, T021).

With IRIS_LOGIN set (every CI cell), only that login runs; otherwise all three. The test id carries
the login, so a job summary shows which one ran. Needs a seeded instance (IRIS_HOST, IRIS_PORT).
"""
import importlib.util
import os

import pytest

from seed import CANDIDATES


def _catalog():
    path = next(p for p in CANDIDATES if p.is_file())
    spec = importlib.util.spec_from_file_location("iris_fixture_catalog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CATALOG = _catalog()
SELECTED = [os.environ["IRIS_LOGIN"]] if os.environ.get("IRIS_LOGIN") else sorted(CATALOG.LOGINS)


def _error(cursor, statement, params=()):
    """The error text of a statement, or None when it succeeds."""
    try:
        cursor.execute(statement, list(params))
    except Exception as exc:  # noqa: BLE001 - the driver raises several types; the text is what counts
        return str(exc)
    return None


@pytest.fixture(params=SELECTED)
def login(request, iris_env, connect):
    name = request.param
    if name not in CATALOG.LOGINS:
        raise pytest.UsageError(f"IRIS_LOGIN={name!r}: expected one of {', '.join(sorted(CATALOG.LOGINS))}")
    account = CATALOG.LOGINS[name]
    if account.is_admin:
        user, password = iris_env["admin_user"], iris_env["admin_password"]
    else:
        user, password = account.user, account.password
    conn = connect(user, password)
    yield name, account, conn.cursor()
    conn.close()


def test_login_reads_the_fixtures(login):
    name, _, cursor = login
    cursor.execute("SELECT COUNT(*) FROM Clinic.Patient")
    assert cursor.fetchall()[0][0] == CATALOG.EXPECTED["rows"][("Clinic", "Patient")], name


def test_dictionary_access_matches_the_grant(login):
    name, account, cursor = login
    error = _error(cursor, "SELECT TOP 1 Name FROM %Dictionary.CompiledProperty")
    if account.has_dict_grant:
        assert error is None, f"{name}: {error}"
    else:
        assert error is not None, f"{name} reads the class dictionary without the grant"
        assert "-99" in error, f"{name}: {error}"


def test_write_is_refused_unless_admin(login):
    name, account, cursor = login
    insert = "INSERT INTO Clinic.Patient (PatientId, FullName) VALUES (?, ?)"
    if account.is_admin:
        cursor.execute("START TRANSACTION")
        try:
            assert _error(cursor, insert, (999, "Probe")) is None, name
        finally:
            cursor.execute("ROLLBACK")
        cursor.execute("SELECT COUNT(*) FROM Clinic.Patient")
        assert cursor.fetchall()[0][0] == CATALOG.EXPECTED["rows"][("Clinic", "Patient")], "rollback failed"
    else:
        error = _error(cursor, insert, (999, "Probe"))
        assert error is not None, f"{name} could insert into Clinic.Patient"
        assert "-99" in error, f"{name}: {error}"
