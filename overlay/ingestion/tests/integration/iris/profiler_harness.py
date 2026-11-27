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
Spec 006: run OpenMetadata's profiler and data-quality tests in process against the IRIS fixtures, with no
OpenMetadata server, as OpenMetadata's own unit tests do (research R9).

The sampler, profiler and test-suite classes are resolved through the IRIS ServiceSpec, so whatever the connector
registers is what runs. A stub client answers the database and schema names and the built-in test definitions,
read from the OpenMetadata tree. Every profiler run uses threadCount 5: IRIS Community runs out of licenses under
the default thread count (SPIKE-04).
"""

import json
import logging
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import event
from sqlalchemy.engine import Engine

from metadata.data_quality.builders.validator_builder import ValidatorBuilder
from metadata.generated.schema.entity.data.table import Column, ColumnName, DataType, Table
from metadata.generated.schema.entity.services.databaseService import DatabaseServiceType
from metadata.generated.schema.entity.services.serviceType import ServiceType
from metadata.generated.schema.tests.testCase import TestCase, TestCaseParameterValue
from metadata.generated.schema.tests.testDefinition import TestDefinition
from metadata.generated.schema.type.entityReference import EntityReference
from metadata.ingestion.api.status import Status
from metadata.profiler.metrics.registry import Metrics
from metadata.profiler.processor.core import Profiler
from metadata.profiler.processor.default import DefaultProfiler
from metadata.sampler.models import SampleConfig
from metadata.sampler.sampler_config import DatabaseSamplerConfig
from metadata.utils.logger import StatusWarningHandler, ingestion_logger
from metadata.utils.service_spec.service_spec import (
    import_profiler_class,
    import_sampler_class,
    import_test_suite_class,
)

SOURCE_TYPE = "iris"
THREAD_COUNT = 5
SERVICE = "iris_test"
NAMESPACE = "USER"
DEFINITIONS = Path(__file__).resolve().parents[4] / "openmetadata-service/src/main/resources/json/data/tests"
DEFINITION_FILE = {
    "columnValuesMissingCount": "columnValuesMissingCountToBeEqual",
    "columnValueLengthsToBeBetween": "columnValuesLengthsToBeBetween",
}

# The fixture tables as spec 003 catalogs them. Restricted.ColumnGrant is cataloged with Id only for the readers
# (spec 005: a column-level grant hides the other columns).
TABLES: dict[str, list[tuple[str, DataType]]] = {
    "Clinic.Patient": [
        ("PatientId", DataType.INT),
        ("FullName", DataType.VARCHAR),
        ("BirthDate", DataType.DATE),
        ("Weight", DataType.NUMERIC),
    ],
    "Clinic.Encounter": [
        ("EncounterId", DataType.INT),
        ("PatientId", DataType.INT),
        ("StartedAt", DataType.TIMESTAMP),
        ("Notes", DataType.TEXT),
        ("Active", DataType.BOOLEAN),
    ],
    "Billing.Patient": [("Code", DataType.VARCHAR), ("Balance", DataType.DOUBLE)],
    "Types.AllTypes": [
        ("Id", DataType.INT),
        ("BigIntCol", DataType.BIGINT),
        ("BitCol", DataType.BOOLEAN),
        ("DateCol", DataType.DATE),
        ("DoubleCol", DataType.DOUBLE),
        ("GuidCol", DataType.UUID),
        ("LongVarBinaryCol", DataType.BLOB),
        ("LongVarCharCol", DataType.TEXT),
        ("NumericCol", DataType.NUMERIC),
        ("SmallIntCol", DataType.SMALLINT),
        ("TimeCol", DataType.TIME),
        ("TimestampCol", DataType.TIMESTAMP),
        ("TinyIntCol", DataType.TINYINT),
        ("VarBinaryCol", DataType.VARBINARY),
        ("VarCharCol", DataType.VARCHAR),
        ("VarChar1Col", DataType.VARCHAR),
    ],
    "Restricted.Secret": [("Id", DataType.INT), ("Code", DataType.VARCHAR), ("Note", DataType.VARCHAR)],
    "Restricted.ColumnGrant": [("Id", DataType.INT)],
}
# The tables a login sees: Restricted.Hidden is invisible to the readers and empty of interest to the admin.
PROFILED = ("Clinic.Patient", "Clinic.Encounter", "Billing.Patient", "Types.AllTypes")
RESTRICTED = ("Restricted.Secret", "Restricted.ColumnGrant")


def table_fqn(qualified: str) -> str:
    return f"{SERVICE}.{NAMESPACE}.{qualified}"


class StubClient:
    """Stands in for the OpenMetadata client: database and schema names by id, and test definitions."""

    def __init__(self):
        self.names: dict[str, str] = {}
        self.definitions: dict[str, TestDefinition] = {}

    def get_by_id(self, entity, entity_id, **_kw):
        key = str(getattr(entity_id, "root", entity_id))
        if entity is TestDefinition:
            return self.definitions[key]
        return SimpleNamespace(name=SimpleNamespace(root=self.names[key]))

    def get_by_name(self, entity, fqn, **_kw):
        fqn = getattr(fqn, "root", fqn)
        return next(d for d in self.definitions.values() if d.fullyQualifiedName.root == fqn)

    def definition(self, name: str) -> TestDefinition:
        for known in self.definitions.values():
            if known.name.root == name:
                return known
        raw = json.loads((DEFINITIONS / f"{DEFINITION_FILE.get(name, name)}.json").read_text())
        raw["id"] = str(uuid.uuid4())
        raw.setdefault("fullyQualifiedName", raw["name"])
        test_definition = TestDefinition.model_validate(raw)
        self.definitions[str(test_definition.id.root)] = test_definition
        return test_definition

    def table(self, qualified: str) -> Table:
        schema, name = qualified.split(".")
        schema_id, db_id = uuid.uuid4(), uuid.uuid4()
        self.names[str(schema_id)], self.names[str(db_id)] = schema, NAMESPACE
        return Table(
            id=uuid.uuid4(),
            name=name,
            fullyQualifiedName=table_fqn(qualified),
            serviceType=DatabaseServiceType.Iris,
            database=EntityReference(id=db_id, type="database"),
            databaseSchema=EntityReference(id=schema_id, type="databaseSchema"),
            columns=[
                Column(name=ColumnName(col), dataType=dt, arrayDataType=(rest[0] if rest else None))
                for col, dt, *rest in TABLES[qualified]
            ],
        )


def sampler_class():
    return import_sampler_class(ServiceType.Database, source_type=SOURCE_TYPE)


def sampler(connection, client: StubClient, table: Table, sample_config: SampleConfig | None = None):
    return sampler_class()(
        service_connection_config=connection,
        ometa_client=client,
        entity=table,
        config=DatabaseSamplerConfig(sample_config=sample_config or SampleConfig(randomizedSample=False)),
    )


def profiler_interface(connection, client: StubClient, qualified: str, sample_config: SampleConfig | None = None):
    table = client.table(qualified)
    profiler_class = import_profiler_class(ServiceType.Database, source_type=SOURCE_TYPE)
    return profiler_class(connection, client, table, None, sampler(connection, client, table, sample_config),
                          THREAD_COUNT, 600)


def profile(connection, client: StubClient, qualified: str, sample_config: SampleConfig | None = None):
    """The default profiler on one table. Returns (table results, column results, profiler-interface failures)."""
    interface = profiler_interface(connection, client, qualified, sample_config)
    try:
        profiler = DefaultProfiler(profiler_interface=interface, metrics_registry=Metrics)
        profiler.compute_metrics()
        return dict(profiler._table_results or {}), dict(profiler._column_results or {}), list(
            interface.status.failures
        )
    finally:
        release(interface)


def profile_metrics(connection, client: StubClient, qualified: str, names: tuple[str, ...],
                    sample_config: SampleConfig | None = None):
    """Chosen metrics (with the inputs composed metrics need) on one table. Returns the column results."""
    needs = {"duplicateCount": ("valuesCount", "distinctCount")}
    wanted = list(dict.fromkeys(n for name in names for n in (name, *needs.get(name, ()))))
    interface = profiler_interface(connection, client, qualified, sample_config)
    try:
        profiler = Profiler(*(Metrics.get(name) for name in wanted), profiler_interface=interface)
        profiler.compute_metrics()
        return dict(profiler._column_results or {})
    finally:
        release(interface)


def run_test_case(connection, client: StubClient, qualified: str, column: str | None, definition: str,
                  params: dict, sample_config: SampleConfig | None = None):
    """One built-in test through the connector's test-suite class. Returns (status, result text)."""
    table = client.table(qualified)
    test_definition = client.definition(definition)
    link = f"<#E::table::{table.fullyQualifiedName.root}" + (f"::columns::{column}>" if column else ">")
    case = TestCase(
        id=uuid.uuid4(),
        name=f"{definition}_{column or 'table'}",
        fullyQualifiedName=f"{table.fullyQualifiedName.root}.{definition}",
        entityLink=link,
        testDefinition=EntityReference(
            id=test_definition.id, type="testDefinition", fullyQualifiedName=test_definition.fullyQualifiedName.root
        ),
        testSuite=EntityReference(id=uuid.uuid4(), type="testSuite"),
        parameterValues=[TestCaseParameterValue(name=k, value=v) for k, v in params.items()],
    )
    suite_class = import_test_suite_class(ServiceType.Database, source_type=SOURCE_TYPE)
    the_sampler = sampler(connection, client, table, sample_config)
    suite = suite_class(connection, client, the_sampler, table, validator_builder=ValidatorBuilder)
    try:
        response = suite.run_test_case(case)
    finally:
        release(suite, the_sampler)
    result = response.testCaseResult
    return result.testCaseStatus.value, result.result or ""


def release(*holders) -> None:
    """IRIS Community allows few connections: close every session and dispose every engine a run opened."""
    for holder in holders:
        inner = getattr(holder, "sampler", None)
        if inner is not None:
            release(inner)
        session = getattr(holder, "session", None)
        if session is not None and hasattr(session, "get_bind"):
            bind = session.get_bind()
            session.close()
            bind.dispose()
        engine = getattr(holder, "connection", None)
        if engine is not None and hasattr(engine, "dispose"):
            engine.dispose()


@contextmanager
def step_status():
    """A Status fed by the framework's StatusWarningHandler on ingestion_logger(), as Step.run() attaches it."""
    status = Status()
    handler = StatusWarningHandler(status)
    logger = ingestion_logger()
    logger.addHandler(handler)
    try:
        yield status
    finally:
        logger.removeHandler(handler)


def warnings_with(status: Status, prefix: str) -> list[str]:
    return [reason for entry in status.warnings for reason in entry.values() if str(reason).startswith(prefix)]


@contextmanager
def count_statements():
    """Collect every statement any engine runs (each sampler builds its own), to prove that no metric query ran."""
    statements: list[str] = []

    def before(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", before)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", before)


logging.getLogger("metadata").setLevel(logging.WARNING)
