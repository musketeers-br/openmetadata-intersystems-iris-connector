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
Iris source module
"""

from collections.abc import Iterable
from typing import cast

from metadata.generated.schema.entity.services.connections.database.irisConnection import (
    IrisConnection,
)
from metadata.generated.schema.metadataIngestion.workflow import (
    Source as WorkflowSource,
)
from metadata.ingestion.api.steps import InvalidSourceException
from metadata.ingestion.ometa.ometa_api import OpenMetadata
from metadata.ingestion.source.database.common_db_source import CommonDbSourceService


class IrisSource(CommonDbSourceService):
    @classmethod
    def create(cls, config_dict, metadata: OpenMetadata, pipeline_name: str | None = None):
        config: WorkflowSource = WorkflowSource.model_validate(config_dict)
        connection = cast("IrisConnection", config.serviceConnection.root.config)
        if not isinstance(connection, IrisConnection):
            raise InvalidSourceException(f"Expected IrisConnection, but got {connection}")
        return cls(config, metadata)

    def get_database_names(self) -> Iterable[str]:
        # One service connects to one Namespace, which is the Database (ADR-0004).
        # Do not call set_inspector(): it writes service_connection.database, which this model lacks.
        yield self.service_connection.namespace

    # --- 002: catalog ---

    # --- 004: dictionary / VECTOR enrichment ---
