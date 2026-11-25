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
from metadata.ingestion.api.steps import InvalidSourceException
from metadata.ingestion.source.database.iris.connection import (
    IrisConnection,
    get_connection_url,
    preset_dialect_state,
)
from metadata.ingestion.source.database.iris.metadata import IrisSource
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
