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
IRIS lineage module
"""

from metadata.generated.schema.entity.services.connections.database.irisConnection import (
    IrisConnection,
)
from metadata.generated.schema.metadataIngestion.workflow import (
    Source as WorkflowSource,
)
from metadata.ingestion.api.steps import InvalidSourceException
from metadata.ingestion.ometa.ometa_api import OpenMetadata
from metadata.ingestion.source.database.iris.metadata import apply_default_schema_filter
from metadata.ingestion.source.database.lineage_source import LineageSource
from metadata.utils.logger import ingestion_logger

logger = ingestion_logger()


class IrisLineageSource(LineageSource):
    """
    IRIS lineage source: view lineage from the view definitions ingested with the metadata
    """

    @classmethod
    def create(cls, config_dict, metadata: OpenMetadata, pipeline_name: str | None = None):
        """Create class instance"""
        config: WorkflowSource = WorkflowSource.model_validate(config_dict)
        connection: IrisConnection = config.serviceConnection.root.config
        if not isinstance(connection, IrisConnection):
            raise InvalidSourceException(f"Expected IrisConnection, but got {connection}")
        source = cls(config, metadata)
        apply_default_schema_filter(source)
        return source
