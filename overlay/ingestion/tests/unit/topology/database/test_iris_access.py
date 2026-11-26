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
Access gaps (spec 005): every read of the IRIS source that fails with a database error becomes one IRIS-ACCESS status
warning (ADR-0008), and the run goes on. No IRIS and no OpenMetadata server needed.
"""

import logging
from types import SimpleNamespace

import pytest
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.exc import OperationalError

from metadata.generated.schema.entity.data.table import TableType
from metadata.ingestion.api.status import Status
from metadata.ingestion.source.database.iris.metadata import IrisSource
from metadata.ingestion.source.database.iris.queries import (
    IRIS_COLUMN_TYPES,
    IRIS_READ_PROBE,
    IRIS_UNIQUE_CONSTRAINTS,
)
from metadata.ingestion.source.database.sql_column_handler import SqlColumnHandlerMixin

FIRST_LINE = "[SQLCODE: <-99>:<Privilege violation>]"
SECRET = "password=S3cret!pw"
SCHEMA_FQN = "iris_test.USER.S"
TABLE_FQN = "iris_test.USER.S.T"


def _db_error():
    return OperationalError("SELECT 1", {}, Exception(f"{FIRST_LINE}\n{SECRET}"))


class _Inspector:
    """Stub of the dialect inspector; the methods named in `fail` raise a database error (or `error`)."""

    def __init__(self, fail=(), error=None):
        self.fail = set(fail)
        self.error = error

    def _call(self, name, value):
        if name in self.fail:
            raise self.error or _db_error()
        return value

    def get_table_names(self, schema):
        return self._call("get_table_names", ["T"])

    def get_view_names(self, schema):
        return self._call("get_view_names", ["V"])

    def get_columns(self, table, schema, **kw):
        return self._call("get_columns", [{"name": "A", "type": "x"}])

    def get_pk_constraint(self, table, schema):
        return self._call("get_pk_constraint", {"constrained_columns": ["A"]})

    def get_foreign_keys(self, table, schema):
        return self._call("get_foreign_keys", [{"constrained_columns": ["A"], "referred_table": "U"}])

    def get_table_comment(self, table, schema):
        return self._call("get_table_comment", {"text": "about"})

    def get_view_definition(self, table, schema):
        return self._call("get_view_definition", "SELECT 1")


class _Result:
    def __init__(self, connection):
        self.connection = connection

    def close(self):
        self.connection.closed_results += 1


class _Connection:
    """A real dialect for quoting. `fail` names what raises: a queries.py constant, or "probe" for the read probe."""

    dialect = DefaultDialect()

    def __init__(self, fail=(), error=None):
        self.fail = set(fail)
        self.error = error
        self.statements = []
        self.closed_results = 0

    def execute(self, statement, params=None):
        self.statements.append(str(statement))
        if str(statement) in self.fail:
            raise self.error or _db_error()
        return iter(())

    def exec_driver_sql(self, statement):
        self.statements.append(statement)
        if "probe" in self.fail:
            raise self.error or _db_error()
        return _Result(self)


def _source(connection=None, inspector=None):
    source = IrisSource.__new__(IrisSource)
    source.status = Status()
    source.metadata = None
    source.context = SimpleNamespace(
        get=lambda: SimpleNamespace(database_service="iris_test", database="USER"),
        get_current_thread_id=lambda: 1,
    )
    source._connection_map = {1: connection or _Connection()}
    source._inspector_map = {1: inspector or _Inspector()}
    return source


# (feature, key, object in the message, what fails, the read, its empty value)
READS = [
    ("tables", SCHEMA_FQN, "S", {"get_table_names"}, lambda s, i: s.query_table_names_and_types("S"), []),
    ("views", SCHEMA_FQN, "S", {"get_view_names"}, lambda s, i: s.query_view_names_and_types("S"), []),
    ("columns", TABLE_FQN, "S.T", {"get_columns"}, lambda s, i: s._get_columns_internal("S", "T", "USER", i), []),
    (
        "columns",
        TABLE_FQN,
        "S.T",
        {IRIS_COLUMN_TYPES},
        lambda s, i: s._get_columns_internal("S", "T", "USER", i),
        [{"name": "A", "type": "x"}],
    ),
    ("keys", TABLE_FQN, "S.T", {"get_pk_constraint"}, lambda s, i: s._get_columns_with_constraints("S", "T", i)[0], []),
    (
        "keys",
        TABLE_FQN,
        "S.T",
        {IRIS_UNIQUE_CONSTRAINTS},
        lambda s, i: s._get_columns_with_constraints("S", "T", i)[1],
        [],
    ),
    ("keys", TABLE_FQN, "S.T", {"get_foreign_keys"}, lambda s, i: s._get_columns_with_constraints("S", "T", i)[2], []),
    ("description", TABLE_FQN, "S.T", {"get_table_comment"}, lambda s, i: s.get_table_description("S", "T", i), None),
    (
        "view definition",
        TABLE_FQN,
        "S.T",
        {"get_view_definition"},
        lambda s, i: s.get_schema_definition(TableType.View, "T", "S", i),
        None,
    ),
    ("data", TABLE_FQN, "S.T", {"probe"}, lambda s, i: s.check_readable("S", "T"), None),
]


def _split(fail):
    inspector_methods = {name for name in fail if name.startswith("get_")}
    return _Connection(fail - inspector_methods), _Inspector(inspector_methods)


@pytest.mark.parametrize(
    ("feature", "key", "where", "fail", "read", "empty"),
    READS,
    ids=[f"{case[0]}-{sorted(case[3])[0][:20]}" for case in READS],
)
def test_each_failed_read_is_one_warning_and_the_run_goes_on(feature, key, where, fail, read, empty, caplog):
    connection, inspector = _split(fail)
    source = _source(connection, inspector)
    with caplog.at_level(logging.DEBUG):
        assert read(source, inspector) == empty
    assert source.status.warnings == [{key: f"IRIS-ACCESS: cannot read {feature} of {where}: {FIRST_LINE}"}]
    assert SECRET not in str(source.status.warnings)
    # Nothing is only logged: the status entry is the report.
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


def test_keys_failing_in_all_three_steps_are_one_warning():
    source = _source(_Connection({IRIS_UNIQUE_CONSTRAINTS}), _Inspector({"get_pk_constraint", "get_foreign_keys"}))
    assert source._get_columns_with_constraints("S", "T", source.inspector) == ([], [], [])
    assert len(source.status.warnings) == 1
    assert source.status.warnings[0][TABLE_FQN].startswith("IRIS-ACCESS: cannot read keys of S.T: ")


def test_the_same_unreadable_table_warns_once_per_run():
    source = _source(_Connection({"probe"}))
    source.check_readable("S", "T")
    source.check_readable("S", "T")
    assert len(source.status.warnings) == 1


def test_a_new_run_warns_again():
    for _ in range(2):
        source = _source(_Connection({"probe"}))
        source.check_readable("S", "T")
        assert len(source.status.warnings) == 1


def test_a_schema_message_names_the_schema_alone():
    source = _source(inspector=_Inspector({"get_table_names", "get_view_names"}))
    source.query_table_names_and_types("S")
    source.query_view_names_and_types("S")
    assert source.status.warnings == [
        {SCHEMA_FQN: f"IRIS-ACCESS: cannot read tables of S: {FIRST_LINE}"},
        {SCHEMA_FQN: f"IRIS-ACCESS: cannot read views of S: {FIRST_LINE}"},
    ]


def test_listings_return_the_framework_names_and_types():
    source = _source()
    tables = list(source.query_table_names_and_types("S"))
    views = list(source.query_view_names_and_types("S"))
    assert [(t.name, t.type_) for t in tables] == [("T", TableType.Regular)]
    assert [(v.name, v.type_) for v in views] == [("V", TableType.View)]
    assert source.status.warnings == []


@pytest.mark.parametrize(
    "read",
    [
        lambda s: s.query_table_names_and_types("S"),
        lambda s: s.query_view_names_and_types("S"),
        lambda s: s.check_readable("S", "T"),
    ],
    ids=["tables", "views", "data"],
)
def test_a_non_database_error_is_a_bug_and_propagates(read):
    error = ValueError("bug")
    source = _source(
        _Connection({"probe"}, error=error), _Inspector({"get_table_names", "get_view_names"}, error=error)
    )
    with pytest.raises(ValueError, match="bug"):
        read(source)
    assert source.status.warnings == []


def test_the_probe_quotes_names_with_the_dialect():
    connection = _Connection()
    source = _source(connection)
    source.check_readable("Sql_Name", 'Odd.Na"me')
    assert connection.statements == ['SELECT TOP 0 * FROM "Sql_Name"."Odd.Na""me"']
    assert IRIS_READ_PROBE.format(schema='"S"', table='"T"') == 'SELECT TOP 0 * FROM "S"."T"'


def test_a_readable_table_gives_no_warning_and_closes_its_result():
    connection = _Connection()
    source = _source(connection)
    source.check_readable("S", "T")
    assert source.status.warnings == []
    assert connection.closed_results == 1


def test_every_cataloged_table_and_view_is_probed_after_its_columns(monkeypatch):
    calls = []

    def framework(self, schema_name, table_name, db_name, inspector, table_type=None):
        calls.append(("columns", schema_name, table_name, table_type))
        return ["columns"], ["constraints"], ["foreign keys"]

    monkeypatch.setattr(SqlColumnHandlerMixin, "get_columns_and_constraints", framework)
    connection = _Connection()
    source = _source(connection)
    result = source.get_columns_and_constraints("S", "V", "USER", source.inspector, TableType.View)
    assert result == (["columns"], ["constraints"], ["foreign keys"])
    assert calls == [("columns", "S", "V", TableType.View)]
    assert connection.statements == ['SELECT TOP 0 * FROM "S"."V"']
