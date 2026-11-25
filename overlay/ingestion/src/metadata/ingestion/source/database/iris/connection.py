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
Source connection handler
"""

import re
import threading
from functools import partial
from urllib.parse import quote_plus

from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine

from metadata.generated.schema.entity.automations.workflow import (
    Workflow as AutomationWorkflow,
)
from metadata.generated.schema.entity.services.connections.database.irisConnection import (
    IrisConnection as IrisConnectionConfig,
)
from metadata.generated.schema.entity.services.connections.testConnectionResult import (
    TestConnectionResult,
)
from metadata.generated.schema.type.filterPattern import FilterPattern
from metadata.ingestion.connections.builders import (
    create_generic_db_connection,
    get_connection_args_common,
    get_connection_options_dict,
    get_password_secret,
)
from metadata.ingestion.connections.connection import BaseConnection
from metadata.ingestion.connections.test_connections import (
    execute_inspector_func,
    test_connection_engine_step,
    test_connection_steps,
    test_query,
)
from metadata.ingestion.ometa.ometa_api import OpenMetadata
from metadata.ingestion.source.connections_utils import kill_active_connections
from metadata.ingestion.source.database.iris.queries import (
    IRIS_CLASS_DICTIONARY_PROBE,
    IRIS_ZVERSION,
)
from metadata.utils.constants import THREE_MIN
from metadata.utils.filters import filter_by_schema
from metadata.utils.importer import MissingPluginException

# "IRIS for UNIX (...) 2026.1 (Build 233U) ..." or "... 2025.3.0L (Build 226U) ..."
_ZVERSION_RE = re.compile(r"\b(\d{4})\.(\d+)(?:\.(\d+))?[A-Za-z]*\s*\(Build")
_PRESET_LOCK = threading.Lock()


def get_connection_url(connection: IrisConnectionConfig) -> str:
    """
    iris://<user>:<password>@<host:port>/<namespace>[?options]

    The common builder is not used: it would put `databaseSchema` in the path, and the
    dialect reads the path as the Namespace. The Namespace is not URL-quoted because
    SQLAlchemy does not unquote the database part (`%SYS` must stay `%SYS`).
    """
    url = f"{connection.scheme.value}://"
    if connection.username:
        password = get_password_secret(connection).get_secret_value()
        url += f"{quote_plus(connection.username)}:{quote_plus(password)}@"
    url += f"{connection.hostPort}/{connection.namespace}"
    options = get_connection_options_dict(connection)
    if options:
        url += "?" + "&".join(f"{key}={quote_plus(value)}" for key, value in options.items() if value)
    return url


def preset_dialect_state(dialect, connect_args, connect_kwargs) -> None:
    """
    ADR-0015 (GAP-004, GAP-005): set two state attributes the official dialect already defines, so a
    login with only SELECT can connect and reflect. No SQL is rewritten and nothing is patched.

    - server_version_info: read with plain SQL, because the dialect's own read uses the Native API
      and needs the %Native_ClassExecution resource.
    - _dictionary_access: from a real read of %Dictionary.PropertyDefinition, because the dialect's
      %CHECKPRIV probe answers "yes" for every login.

    Runs before the first pooled connection, with the connect arguments the pool is about to use.
    Remove when the dialect fixes both defects.
    """
    if dialect.server_version_info is not None and dialect._dictionary_access is not None:
        return
    with _PRESET_LOCK:
        connection = dialect.dbapi.connect(*connect_args, **connect_kwargs)
        try:
            cursor = connection.cursor()
            if dialect.server_version_info is None:
                cursor.execute(IRIS_ZVERSION)
                version = str(cursor.fetchone()[0])
                match = _ZVERSION_RE.search(version)
                if not match:
                    raise RuntimeError(f"Unrecognized IRIS version string {version!r}")
                dialect.server_version_info = (int(match[1]), int(match[2]), int(match[3] or 0))
            if dialect._dictionary_access is None:
                try:
                    cursor.execute(IRIS_CLASS_DICTIONARY_PROBE)
                    cursor.fetchone()
                    dialect._dictionary_access = True
                except dialect.dbapi.Error:
                    dialect._dictionary_access = False
        finally:
            connection.close()


def _schemas_in_scope(engine: Engine, schema_filter: FilterPattern | None) -> list:
    return [schema for schema in inspect(engine).get_schema_names() if not filter_by_schema(schema_filter, schema)]


def _check_tables(engine: Engine, schema_filter: FilterPattern | None) -> None:
    inspector = inspect(engine)
    for schema in _schemas_in_scope(engine, schema_filter):
        if inspector.get_table_names(schema):
            return
    raise RuntimeError("No table is visible in any schema that passes the schema filter pattern")


def _check_views(engine: Engine, schema_filter: FilterPattern | None) -> None:
    schemas = _schemas_in_scope(engine, schema_filter)
    if not schemas:
        raise RuntimeError("No schema passes the schema filter pattern")
    inspect(engine).get_view_names(schemas[0])


class IrisConnection(BaseConnection[IrisConnectionConfig, Engine]):
    def _get_client(self) -> Engine:
        try:
            import sqlalchemy_intersystems_iris  # noqa: F401  pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise MissingPluginException("iris") from exc

        engine = create_generic_db_connection(
            connection=self.service_connection,
            get_connection_url_fn=get_connection_url,
            get_connection_args_fn=get_connection_args_common,
        )
        event.listen(
            engine,
            "do_connect",
            lambda dialect, _record, args, kwargs: preset_dialect_state(dialect, args, kwargs),
        )
        return engine

    def test_connection(
        self,
        metadata: OpenMetadata,
        automation_workflow: AutomationWorkflow | None = None,
        timeout_seconds: int | None = THREE_MIN,
    ) -> TestConnectionResult:
        engine = self.client
        schema_filter = self.service_connection.schemaFilterPattern
        test_fn = {
            "CheckAccess": partial(test_connection_engine_step, engine),
            "GetSchemas": partial(execute_inspector_func, engine, "get_schema_names"),
            "GetTables": partial(_check_tables, engine, schema_filter),
            "GetViews": partial(_check_views, engine, schema_filter),
            "GetClassDictionary": partial(test_query, engine, IRIS_CLASS_DICTIONARY_PROBE),
        }
        result = test_connection_steps(
            metadata=metadata,
            test_fn=test_fn,
            service_type=self.service_connection.type.value,
            automation_workflow=automation_workflow,
            timeout_seconds=timeout_seconds,
        )
        kill_active_connections(engine)
        return result
