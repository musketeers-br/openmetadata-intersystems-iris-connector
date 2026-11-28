"""Tests of the fixture loader and its self-check (spec 001, FR-001..FR-007).

Offline tests replace the driver with a fake and need no IRIS. Live tests need a prepared instance
(fixtures/iris/start-iris.sh) and IRIS_HOST / IRIS_PORT; they reload the fixtures where they change
state.
"""
import importlib.util
import sys
import types

import pytest

from seed import CANDIDATES

REFUSED = "<COMMUNICATION LINK ERROR> Failed to connect to server; Details: Error code: -1 Error message: "
EXPIRED = (
    "<COMMUNICATION LINK ERROR> Failed to connect to server; Details: <COMMUNICATION ERROR> "
    "Invalid Message received; Details: Password change required"
)


# --- offline ------------------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, fail_on=None):
        self.statements = []
        self.fail_on = fail_on

    def execute(self, statement, params=None):
        self.statements.append(statement)
        if statement == self.fail_on:
            raise RuntimeError("[SQLCODE: <-1>:<Invalid SQL statement>]")

    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def close(self):
        pass


class FakeClock:
    """Stands in for the loader's `time` module: sleeping advances the clock, nothing waits."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def fake_driver(monkeypatch, connect):
    module = types.ModuleType("iris")
    module.connect = connect
    monkeypatch.setitem(sys.modules, "iris", module)


def env(monkeypatch, **values):
    base = {"IRIS_HOST": "10.0.0.9", "IRIS_PORT": "4242", "IRIS_WAIT_SECONDS": "0"}
    base.update(values)
    for key, value in base.items():
        monkeypatch.setenv(key, value)


def test_connection_error_exits_2_and_names_host_port(seed_module, monkeypatch, capsys):
    def connect(*_):
        raise RuntimeError(REFUSED)

    fake_driver(monkeypatch, connect)
    monkeypatch.setattr(seed_module, "time", FakeClock())
    env(monkeypatch)
    assert seed_module.main() == 2
    assert "10.0.0.9:4242" in capsys.readouterr().err


def test_expired_password_exits_2_and_points_to_the_start_script(seed_module, monkeypatch, capsys):
    def connect(*_):
        raise RuntimeError(EXPIRED)

    fake_driver(monkeypatch, connect)
    env(monkeypatch, IRIS_WAIT_SECONDS="60")
    assert seed_module.main() == 2
    assert "start-iris.sh" in capsys.readouterr().err


def test_failing_statement_exits_3_with_its_head_and_the_iris_error(seed_module, monkeypatch, capsys):
    failing = seed_module.DDL[2]
    fake_driver(monkeypatch, lambda *_: FakeConnection(FakeCursor(fail_on=failing)))
    env(monkeypatch)
    assert seed_module.main() == 3
    err = capsys.readouterr().err
    assert " ".join(failing.split())[:60] in err
    assert "SQLCODE: <-1>" in err


def test_import_does_not_connect(monkeypatch):
    def connect(*_):
        raise AssertionError("importing the loader must not connect")

    fake_driver(monkeypatch, connect)
    path = next(p for p in CANDIDATES if p.is_file())
    spec = importlib.util.spec_from_file_location("iris_fixture_seed_import_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.CATALOG_VERSION == 4
    assert set(module.VERSION_HISTORY) == {1, 2, 3, 4}
    assert set(module.LOGINS) == {"admin", "reader", "reader_dict"}


def test_passwords_are_never_printed(seed_module, monkeypatch, capsys):
    token = "Tok3n-9f2c1d"
    reader = seed_module.LOGINS["reader"]
    create_user = f"CREATE USER {reader.user} IDENTIFIED BY {reader.password}"
    fake_driver(monkeypatch, lambda *_: FakeConnection(FakeCursor(fail_on=create_user)))
    env(monkeypatch, IRIS_ADMIN_PASSWORD=token)
    assert seed_module.main() == 3
    first = capsys.readouterr()

    def denied(*_):
        raise RuntimeError("<COMMUNICATION LINK ERROR> Invalid Message received; Details: Access Denied")

    fake_driver(monkeypatch, denied)
    assert seed_module.main() == 2
    second = capsys.readouterr()
    printed = first.out + first.err + second.out + second.err
    assert "IDENTIFIED BY ***" in first.err
    assert token not in printed
    assert reader.password not in printed


def test_connect_retries_while_refused_then_gives_up(seed_module, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(seed_module, "time", clock)
    calls = []

    def refused_twice(*_):
        calls.append(1)
        if len(calls) <= 2:
            raise RuntimeError("Connection refused")
        return FakeConnection(FakeCursor())

    fake_driver(monkeypatch, refused_twice)
    assert isinstance(seed_module._connect("h", 1, "USER", "u", "p", wait_seconds=10), FakeConnection)
    assert len(calls) == 3

    def always_refused(*_):
        raise RuntimeError("Connection refused")

    fake_driver(monkeypatch, always_refused)
    with pytest.raises(seed_module.NotPreparedError, match=r"after waiting \d+s"):
        seed_module._connect("h", 1, "USER", "u", "p", wait_seconds=1)

    calls.clear()

    def expired(*_):
        calls.append(1)
        raise RuntimeError(EXPIRED)

    fake_driver(monkeypatch, expired)
    with pytest.raises(seed_module.NotPreparedError, match="unexpire"):
        seed_module._connect("h", 1, "USER", "u", "p", wait_seconds=60)
    assert len(calls) == 1


# --- live ---------------------------------------------------------------------------------------


def _sqlcode_of(callable_):
    try:
        callable_()
    except Exception as exc:  # pylint: disable=broad-except
        return str(exc)
    return "ok"


def snapshot(seed, admin, connect):
    cursor = admin.cursor()
    state = {}
    for schema, name in seed.EXPECTED["rows"]:
        cursor.execute(f"SELECT * FROM {schema}.{name} ORDER BY 1")
        state[f"rows {schema}.{name}"] = [tuple(row) for row in cursor.fetchall()]
    for schema, name in seed.EXPECTED["columns"]:
        state[f"columns {schema}.{name}"] = seed._columns(cursor, schema, name)
    for schema, name in seed.EXPECTED["constraints"]:
        state[f"constraints {schema}.{name}"] = seed._constraints(cursor, schema, name)
    state["scratch"] = seed._scratch_tables(cursor)
    # Users and grants live in %SYS; compare them by what each login can do.
    for login in seed.READERS:
        account = seed.LOGINS[login]
        conn = connect(account.user, account.password)
        try:
            state[login] = seed.reader_outcome(conn.cursor(), seed.EXPECTED)
        finally:
            conn.close()
    return state


def test_load_reports_all_checks(seed_module, loaded, monkeypatch, capsys):
    monkeypatch.setenv("IRIS_HOST", loaded["host"])
    monkeypatch.setenv("IRIS_PORT", str(loaded["port"]))
    assert seed_module.main() == 0
    out = capsys.readouterr().out
    for number in range(1, 13):
        assert f"PASS C{number} " in out
    assert f"FIXTURES OK v{seed_module.CATALOG_VERSION} IRIS" in out


def test_load_is_idempotent(seed_module, loaded, connect):
    seed_module.load(**loaded)
    admin = connect(loaded["admin_user"], loaded["admin_password"])
    try:
        first = snapshot(seed_module, admin, connect)
        seed_module.load(**loaded)
        second = snapshot(seed_module, admin, connect)
    finally:
        admin.close()
    assert first["rows Clinic.Patient"] and first["reader"]
    assert first == second


def test_dictionary_toggle(seed_module, loaded, connect):
    for login, allowed in (("reader", False), ("reader_dict", True)):
        account = seed_module.LOGINS[login]
        conn = connect(account.user, account.password)
        try:
            for table in seed_module.DICTIONARY_TABLES:
                cursor = conn.cursor()
                result = _sqlcode_of(lambda: (cursor.execute(f"SELECT TOP 1 Name FROM {table}"), cursor.fetchall()))
                if allowed:
                    assert result == "ok", f"{account.user} {table}: {result}"
                else:
                    assert "SQLCODE: <-99>" in result, f"{account.user} {table}: {result}"
        finally:
            conn.close()


def test_readers_cannot_write(seed_module, loaded, connect):
    for login in seed_module.READERS:
        account = seed_module.LOGINS[login]
        conn = connect(account.user, account.password)
        try:
            for statement in (
                "INSERT INTO Clinic.Patient (PatientId, FullName) VALUES (98, 'Nope')",
                "CREATE TABLE Scratch.ReaderProbe (Id INT)",
            ):
                result = _sqlcode_of(lambda: conn.cursor().execute(statement))
                assert "SQLCODE: <-99>" in result, f"{account.user}: {statement}: {result}"
        finally:
            conn.close()


def test_self_check_can_fail(seed_module, loaded):
    expected = seed_module.expected_copy()
    expected["rows"][("Clinic", "Patient")] = 3
    with pytest.raises(seed_module.SelfCheckError) as failure:
        seed_module.self_check(**loaded, expected=expected)
    message = str(failure.value)
    for part in ("C5", "Clinic.Patient", "expected 3", "actual 2"):
        assert part in message


def test_missing_object_is_named(seed_module, loaded, admin_conn):
    admin_conn.cursor().execute("DROP TABLE Billing.Patient")
    try:
        with pytest.raises(seed_module.SelfCheckError) as failure:
            seed_module.self_check(**loaded)
        assert failure.value.check == "C1"
        assert failure.value.obj == "Billing.Patient"
    finally:
        seed_module.load(**loaded)


def test_scratch_is_emptied(seed_module, loaded, admin_conn):
    admin_conn.cursor().execute("CREATE TABLE Scratch.Leftover (Id INT)")
    passes = seed_module.load(**loaded)
    assert seed_module._scratch_tables(admin_conn.cursor()) == ["Keep"]
    assert ("C7", "tables", "Scratch") in passes


# The 15 DATA_TYPE values the IRIS SQL catalog reports on all three tracks (spec 003, research R1).
CATALOG_TYPES = {
    "bigint", "bit", "date", "double", "guid", "integer", "longvarbinary", "longvarchar",
    "numeric", "smallint", "time", "timestamp", "tinyint", "varbinary", "varchar",
}  # fmt: skip


def test_type_fixture_has_every_catalog_type(seed_module, loaded, admin_conn):
    cursor = admin_conn.cursor()
    columns = seed_module._columns(cursor, "Types", "AllTypes")
    assert {data_type for _, data_type in columns} == CATALOG_TYPES
    cursor.execute(
        "SELECT CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = 'Types' AND TABLE_NAME = 'AllTypes' AND COLUMN_NAME = 'VarChar1Col'"
    )
    assert cursor.fetchall()[0][0] == 1


def test_readers_can_read_the_type_fixture(seed_module, loaded, connect):
    for login in seed_module.READERS:
        account = seed_module.LOGINS[login]
        conn = connect(account.user, account.password)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Types.AllTypes")
            assert cursor.fetchall()[0][0] == 1, account.user
        finally:
            conn.close()


RESTRICTED = ("Secret", "ColumnGrant", "Hidden")


def test_the_restricted_tables_exist_for_the_admin(seed_module, loaded, admin_conn):
    objects = seed_module.EXPECTED["objects"]
    assert {name for schema, name in objects if schema == "Restricted"} == set(RESTRICTED)
    assert seed_module._columns(admin_conn.cursor(), "Restricted", "ColumnGrant") == [
        ("Id", "integer"),
        ("Hidden", "varchar"),
    ]
    assert "Restricted" not in seed_module.READER_SCHEMAS


def test_readers_see_but_cannot_read_the_restricted_tables(seed_module, loaded, connect):
    """Spec 005: REFERENCES lists Secret, a one-column SELECT lists ColumnGrant with Id only, Hidden stays unseen."""
    for login in seed_module.READERS:
        account = seed_module.LOGINS[login]
        conn = connect(account.user, account.password)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'Restricted'")
            assert sorted(row[0] for row in cursor.fetchall()) == ["ColumnGrant", "Secret"], account.user
            assert [c for c, _ in seed_module._columns(cursor, "Restricted", "ColumnGrant")] == ["Id"], account.user
            for table in RESTRICTED:
                result = _sqlcode_of(lambda t=table: (cursor.execute(f"SELECT TOP 1 * FROM Restricted.{t}"),))
                assert "SQLCODE: <-99>" in result, f"{account.user} Restricted.{table}: {result}"
            cursor.execute("SELECT TOP 1 Id FROM Restricted.ColumnGrant")
            assert cursor.fetchall()[0][0] == 1, account.user
        finally:
            conn.close()


# Spec 004: the three VECTOR columns, as the SQL catalog reports them (varchar, with these lengths).
VECTOR_LENGTHS = {"Vec": 1037, "Vec4": 83, "vec_low": 691}


def test_the_vector_fixture(seed_module, loaded, admin_conn):
    cursor = admin_conn.cursor()
    assert seed_module._columns(cursor, "AI", "Embedding") == [
        ("Id", "integer"),
        ("Content", "varchar"),
        ("Vec", "varchar"),
        ("Vec4", "varchar"),
        ("vec_low", "varchar"),
    ]
    cursor.execute(
        "SELECT COLUMN_NAME, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = 'AI' AND TABLE_NAME = 'Embedding'"
    )
    lengths = {name: length for name, length in cursor.fetchall() if name in VECTOR_LENGTHS}
    assert lengths == VECTOR_LENGTHS
    assert seed_module.EXPECTED["vectors"] == {
        ("AI", "Embedding", "Vec"): ("DOUBLE", 3),
        ("AI", "Embedding", "Vec4"): ("INT", 4),
        ("AI", "Embedding", "vec_low"): ("FLOAT", 2),
    }
    cursor.execute('SELECT Vec4, "vec_low" FROM AI.Embedding WHERE Id = 1')
    assert all(value is not None for value in cursor.fetchall()[0])


def test_scratch_stays_listed(seed_module, loaded, admin_conn):
    cursor = admin_conn.cursor()
    cursor.execute("CREATE TABLE Scratch.Tmp (Id INT)")
    cursor.execute("DROP TABLE Scratch.Tmp")
    assert seed_module._is_listed(cursor, "Scratch")
    assert seed_module._scratch_tables(cursor) == ["Keep"]
