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
from contextlib import contextmanager
from typing import cast

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from metadata.generated.schema.entity.data.database import Database
from metadata.generated.schema.entity.data.table import Table, TableType
from metadata.generated.schema.entity.services.connections.database.irisConnection import (
    IrisConnection,
)
from metadata.generated.schema.metadataIngestion.workflow import (
    Source as WorkflowSource,
)
from metadata.ingestion.api.steps import InvalidSourceException
from metadata.ingestion.ometa.ometa_api import OpenMetadata
from metadata.ingestion.source.database.common_db_source import CommonDbSourceService
from metadata.ingestion.source.database.iris.queries import (
    IRIS_COLUMN_TYPES,
    IRIS_UNIQUE_CONSTRAINTS,
)
from metadata.ingestion.source.database.iris.types import (
    ColumnFacts,
    UnknownTypes,
    resolve,
    unknown_type_message,
)
from metadata.utils import fqn as fqn_utils


def apply_default_schema_filter(source) -> None:
    """
    ADR-0009: the framework filters with the pipeline's schemaFilterPattern only. When the pipeline has none,
    use the connection's default (irisConnection.json); a pipeline pattern replaces it completely, never merged.
    """
    pattern = source.source_config.schemaFilterPattern
    if pattern is None or not (pattern.includes or pattern.excludes):
        source.source_config.schemaFilterPattern = source.service_connection.schemaFilterPattern


class IrisSource(CommonDbSourceService):
    @classmethod
    def create(cls, config_dict, metadata: OpenMetadata, pipeline_name: str | None = None):
        config: WorkflowSource = WorkflowSource.model_validate(config_dict)
        connection = cast("IrisConnection", config.serviceConnection.root.config)
        if not isinstance(connection, IrisConnection):
            raise InvalidSourceException(f"Expected IrisConnection, but got {connection}")
        source = cls(config, metadata)
        apply_default_schema_filter(source)
        return source

    def get_database_names(self) -> Iterable[str]:
        # One service connects to one Namespace, which is the Database (ADR-0004).
        # Do not call set_inspector(): it writes service_connection.database, which this model lacks.
        yield self.service_connection.namespace

    # --- 002: catalog ---

    @contextmanager
    def report_access_gap(self, fqn: str, feature: str, schema: str, name: str):
        """Record one IRIS-ACCESS status warning (ADR-0008) for a failed read of one object feature, then go on."""
        try:
            yield
        except SQLAlchemyError as exc:
            reason = str(getattr(exc, "orig", None) or exc).strip()
            first_line = reason.splitlines()[0] if reason else type(exc).__name__
            # Once per object and feature: keys are read in three steps but count as one feature.
            reported = self.__dict__.setdefault("_access_gaps_reported", set())
            if (fqn, feature) not in reported:
                reported.add((fqn, feature))
                self.status.warning(fqn, f"IRIS-ACCESS: cannot read {feature} of {schema}.{name}: {first_line}")

    def _table_fqn(self, schema_name: str, table_name: str) -> str:
        return fqn_utils.build(
            metadata=self.metadata,
            entity_type=Table,
            service_name=self.context.get().database_service,
            database_name=self.context.get().database,
            schema_name=schema_name,
            table_name=table_name,
            skip_es_search=True,
        )

    def get_table_description(self, schema_name: str, table_name: str, inspector) -> str | None:  # type: ignore[override]
        with self.report_access_gap(self._table_fqn(schema_name, table_name), "description", schema_name, table_name):
            return inspector.get_table_comment(table_name, schema_name).get("text")
        return None

    def get_schema_definition(self, table_type, table_name: str, schema_name: str, inspector) -> str | None:
        if table_type != TableType.View:
            return None
        with self.report_access_gap(
            self._table_fqn(schema_name, table_name), "view definition", schema_name, table_name
        ):
            definition = inspector.get_view_definition(table_name, schema_name)
            return str(definition).strip() if definition is not None else None
        return None

    def _get_columns_with_constraints(self, schema_name: str, table_name: str, inspector):  # type: ignore[override]
        # Keys: PK, unique and foreign keys are read one by one so one unreadable kind does not hide the others.
        table_fqn = self._table_fqn(schema_name, table_name)
        pk_columns, unique_columns, foreign_columns = [], [], []
        with self.report_access_gap(table_fqn, "keys", schema_name, table_name):
            pk_columns = inspector.get_pk_constraint(table_name, schema_name).get("constrained_columns") or []
        with self.report_access_gap(table_fqn, "keys", schema_name, table_name):
            by_constraint: dict[str, list[str]] = {}
            for constraint_name, column_name in self.connection.execute(
                text(IRIS_UNIQUE_CONSTRAINTS), {"schema": schema_name, "table": table_name}
            ):
                by_constraint.setdefault(constraint_name, []).append(column_name)
            unique_columns = list(by_constraint.values())
        with self.report_access_gap(table_fqn, "keys", schema_name, table_name):
            foreign_columns = [
                constraint
                for constraint in inspector.get_foreign_keys(table_name, schema_name)
                if constraint.get("constrained_columns")
            ]
        return pk_columns, unique_columns, foreign_columns

    def _get_columns_internal(self, schema_name, table_name, db_name, inspector, table_type=None):
        columns = []
        with self.report_access_gap(self._table_fqn(schema_name, table_name), "columns", schema_name, table_name):
            columns = inspector.get_columns(table_name, schema_name, table_type=table_type, db_name=db_name)
        self.map_column_types(schema_name, table_name, columns)
        return columns

    # --- 003: type map ---

    def map_column_types(self, schema_name: str, table_name: str, columns: list[dict]) -> None:
        """
        ADR-0006: resolve each column's type from its own INFORMATION_SCHEMA.COLUMNS row through the one type table,
        not from the dialect's reflected type (GAP-008). Sets `type` and `system_data_type`; the framework builds the
        column from them. An unmapped type is cataloged as UNKNOWN with one IRIS-UNKNOWN-TYPE warning per type per run.
        """
        if not columns:
            return
        facts: dict[str, ColumnFacts] = {}
        with self.report_access_gap(self._table_fqn(schema_name, table_name), "columns", schema_name, table_name):
            rows = self.connection.execute(text(IRIS_COLUMN_TYPES), {"schema": schema_name, "table": table_name})
            # The catalog may compare names case-insensitively; keep the exact (schema, table) only (Principle III).
            facts = {row[2]: ColumnFacts(*row[3:7]) for row in rows if (row[0], row[1]) == (schema_name, table_name)}
        unknown = self.__dict__.setdefault("_unknown_types", UnknownTypes())
        for column in columns:
            column_facts = facts.get(column["name"])
            if column_facts is None:
                continue
            resolved = resolve(column_facts)
            column["type"] = resolved.sqlalchemy_type
            column["system_data_type"] = resolved.display
            where = f"{schema_name}.{table_name}.{column['name']}"
            if not resolved.known and unknown.first(column_facts.data_type or "", where):
                self.status.warning(self._database_fqn(), unknown_type_message(column_facts.data_type, where))

    def _database_fqn(self) -> str:
        return fqn_utils.build(
            metadata=self.metadata,
            entity_type=Database,
            service_name=self.context.get().database_service,
            database_name=self.context.get().database,
        )

    # --- 004: dictionary / VECTOR enrichment ---
