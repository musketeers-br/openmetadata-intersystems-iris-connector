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
Test connection against a real IRIS. Needs only an IRIS instance with the shared fixtures (no
OpenMetadata server). The cell's login, its credentials and its dictionary grant come from the
conftest (`iris_cell`, `iris_service_connection`).
"""

import json
from pathlib import Path

import pytest

from metadata.generated.schema.entity.services.connections.database.common.basicAuth import (
    BasicAuth,
)
from metadata.generated.schema.entity.services.connections.testConnectionDefinition import (
    TestConnectionDefinition,
)
from metadata.generated.schema.entity.services.connections.testConnectionResult import (
    StatusType,
)
from metadata.ingestion.source.database.iris.connection import IrisConnection

pytestmark = pytest.mark.iris

STEPS = ["CheckAccess", "GetSchemas", "GetTables", "GetViews", "GetClassDictionary"]
DEFINITION = (
    Path(__file__).resolve().parents[4]
    / "openmetadata-service/src/main/resources/json/data/testConnections/database/iris.json"
)


class _MetadataStub:
    """Test connection reads its definition from the server; the definition file is the same one."""

    def get_by_name(self, entity, fqn):
        assert fqn == "Iris.testConnectionDefinition"
        return TestConnectionDefinition.model_validate(json.loads(DEFINITION.read_text()))


def _run(config, **overrides):
    connection = IrisConnection(config.model_copy(update=overrides) if overrides else config)
    return connection.test_connection(_MetadataStub(), timeout_seconds=60)


def _steps(result):
    return {step.name: step for step in result.steps}


def test_steps_follow_the_contract_table(iris_cell, iris_service_connection):
    steps = _steps(_run(iris_service_connection))

    assert list(steps) == STEPS
    for name in STEPS[:4]:
        assert steps[name].passed, f"{iris_cell.name}: {name} failed: {steps[name].errorLog}"
    assert steps["GetClassDictionary"].passed is iris_cell.has_dict_grant, iris_cell.name
    assert steps["GetClassDictionary"].mandatory is False
    if not iris_cell.has_dict_grant:
        assert "GRANT SELECT ON %Dictionary.PropertyDefinition" in steps["GetClassDictionary"].message


def test_overall_result_has_no_mandatory_failure(iris_service_connection):
    result = _run(iris_service_connection)
    assert not [step for step in result.steps if step.mandatory and not step.passed]


def test_wrong_password_fails_on_connect_only(iris_service_connection):
    steps = _steps(_run(iris_service_connection, authType=BasicAuth(password="definitely-wrong")))
    assert list(steps) == ["CheckAccess"]
    assert steps["CheckAccess"].passed is False
    assert "Check host, superserver port, Namespace, username and password" in steps["CheckAccess"].message
    assert "definitely-wrong" not in str(steps["CheckAccess"].errorLog)


@pytest.mark.parametrize(
    "override",
    [
        {"hostPort": "127.0.0.1:1"},
        {"hostPort": "no-such-host.invalid:1972"},
        {"namespace": "NO_SUCH_NAMESPACE"},
    ],
    ids=["wrong-port", "wrong-host", "wrong-namespace"],
)
def test_wrong_host_port_or_namespace_fails_on_connect(iris_service_connection, override):
    steps = _steps(_run(iris_service_connection, **override))
    assert list(steps) == ["CheckAccess"]
    assert steps["CheckAccess"].passed is False
    assert "Failed to connect to IRIS" in steps["CheckAccess"].message


def test_credentials_never_reach_step_output(iris_cell, iris_service_connection):
    result = _run(iris_service_connection)
    assert iris_cell.password not in result.model_dump_json()
    assert result.status in (StatusType.Running, StatusType.Successful)
