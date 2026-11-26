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
Unit tests for the IRIS connector foundation. No IRIS and no OpenMetadata server needed.
"""

import sys
from importlib import metadata as importlib_metadata
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from metadata.generated.schema.entity.data.table import TableType
from metadata.generated.schema.entity.services.connections.database.common.basicAuth import (
    BasicAuth,
)
from metadata.generated.schema.entity.services.connections.database.irisConnection import (
    IrisConnection as IrisConnectionConfig,
)
from metadata.generated.schema.entity.services.connections.database.mysqlConnection import (
    MysqlConnection,
)
from metadata.generated.schema.metadataIngestion.workflow import (
    Source as WorkflowSource,
)
from metadata.generated.schema.type.filterPattern import FilterPattern
from metadata.ingestion.api.status import Status
from metadata.ingestion.api.steps import InvalidSourceException
from metadata.ingestion.source.database.iris.connection import (
    IrisConnection,
    get_connection_url,
    preset_dialect_state,
)
from metadata.ingestion.source.database.iris.lineage import IrisLineageSource
from metadata.ingestion.source.database.iris.metadata import IrisSource, apply_default_schema_filter
from metadata.ingestion.source.database.iris.queries import IRIS_UNIQUE_CONSTRAINTS
from metadata.ingestion.source.database.iris.service_spec import ServiceSpec
from metadata.utils.filters import filter_by_schema
from metadata.utils.importer import MissingPluginException

PASSWORD = "S3cret!pw"
# Dialect version the ADR-0015 presets were reviewed against. A new dialect release may have fixed
# GAP-004 / GAP-005: re-evaluate preset_dialect_state, then update this constant.
REVIEWED_DIALECT_VERSION = "1.0.2"


def _config(**overrides) -> IrisConnectionConfig:
    values = {
        "username": "omd_reader",
        "authType": BasicAuth(password=PASSWORD),
        "hostPort": "127.0.0.1:1972",
        "namespace": "USER",
    }
    values.update(overrides)
    return IrisConnectionConfig(**values)


class TestConfig:
    def test_parses_from_yaml_like_dict(self):
        source = WorkflowSource.model_validate(
            {
                "type": "iris",
                "serviceName": "iris_test",
                "serviceConnection": {
                    "config": {
                        "type": "Iris",
                        "hostPort": "127.0.0.1:1972",
                        "username": "omd_reader",
                        "authType": {"password": PASSWORD},
                        "namespace": "USER",
                    }
                },
                "sourceConfig": {"config": {"type": "DatabaseMetadata"}},
            }
        )
        config = source.serviceConnection.root.config
        assert isinstance(config, IrisConnectionConfig)
        assert config.namespace == "USER"
        assert config.scheme.value == "iris"

    def test_namespace_is_required(self):
        with pytest.raises(ValidationError, match="namespace"):
            IrisConnectionConfig(
                username="u",
                authType=BasicAuth(password="p"),
                hostPort="127.0.0.1:1972",
            )

    def test_no_database_name_or_schema_fields(self):
        with pytest.raises(ValidationError):
            _config(databaseSchema="Clinic")
        with pytest.raises(ValidationError):
            _config(databaseName="x")

    @pytest.mark.parametrize(
        ("schema", "excluded"),
        [
            ("%SYS", True),
            ("%Dictionary", True),
            ("INFORMATION_SCHEMA", True),
            ("Ens_Util", True),
            ("EnsLib", True),
            ("Clinic", False),
            ("SQLUser", False),
        ],
    )
    def test_system_schemas_excluded_by_default(self, schema, excluded):
        assert filter_by_schema(_config().schemaFilterPattern, schema) is excluded


class TestUrl:
    def test_url_carries_the_namespace_and_no_schema(self):
        url = make_url(get_connection_url(_config(namespace="Clinic")))
        assert url.drivername == "iris"
        assert url.database == "Clinic"
        assert (url.host, url.port, url.username) == ("127.0.0.1", 1972, "omd_reader")
        assert url.password == PASSWORD

    def test_namespace_keeps_case_and_percent(self):
        assert make_url(get_connection_url(_config(namespace="%SYS"))).database == "%SYS"
        assert make_url(get_connection_url(_config(namespace="MixedCase"))).database == "MixedCase"

    def test_password_with_special_characters_round_trips(self):
        url = make_url(get_connection_url(_config(authType=BasicAuth(password="p@ss/w:rd?"))))
        assert url.password == "p@ss/w:rd?"

    def test_no_trailing_question_mark_when_all_options_are_empty(self):
        assert not get_connection_url(_config(connectionOptions={"timeout": ""})).endswith("?")
        assert get_connection_url(_config(connectionOptions={"timeout": "5"})).endswith("?timeout=5")

    def test_password_is_masked_in_the_model(self):
        config = _config()
        assert PASSWORD not in repr(config)
        assert PASSWORD not in str(config)
        assert PASSWORD not in config.model_dump_json()


class TestMissingExtra:
    def test_missing_driver_gives_the_standard_plugin_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "sqlalchemy_intersystems_iris", None)
        with pytest.raises(MissingPluginException, match=r"openmetadata-ingestion\[iris\]"):
            IrisConnection(_config())._get_client()


class TestSource:
    def test_database_is_the_namespace_verbatim(self):
        source = object.__new__(IrisSource)
        source.service_connection = _config(namespace="MixedCase")
        assert list(source.get_database_names()) == ["MixedCase"]

    def test_create_rejects_another_connection_type(self):
        config = {
            "type": "iris",
            "serviceName": "wrong",
            "serviceConnection": {
                "config": MysqlConnection(
                    username="u", authType=BasicAuth(password="p"), hostPort="localhost:3306"
                ).model_dump(mode="json")
            },
            "sourceConfig": {"config": {"type": "DatabaseMetadata"}},
        }
        with pytest.raises(InvalidSourceException):
            IrisSource.create(config, metadata=None)


class _Error(Exception):
    pass


class _FakeDriver:
    """DB-API stand-in: records every statement and answers the two presets queries."""

    Error = _Error

    def __init__(self, zversion, dictionary_readable):
        self.zversion = zversion
        self.dictionary_readable = dictionary_readable
        self.statements = []
        self.connects = []

    def connect(self, *args, **kwargs):
        self.connects.append((args, kwargs))
        return _FakeConnection(self)


class _FakeConnection:
    def __init__(self, driver):
        self.driver = driver
        self.closed = False

    def cursor(self):
        return _FakeCursor(self.driver)

    def close(self):
        self.closed = True


class _FakeCursor:
    def __init__(self, driver):
        self.driver = driver
        self.row = None

    def execute(self, sql):
        self.driver.statements.append(sql)
        if "$ZVERSION" in sql:
            self.row = (self.driver.zversion,)
        elif "%Dictionary.PropertyDefinition" in sql:
            if not self.driver.dictionary_readable:
                raise _Error("SQLCODE -99: Privilege violation")
            self.row = ("Name",)
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self.row


def _dialect(driver):
    return SimpleNamespace(server_version_info=None, _dictionary_access=None, dbapi=driver)


class TestDialectPresets:
    @pytest.mark.parametrize(
        ("zversion", "expected"),
        [
            (
                "IRIS for UNIX (Ubuntu Server LTS for x86-64 Containers) 2026.1 (Build 233U) Tue Mar 17 2026",
                (2026, 1, 0),
            ),
            (
                "IRIS for UNIX (Ubuntu Server LTS for ARM64 Containers) 2026.2.0L (Build 120U) Mon Jun 1 2026",
                (2026, 2, 0),
            ),
            (
                "IRIS for UNIX (Ubuntu Server LTS for x86-64 Containers) 2022.1.2 (Build 574U) Wed Jun 1 2022",
                (2022, 1, 2),
            ),
        ],
    )
    def test_version_is_parsed_from_plain_sql(self, zversion, expected):
        driver = _FakeDriver(zversion, dictionary_readable=True)
        dialect = _dialect(driver)
        preset_dialect_state(dialect, ["x"], {"hostname": "h"})
        assert dialect.server_version_info == expected
        assert driver.connects == [(("x",), {"hostname": "h"})]

    def test_dictionary_access_true_when_readable(self):
        driver = _FakeDriver("IRIS 2026.1 (Build 1U)", dictionary_readable=True)
        dialect = _dialect(driver)
        preset_dialect_state(dialect, [], {})
        assert dialect._dictionary_access is True

    def test_dictionary_access_false_when_not_readable(self):
        driver = _FakeDriver("IRIS 2026.1 (Build 1U)", dictionary_readable=False)
        dialect = _dialect(driver)
        preset_dialect_state(dialect, [], {})
        assert dialect._dictionary_access is False

    def test_runs_once_and_closes_its_connection(self):
        driver = _FakeDriver("IRIS 2026.1 (Build 1U)", dictionary_readable=True)
        dialect = _dialect(driver)
        preset_dialect_state(dialect, [], {})
        preset_dialect_state(dialect, [], {})
        assert len(driver.connects) == 1
        assert len(driver.statements) == 2

    def test_unrecognized_version_is_an_error_not_a_guess(self):
        driver = _FakeDriver("something else", dictionary_readable=True)
        with pytest.raises(RuntimeError, match="Unrecognized IRIS version"):
            preset_dialect_state(_dialect(driver), [], {})

    def test_reviewed_against_the_pinned_dialect(self):
        try:
            installed = importlib_metadata.version("sqlalchemy-intersystems-iris")
        except importlib_metadata.PackageNotFoundError:
            pytest.skip("the iris extra is not installed")
        assert installed == REVIEWED_DIALECT_VERSION, (
            "The dialect changed: check whether GAP-004 / GAP-005 are fixed and drop the presets if so"
        )


# --- 002: catalog ---


def _db_error(message="[SQLCODE: <-99>:<Privilege violation>]\nsecond line with detail"):
    return OperationalError("SELECT 1", {}, Exception(message))


def _source(connection=None):
    source = IrisSource.__new__(IrisSource)
    source.status = Status()
    source.metadata = None
    source.context = SimpleNamespace(
        get=lambda: SimpleNamespace(database_service="iris_test", database="USER"),
        get_current_thread_id=lambda: 1,
    )
    source._connection_map = {1: connection}
    return source


class _Inspector:
    """Stub of the dialect inspector; every method can be told to raise."""

    def __init__(self, columns=None, fail=()):
        self.columns = columns if columns is not None else []
        self.fail = set(fail)
        self.calls = []

    def _call(self, name, table, schema, value):
        self.calls.append((name, schema, table))
        if name in self.fail:
            raise _db_error()
        return value

    def get_columns(self, table, schema, **kw):
        return self._call("get_columns", table, schema, [dict(c) for c in self.columns])

    def get_pk_constraint(self, table, schema):
        return self._call("get_pk_constraint", table, schema, {"constrained_columns": ["Id"]})

    def get_unique_constraints(self, table, schema):
        return self._call("get_unique_constraints", table, schema, [{"column_names": ["Code"]}])

    def get_foreign_keys(self, table, schema):
        return self._call(
            "get_foreign_keys",
            table,
            schema,
            [{"constrained_columns": ["PatientId"], "referred_schema": "Clinic", "referred_table": "Patient"}],
        )

    def get_table_comment(self, table, schema):
        return self._call("get_table_comment", table, schema, {"text": f"about {schema}.{table}"})

    def get_view_definition(self, table, schema):
        return self._call("get_view_definition", table, schema, "  SELECT 1  ")


class _Connection:
    """Answers per statement: `rows` go only to `query` (a queries.py constant); any other statement gets none."""

    def __init__(self, rows=(), fail=False, query=None):
        self.rows, self.fail, self.query, self.params = rows, fail, query, None

    def execute(self, statement, params):
        self.params = params
        if self.fail:
            raise _db_error()
        return iter(self.rows if str(statement) == self.query else ())


class Test002AccessGap:
    def test_database_error_becomes_one_warning_and_the_run_continues(self):
        source = _source()
        after = []
        with source.report_access_gap("iris_test.USER.Restricted.Secret", "columns", "Restricted", "Secret"):
            raise _db_error()
        after.append("continued")
        assert after == ["continued"]
        assert source.status.warnings == [
            {
                "iris_test.USER.Restricted.Secret": (
                    "IRIS-ACCESS: cannot read columns of Restricted.Secret: [SQLCODE: <-99>:<Privilege violation>]"
                )
            }
        ]

    def test_only_the_first_line_of_the_error_is_kept(self):
        source = _source()
        with source.report_access_gap("k", "keys", "S", "T"):
            raise _db_error("first\nsecond\nthird")
        assert source.status.warnings[0]["k"].endswith(": first")

    def test_non_database_errors_propagate(self):
        source = _source()
        with pytest.raises(ValueError), source.report_access_gap("k", "keys", "S", "T"):
            raise ValueError("bug")
        assert source.status.warnings == []

    def test_one_warning_per_object_and_feature(self):
        source = _source()
        for _ in range(3):
            with source.report_access_gap("k", "keys", "S", "T"):
                raise _db_error()
        with source.report_access_gap("k", "columns", "S", "T"):
            raise _db_error()
        assert len(source.status.warnings) == 2

    def test_no_warning_without_an_error(self):
        source = _source()
        with source.report_access_gap("k", "keys", "S", "T"):
            pass
        assert source.status.warnings == []


class Test002Hierarchy:
    def test_same_name_tables_in_two_schemas_keep_their_own_columns_and_descriptions(self):
        source = _source(_Connection())
        clinic = source._get_columns_internal(
            "Clinic", "Patient", "USER", _Inspector([{"name": "PatientId", "comment": "Patient identifier"}])
        )
        billing = source._get_columns_internal("Billing", "Patient", "USER", _Inspector([{"name": "Code"}]))
        assert [c["name"] for c in clinic] == ["PatientId"]
        assert [c["name"] for c in billing] == ["Code"]
        assert clinic[0]["comment"] == "Patient identifier"
        assert "comment" not in billing[0]

    def test_column_names_and_comments_pass_through_unchanged(self):
        source = _source(_Connection())
        columns = source._get_columns_internal(
            "Clinic", "Patient", "USER", _Inspector([{"name": "PatientId", "comment": "id"}])
        )
        assert columns == [{"name": "PatientId", "comment": "id"}]

    def test_unreadable_columns_warn_and_return_nothing(self):
        source = _source(_Connection())
        result = source._get_columns_internal("S", "T", "USER", _Inspector([{"name": "A"}], fail={"get_columns"}))
        assert result == []
        assert list(source.status.warnings[0]) == ["iris_test.USER.S.T"]
        assert "cannot read columns of S.T" in source.status.warnings[0]["iris_test.USER.S.T"]

    def test_table_description_comes_from_the_inspector(self):
        assert _source().get_table_description("Clinic", "Patient", _Inspector()) == "about Clinic.Patient"

    def test_unreadable_table_description_warns_and_returns_none(self):
        source = _source()
        assert source.get_table_description("S", "T", _Inspector(fail={"get_table_comment"})) is None
        assert "cannot read description of S.T" in source.status.warnings[0]["iris_test.USER.S.T"]

    def test_view_definition_only_for_views(self):
        source = _source()
        assert source.get_schema_definition(TableType.Regular, "T", "S", _Inspector()) is None
        assert source.get_schema_definition(TableType.View, "V", "S", _Inspector()) == "SELECT 1"

    def test_unreadable_view_definition_warns(self):
        source = _source()
        inspector = _Inspector(fail={"get_view_definition"})
        assert source.get_schema_definition(TableType.View, "V", "S", inspector) is None
        assert "cannot read view definition of S.V" in source.status.warnings[0]["iris_test.USER.S.V"]


class Test002Keys:
    def test_keys_are_read_for_the_exact_schema_and_table(self):
        inspector = _Inspector()
        connection = _Connection(
            [("UqBillingCode", "Code"), ("UqPair", "A"), ("UqPair", "B")], query=IRIS_UNIQUE_CONSTRAINTS
        )
        pk, unique, foreign = _source(connection)._get_columns_with_constraints("Clinic", "Encounter", inspector)
        assert pk == ["Id"]
        assert unique == [["Code"], ["A", "B"]]
        assert connection.params == {"schema": "Clinic", "table": "Encounter"}
        assert foreign[0]["referred_schema"] == "Clinic"
        assert {(schema, table) for _, schema, table in inspector.calls} == {("Clinic", "Encounter")}

    def test_one_unreadable_kind_of_key_does_not_hide_the_others(self):
        source = _source(_Connection([("Uq", "Code")], query=IRIS_UNIQUE_CONSTRAINTS))
        pk, unique, foreign = source._get_columns_with_constraints("S", "T", _Inspector(fail={"get_foreign_keys"}))
        assert pk == ["Id"] and unique == [["Code"]] and foreign == []
        assert len(source.status.warnings) == 1
        assert "cannot read keys of S.T" in source.status.warnings[0]["iris_test.USER.S.T"]

    def test_unreadable_unique_constraints_warn_once_for_keys(self):
        source = _source(_Connection(fail=True))
        pk, unique, foreign = source._get_columns_with_constraints("S", "T", _Inspector(fail={"get_foreign_keys"}))
        assert pk == ["Id"] and unique == [] and foreign == []
        assert len(source.status.warnings) == 1


class Test002Lineage:
    def test_the_service_spec_registers_the_lineage_source(self):
        assert ServiceSpec.lineage_source_class == f"{IrisLineageSource.__module__}.{IrisLineageSource.__name__}"

    def test_create_accepts_an_iris_connection(self, monkeypatch):
        def init(self, config, metadata):
            self.source_config = config.sourceConfig.config
            self.service_connection = config.serviceConnection.root.config

        monkeypatch.setattr(IrisLineageSource, "__init__", init)
        config = {
            "type": "iris",
            "serviceName": "iris_test",
            "serviceConnection": {"config": _config().model_dump(mode="json")},
            "sourceConfig": {"config": {"type": "DatabaseLineage"}},
        }
        assert isinstance(IrisLineageSource.create(config, metadata=None), IrisLineageSource)

    def test_create_rejects_another_connection(self):
        config = {
            "type": "iris",
            "serviceName": "wrong",
            "serviceConnection": {
                "config": MysqlConnection(
                    username="u", authType=BasicAuth(password="p"), hostPort="localhost:3306"
                ).model_dump(mode="json")
            },
            "sourceConfig": {"config": {"type": "DatabaseLineage"}},
        }
        with pytest.raises(InvalidSourceException):
            IrisLineageSource.create(config, metadata=None)


class Test002IdentityRegression:
    """ADR-0005: every read is keyed on (schema, name); a name alone would merge Clinic.Patient and Billing.Patient."""

    def test_the_unique_constraint_query_joins_and_binds_on_schema_and_table(self):
        query = " ".join(IRIS_UNIQUE_CONSTRAINTS.split())
        assert "k.TABLE_SCHEMA = tc.TABLE_SCHEMA AND k.TABLE_NAME = tc.TABLE_NAME" in query
        assert "k.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA AND k.CONSTRAINT_NAME" in query.replace('"', "")
        assert "tc.TABLE_SCHEMA = :schema AND tc.TABLE_NAME = :table" in query

    def test_each_schema_gets_only_its_own_unique_constraints(self):
        class Connection(_Connection):
            def execute(self, statement, params):
                self.params = params
                rows = {("Billing", "Patient"): [("UqBillingCode", "Code")]}.get(
                    (params["schema"], params["table"]), []
                )
                return iter(rows)

        source = _source(Connection())
        assert source._get_columns_with_constraints("Billing", "Patient", _Inspector())[1] == [["Code"]]
        assert source._get_columns_with_constraints("Clinic", "Patient", _Inspector())[1] == []

    def test_the_inspector_is_asked_for_the_exact_schema_and_table(self):
        inspector = _Inspector([{"name": "Code"}])
        _source(_Connection())._get_columns_internal("Billing", "Patient", "USER", inspector)
        assert inspector.calls == [("get_columns", "Billing", "Patient")]

    def test_mixed_case_names_are_not_normalized(self):
        inspector = _Inspector([{"name": "PatientId"}])
        _source(_Connection())._get_columns_internal("Clinic", "Patient", "USER", inspector)
        assert inspector.calls == [("get_columns", "Clinic", "Patient")]


class Test002DefaultSchemaFilter:
    """ADR-0009: the connection's default applies when the pipeline has no schema pattern; a pipeline pattern wins."""

    @staticmethod
    def _source(pipeline_pattern):
        return SimpleNamespace(
            source_config=SimpleNamespace(schemaFilterPattern=pipeline_pattern),
            service_connection=_config(),
        )

    @staticmethod
    def _kept(source, name):
        return not filter_by_schema(source.source_config.schemaFilterPattern, name)

    @pytest.mark.parametrize("pipeline_pattern", [None, FilterPattern(), FilterPattern(includes=[], excludes=[])])
    def test_an_empty_pipeline_pattern_gets_the_connection_defaults(self, pipeline_pattern):
        source = self._source(pipeline_pattern)
        apply_default_schema_filter(source)
        assert [self._kept(source, n) for n in ("Clinic", "%SYS", "INFORMATION_SCHEMA", "EnsLib", "Ens")] == [
            True,
            False,
            False,
            False,
            False,
        ]

    def test_a_pipeline_pattern_replaces_the_defaults_completely(self):
        pattern = FilterPattern(includes=["^INFORMATION_SCHEMA$"])
        source = self._source(pattern)
        apply_default_schema_filter(source)
        assert source.source_config.schemaFilterPattern is pattern
        assert self._kept(source, "INFORMATION_SCHEMA")
        assert not self._kept(source, "Clinic")

    def test_a_pipeline_exclude_only_pattern_is_not_merged_with_the_defaults(self):
        source = self._source(FilterPattern(excludes=["^Billing$"]))
        apply_default_schema_filter(source)
        assert self._kept(source, "%SYS") and self._kept(source, "Clinic") and not self._kept(source, "Billing")
