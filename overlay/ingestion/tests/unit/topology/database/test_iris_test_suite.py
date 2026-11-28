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
Spec 006 (FR-012a): the IRIS test-suite interface aborts the tests IRIS cannot evaluate correctly (regex on any
column; in set, not in set, value lengths, unique and missing count on stream columns) and passes every other test
to the base interface. No IRIS: the base run_test_case is replaced by a recorder.
"""

import uuid

import pytest

from metadata.data_quality.interface.sqlalchemy.sqa_test_suite_interface import SQATestSuiteInterface
from metadata.generated.schema.entity.data.table import Column, ColumnName, DataType, Table
from metadata.generated.schema.entity.services.databaseService import DatabaseServiceType
from metadata.generated.schema.tests.basic import TestCaseResult, TestCaseStatus
from metadata.generated.schema.tests.testCase import TestCase
from metadata.generated.schema.tests.testDefinition import EntityType, TestDefinition
from metadata.generated.schema.type.basic import Timestamp
from metadata.generated.schema.type.entityReference import EntityReference
from metadata.ingestion.api.status import Status
from metadata.ingestion.source.database.iris.test_suite_interface import IrisTestSuiteInterface
from metadata.utils.logger import StatusWarningHandler, ingestion_logger

FQN = "iris_test.USER.Clinic.Encounter"
COLUMNS = {"Notes": DataType.TEXT, "Blob": DataType.BLOB, "Name": DataType.VARCHAR}
STREAM_ONLY = (
    "columnValuesToBeInSet",
    "columnValuesToBeNotInSet",
    "columnValueLengthsToBeBetween",
    "columnValuesToBeUnique",
    "columnValuesMissingCount",
)
ANY_COLUMN = ("columnValuesToMatchRegex", "columnValuesToNotMatchRegex")
NEVER = ("columnValuesToBeNotNull", "columnValuesToBeBetween", "tableRowCountToEqual")


class Client:
    def __init__(self):
        self.definitions = {}

    def get_by_id(self, entity, entity_id, **_kw):  # pylint: disable=unused-argument
        return self.definitions[str(getattr(entity_id, "root", entity_id))]


def _table() -> Table:
    return Table(
        id=uuid.uuid4(),
        name="Encounter",
        fullyQualifiedName=FQN,
        serviceType=DatabaseServiceType.Iris,
        database=EntityReference(id=uuid.uuid4(), type="database"),
        databaseSchema=EntityReference(id=uuid.uuid4(), type="databaseSchema"),
        columns=[Column(name=ColumnName(name), dataType=dt) for name, dt in COLUMNS.items()],
    )


def _case(client: Client, definition: str, column: str | None) -> TestCase:
    entity_type = EntityType.TABLE if definition.startswith("table") else EntityType.COLUMN
    test_definition = TestDefinition(
        id=uuid.uuid4(),
        name=definition,
        fullyQualifiedName=definition,
        description="d",
        entityType=entity_type,
        testPlatforms=["OpenMetadata"],
    )
    client.definitions[str(test_definition.id.root)] = test_definition
    return TestCase(
        id=uuid.uuid4(),
        name=f"{definition}_{column}",
        fullyQualifiedName=f"{FQN}.{definition}",
        entityLink=f"<#E::table::{FQN}" + (f"::columns::{column}>" if column else ">"),
        testDefinition=EntityReference(id=test_definition.id, type="testDefinition", fullyQualifiedName=definition),
        testSuite=EntityReference(id=uuid.uuid4(), type="testSuite"),
    )


class _Validator:
    execution_date = Timestamp(1_795_000_000_000)

    def get_test_case_result_object(self, execution_date, status, result, values, **_kw):
        return TestCaseResult(timestamp=execution_date, testCaseStatus=status, result=result, testResultValue=values)


class _Builder:
    validator = _Validator()


@pytest.fixture
def interface(monkeypatch):
    calls = []
    monkeypatch.setattr(SQATestSuiteInterface, "run_test_case", lambda self, case: calls.append(case) or "base")
    monkeypatch.setattr(IrisTestSuiteInterface, "_get_validator_builder", lambda self, case, entity_type: _Builder())
    suite = IrisTestSuiteInterface.__new__(IrisTestSuiteInterface)
    suite.ometa_client, suite.table_entity = Client(), _table()
    suite.calls = calls
    return suite


@pytest.fixture
def status():
    status = Status()
    handler = StatusWarningHandler(status)
    ingestion_logger().addHandler(handler)
    yield status
    ingestion_logger().removeHandler(handler)


def _aborted(suite, definition, column):
    response = suite.run_test_case(_case(suite.ometa_client, definition, column))
    assert response != "base", f"{definition} on {column} reached the base interface"
    result = response.testCaseResult
    assert result.testCaseStatus == TestCaseStatus.Aborted
    return result.result


@pytest.mark.parametrize("definition", STREAM_ONLY)
@pytest.mark.parametrize("column", ["Notes", "Blob"])
def test_stream_tests_are_aborted(interface, definition, column):
    text = _aborted(interface, definition, column)
    assert text.startswith(f"IRIS-PROFILER-UNSUPPORTED: test {definition} on stream columns is not supported on IRIS")
    assert f"{FQN}.{column}" in text


@pytest.mark.parametrize("definition", ANY_COLUMN)
@pytest.mark.parametrize("column", ["Notes", "Name"])
def test_regex_tests_are_aborted_on_any_column(interface, definition, column):
    assert "no regular-expression predicate" in _aborted(interface, definition, column)


@pytest.mark.parametrize("definition", STREAM_ONLY + NEVER)
def test_other_tests_reach_the_base_interface(interface, definition):
    column = None if definition.startswith("table") else "Name"  # stream-only tests on a VARCHAR column run
    assert interface.run_test_case(_case(interface.ometa_client, definition, column)) == "base"
    assert len(interface.calls) == 1


def test_warning_once_per_test_type_and_run(interface, status):
    for column in ("Notes", "Blob"):
        _aborted(interface, "columnValuesToBeInSet", column)
    _aborted(interface, "columnValuesToMatchRegex", "Name")
    _aborted(interface, "columnValuesToMatchRegex", "Notes")
    warnings = [r for entry in status.warnings for r in entry.values() if r.startswith("IRIS-PROFILER-UNSUPPORTED")]
    assert len(warnings) == 2, warnings
    interface.ometa_client = Client()  # a new run
    _aborted(interface, "columnValuesToBeInSet", "Notes")
    warnings = [r for entry in status.warnings for r in entry.values() if r.startswith("IRIS-PROFILER-UNSUPPORTED")]
    assert len(warnings) == 3
