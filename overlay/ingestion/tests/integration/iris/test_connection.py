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
Test connection against a real IRIS. Needs only an IRIS container (no OpenMetadata server).

Environment:
  IRIS_HOST (default 127.0.0.1), IRIS_PORT (default 1972), IRIS_NAMESPACE (default USER),
  IRIS_LOGIN: admin | reader | reader_dict (default reader)

spec 001's conftest replaces this ad-hoc environment reading when it lands.
"""

import json
import os
from pathlib import Path

import pytest

from metadata.generated.schema.entity.services.connections.database.common.basicAuth import (
    BasicAuth,
)
from metadata.generated.schema.entity.services.connections.database.irisConnection import (
    IrisConnection as IrisConnectionConfig,
)
from metadata.generated.schema.entity.services.connections.testConnectionDefinition import (
    TestConnectionDefinition,
)
from metadata.generated.schema.entity.services.connections.testConnectionResult import (
    StatusType,
)
from metadata.ingestion.source.database.iris.connection import IrisConnection

pytestmark = pytest.mark.iris

LOGINS = {
    "admin": ("_SYSTEM", "SYS", True),
    "reader": ("omd_reader", "Reader123", False),
    "reader_dict": ("omd_reader_dict", "Reader123", True),
}
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


def _login() -> str:
    return os.environ.get("IRIS_LOGIN", "reader")


def _connection(login=None, **overrides) -> IrisConnection:
    username, password, _ = LOGINS[login or _login()]
    values = {
        "username": username,
        "authType": BasicAuth(password=password),
        "hostPort": f"{os.environ.get('IRIS_HOST', '127.0.0.1')}:{os.environ.get('IRIS_PORT', '1972')}",
        "namespace": os.environ.get("IRIS_NAMESPACE", "USER"),
    }
    values.update(overrides)
    return IrisConnection(IrisConnectionConfig(**values))


def _run(connection: IrisConnection):
    return connection.test_connection(_MetadataStub(), timeout_seconds=60)


def _steps(result):
    return {step.name: step for step in result.steps}


def test_steps_follow_the_contract_table():
    login = _login()
    _, _, dictionary_readable = LOGINS[login]
    steps = _steps(_run(_connection()))

    assert list(steps) == STEPS
    for name in STEPS[:4]:
        assert steps[name].passed, f"{login}: {name} failed: {steps[name].errorLog}"
    assert steps["GetClassDictionary"].passed is (login != "reader"), login
    assert steps["GetClassDictionary"].mandatory is False
    if login == "reader":
        assert "GRANT SELECT ON %Dictionary.PropertyDefinition" in steps["GetClassDictionary"].message
    assert dictionary_readable is (login != "reader")


def test_overall_result_has_no_mandatory_failure():
    result = _run(_connection())
    assert not [step for step in result.steps if step.mandatory and not step.passed]


def test_wrong_password_fails_on_connect_only():
    steps = _steps(_run(_connection(authType=BasicAuth(password="definitely-wrong"))))
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
def test_wrong_host_port_or_namespace_fails_on_connect(override):
    steps = _steps(_run(_connection(**override)))
    assert list(steps) == ["CheckAccess"]
    assert steps["CheckAccess"].passed is False
    assert "Failed to connect to IRIS" in steps["CheckAccess"].message


def test_credentials_never_reach_step_output():
    login = _login()
    _, password, _ = LOGINS[login]
    result = _run(_connection())
    assert password not in result.model_dump_json()
    assert result.status in (StatusType.Running, StatusType.Successful)
