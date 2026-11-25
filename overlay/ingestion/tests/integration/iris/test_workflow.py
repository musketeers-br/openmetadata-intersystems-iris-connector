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
A YAML-style workflow with the same fields as the form creates the service and the Database named after
the Namespace. Needs an OpenMetadata server built from the overlay (make om-image), because a stock server
rejects the Iris service type, plus an IRIS container.

Environment: OM_HOST_PORT (e.g. http://localhost:8585/api), OM_JWT, and the IRIS_* variables of
test_connection.py (login `admin` is used).

Ingesting schemas and tables belongs to spec 002: the schema filter below matches nothing, so this test
only asserts the service and the Database.
"""
import logging
import os

import pytest

from metadata.generated.schema.entity.data.database import Database
from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
    AuthProvider,
    OpenMetadataConnection,
)
from metadata.generated.schema.entity.services.databaseService import DatabaseService
from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
    OpenMetadataJWTClientConfig,
)
from metadata.ingestion.ometa.ometa_api import OpenMetadata
from metadata.workflow.metadata import MetadataWorkflow

pytestmark = pytest.mark.iris

SERVICE_NAME = "iris_test_000"
USERNAME, PASSWORD = "_SYSTEM", "SYS"


@pytest.fixture(scope="module")
def om_client():
    host_port, token = os.environ.get("OM_HOST_PORT"), os.environ.get("OM_JWT")
    if not (host_port and token):
        pytest.skip("OM_HOST_PORT and OM_JWT are not set: needs a server built from the overlay (make om-image)")
    client = OpenMetadata(
        OpenMetadataConnection(
            hostPort=host_port,
            authProvider=AuthProvider.openmetadata,
            securityConfig=OpenMetadataJWTClientConfig(jwtToken=token),
        )
    )
    yield client
    service = client.get_by_name(DatabaseService, SERVICE_NAME)
    if service:
        client.delete(DatabaseService, service.id.root, recursive=True, hard_delete=True)


def _config(host_port: str, token: str) -> dict:
    return {
        "source": {
            "type": "iris",
            "serviceName": SERVICE_NAME,
            "serviceConnection": {
                "config": {
                    "type": "Iris",
                    "hostPort": f"{os.environ.get('IRIS_HOST', '127.0.0.1')}:{os.environ.get('IRIS_PORT', '1972')}",
                    "username": USERNAME,
                    "authType": {"password": PASSWORD},
                    "namespace": os.environ.get("IRIS_NAMESPACE", "USER"),
                }
            },
            "sourceConfig": {
                "config": {
                    "type": "DatabaseMetadata",
                    "includeViews": True,
                    "schemaFilterPattern": {"includes": ["^NoSuchSchemaHere$"]},
                }
            },
        },
        "sink": {"type": "metadata-rest", "config": {}},
        "workflowConfig": {
            "openMetadataServerConfig": {
                "hostPort": host_port,
                "authProvider": "openmetadata",
                "securityConfig": {"jwtToken": token},
            }
        },
    }


def test_workflow_creates_service_and_database_named_after_the_namespace(om_client, caplog):
    caplog.set_level(logging.DEBUG)
    namespace = os.environ.get("IRIS_NAMESPACE", "USER")
    workflow = MetadataWorkflow.create(_config(os.environ["OM_HOST_PORT"], os.environ["OM_JWT"]))
    workflow.execute()
    workflow.raise_from_status()
    workflow.stop()

    service = om_client.get_by_name(DatabaseService, SERVICE_NAME)
    assert service is not None
    assert service.serviceType.value == "Iris"
    database = om_client.get_by_name(Database, f"{SERVICE_NAME}.{namespace}")
    assert database is not None
    assert database.name.root == namespace
    assert f":{PASSWORD}@" not in caplog.text
    assert f"password={PASSWORD}" not in caplog.text
    stored = service.connection.config.authType.password.get_secret_value()
    assert stored != PASSWORD, "the server must return the password masked"
