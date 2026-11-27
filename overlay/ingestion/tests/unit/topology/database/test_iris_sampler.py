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
Spec 006 (ADR-0016): the IRIS sampler. Unquoted CTE names, no random function, no percentage sampling, and the
warnings recorded once per run through the step's warning handler. No IRIS: the sampler is built offline (no query
runs) and its SQL is compiled with the IRIS dialect.
"""

import hashlib
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.dialects import registry

from metadata.generated.schema.entity.data.table import Column, ColumnName, DataType, Table
from metadata.generated.schema.entity.services.connections.database.common.basicAuth import BasicAuth
from metadata.generated.schema.entity.services.connections.database.irisConnection import IrisConnection
from metadata.generated.schema.entity.services.databaseService import DatabaseServiceType
from metadata.generated.schema.type.basic import ProfileSampleType
from metadata.generated.schema.type.entityReference import EntityReference
from metadata.ingestion.api.status import Status
from metadata.ingestion.source.database.iris.sampler import IrisSampler, IrisSamplingSkipped
from metadata.sampler.models import ProfileSampleConfig, SampleConfig
from metadata.sampler.sampler_config import DatabaseSamplerConfig
from metadata.sampler.sqlalchemy import sampler as sqa_sampler
from metadata.generated.schema.type.samplingConfig import SampleConfigType
from metadata.generated.schema.type.staticSamplingConfig import StaticSamplingConfig
from metadata.utils.logger import StatusWarningHandler, ingestion_logger

IRIS = registry.load("iris")()
REAL_CHECK = IrisSampler._check_readable  # kept before the offline fixture replaces it
RANDOM_FUNCTIONS = ("RAND", "RANDOM", "NEWID", "%", " MOD(", "ORDER BY")


class Client:
    def __init__(self):
        self.names = {}

    def get_by_id(self, entity, entity_id, **_kw):  # pylint: disable=unused-argument
        return SimpleNamespace(name=SimpleNamespace(root=self.names[str(getattr(entity_id, "root", entity_id))]))


def _sampler(client, name="Patient", kind=None, amount=None, randomized=False) -> IrisSampler:
    schema_id, db_id = uuid.uuid4(), uuid.uuid4()
    client.names[str(schema_id)], client.names[str(db_id)] = "Clinic", "USER"
    table = Table(
        id=uuid.uuid4(),
        name=name,
        fullyQualifiedName=f"iris_test.USER.Clinic.{name}",
        serviceType=DatabaseServiceType.Iris,
        database=EntityReference(id=db_id, type="database"),
        databaseSchema=EntityReference(id=schema_id, type="databaseSchema"),
        columns=[Column(name=ColumnName("Id"), dataType=DataType.INT)],
    )
    profile = None
    if kind is not None:
        profile = ProfileSampleConfig(
            sampleConfigType=SampleConfigType.STATIC,
            config=StaticSamplingConfig(profileSampleType=kind, profileSample=amount),
        )
    sample_config = SampleConfig(profileSampleConfig=profile, randomizedSample=randomized)
    return IrisSampler(
        service_connection_config=IrisConnection(
            hostPort="127.0.0.1:1", username="u", authType=BasicAuth(password="p"), namespace="USER"
        ),
        ometa_client=client,
        entity=table,
        config=DatabaseSamplerConfig(sample_config=sample_config),
    )


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No IRIS: an engine that never connects, and no readability check (the access tests are in the integration suite)."""
    monkeypatch.setattr(IrisSampler, "_check_readable", lambda self: None, raising=False)
    monkeypatch.setattr(sqa_sampler, "get_ssl_connection", lambda _config: create_engine("iris://u:p@127.0.0.1:1/USER"))


def _sql(sampler: IrisSampler) -> str:
    dataset = sampler.get_dataset()
    return str(select(dataset).compile(dialect=IRIS, compile_kwargs={"literal_binds": True}))


@pytest.fixture
def status():
    status = Status()
    handler = StatusWarningHandler(status)
    ingestion_logger().addHandler(handler)
    yield status
    ingestion_logger().removeHandler(handler)


def _warnings(status, prefix="IRIS-PROFILER-UNSUPPORTED"):
    return [reason for entry in status.warnings for reason in entry.values() if reason.startswith(prefix)]


@pytest.mark.parametrize("name", ["Patient", "Encounter"])  # MD5 digests start with "0" and "d"
def test_cte_name_is_an_unquoted_identifier(name):
    sampler = _sampler(Client(), name, ProfileSampleType.ROWS, 10)
    assert sampler.get_sampler_table_name()[0].isalpha()
    sql = _sql(sampler)
    cte = f"s{hashlib.md5(name.encode()).hexdigest()}_rnd"
    assert f"WITH {cte} AS" in sql and f'"{cte}"' not in sql


@pytest.mark.parametrize("randomized", [False, True])
def test_row_count_sampling_is_top_n_without_random(randomized, status):
    sql = _sql(_sampler(Client(), kind=ProfileSampleType.ROWS, amount=10, randomized=randomized))
    assert "TOP 10" in sql
    assert not [f for f in RANDOM_FUNCTIONS if f in sql.upper()], sql


def test_randomized_warning_once_per_run(status):
    client = Client()
    for name in ("Patient", "Encounter"):
        _sampler(client, name, ProfileSampleType.ROWS, 10, randomized=True).get_dataset()
    assert len(_warnings(status)) == 1
    assert "randomized sampling is not supported on IRIS" in _warnings(status)[0]
    assert "iris_test.USER.Clinic.Patient" in _warnings(status)[0]
    _sampler(Client(), "Patient", ProfileSampleType.ROWS, 10, randomized=True)  # a new run
    assert len(_warnings(status)) == 2


def test_no_warning_without_sampling_or_randomization(status):
    _sampler(Client(), randomized=True).get_dataset()  # no sample configured: the whole table
    _sampler(Client(), kind=ProfileSampleType.ROWS, amount=10).get_dataset()
    assert _warnings(status) == []


def test_percentage_below_100_skips_the_table(status):
    client = Client()
    for name in ("Patient", "Encounter"):
        with pytest.raises(IrisSamplingSkipped, match=f"iris_test.USER.Clinic.{name} was not profiled"):
            _sampler(client, name, ProfileSampleType.PERCENTAGE, 50)
    assert len(_warnings(status)) == 1
    assert "percentage sampling is not supported on IRIS" in _warnings(status)[0]


def test_percentage_100_is_the_whole_table(status):
    sampler = _sampler(Client(), kind=ProfileSampleType.PERCENTAGE, amount=100)
    assert sampler.get_dataset() is sampler.raw_dataset
    assert _warnings(status) == []
    randomized = _sampler(Client(), kind=ProfileSampleType.PERCENTAGE, amount=100, randomized=True)
    assert randomized.get_dataset() is randomized.raw_dataset
    assert len(_warnings(status)) == 1


def test_skips_are_skippable_for_the_sample_data_step():
    assert IrisSampler.is_skippable_sampling_error(IrisSamplingSkipped("x"))
    assert not IrisSampler.is_skippable_sampling_error(RuntimeError("x"))


# --- spec 006 FR-013a: the readability check ---


class _Session:
    """A session whose execute raises `error` (or succeeds), recording the statements."""

    def __init__(self, error, statements):
        self.error, self.statements = error, statements

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement):
        self.statements.append(str(statement.compile(dialect=IRIS)))
        if self.error is not None:
            raise self.error


def _refused(sqlcode: str) -> DBAPIError:
    return DBAPIError("SELECT", None, Exception(f"<SQL ERROR>; Details: [SQLCODE: <{sqlcode}>:<Refused>]\nline two"))


def test_readable_table_reads_no_rows():
    sampler, statements = _sampler(Client()), []
    sampler.session_factory = lambda: _Session(None, statements)
    REAL_CHECK(sampler)
    assert len(statements) == 1
    assert statements[0].startswith("SELECT TOP 0") or "TOP" in statements[0]
    assert '"Id"' in statements[0] and "*" not in statements[0]


def test_privilege_refusal_skips_the_table_with_one_access_warning(status):
    client, statements = Client(), []
    for _ in range(2):
        sampler = _sampler(client)
        sampler.session_factory = lambda: _Session(_refused("-99"), statements)
        with pytest.raises(IrisSamplingSkipped, match="IRIS-ACCESS: cannot read profile of Clinic.Patient"):
            REAL_CHECK(sampler)
    access = _warnings(status, "IRIS-ACCESS")
    assert access == ["IRIS-ACCESS: cannot read profile of Clinic.Patient: <SQL ERROR>; Details: [SQLCODE: <-99>:<Refused>]"]


def test_other_errors_are_raised():
    sampler = _sampler(Client())
    sampler.session_factory = lambda: _Session(_refused("-400"), [])
    with pytest.raises(DBAPIError):
        REAL_CHECK(sampler)
