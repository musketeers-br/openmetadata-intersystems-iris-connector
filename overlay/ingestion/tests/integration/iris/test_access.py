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
Access gaps against a real IRIS (spec 005). The connector lists and reads each schema as the framework does per
table, without an OpenMetadata server, for the cell's login (conftest: `iris_cell`, `iris_engine`). Schema
`Restricted` holds a table the readers may only reference, one they may read one column of, and one they hold no
privilege on (data/seed.py, `EXPECTED["restricted"]`).
"""

from types import SimpleNamespace

import pytest
from tests.integration.iris.data.seed import EXPECTED, READER_SCHEMAS

from metadata.generated.schema.entity.data.table import TableType
from metadata.ingestion.api.status import Status
from metadata.ingestion.source.database.iris.metadata import IrisSource

pytestmark = pytest.mark.iris

SERVICE = "iris_test"


@pytest.fixture
def source(iris_cell, iris_engine, iris_service_connection):
    """A fresh IrisSource per test, so each test is one run with its own warnings."""
    source = IrisSource.__new__(IrisSource)
    source.service_connection = iris_service_connection
    source.engine = iris_engine
    source.status = Status()
    source.metadata = None
    source.source_config = SimpleNamespace(
        includeTables=True, includeViews=True, tableFilterPattern=None, useFqnForFiltering=False
    )
    source._connection_map = {}
    source._inspector_map = {}
    current = SimpleNamespace(database_service=SERVICE, database=iris_cell.namespace, database_schema=None)
    source.context = SimpleNamespace(get=lambda: current, get_current_thread_id=lambda: 1)
    yield source
    source.connection.close()


def _catalog(source, schema, objects):
    """Read each object as the framework does after listing it: columns and keys, then the description."""
    source.context.get().database_schema = schema
    cataloged = {}
    for name, table_type in objects:
        columns, _, _ = source.get_columns_and_constraints(
            schema_name=schema,
            table_name=name,
            db_name=source.context.get().database,
            inspector=source.inspector,
            table_type=table_type,
        )
        source.get_table_description(schema, name, source.inspector)
        cataloged[name] = [column.name.root for column in columns]
    return cataloged


def _access_warnings(source):
    return [(key, reason) for w in source.status.warnings for key, reason in w.items() if "IRIS-ACCESS" in reason]


def test_the_restricted_schema(source, iris_cell):
    source.context.get().database_schema = "Restricted"
    listed = list(source.get_tables_name_and_type())
    cataloged = _catalog(source, "Restricted", listed)
    warnings = _access_warnings(source)
    if iris_cell.is_admin:
        assert sorted(cataloged) == sorted(EXPECTED["restricted"]), iris_cell.name
        assert cataloged["ColumnGrant"] == [c for c, _ in EXPECTED["columns"][("Restricted", "ColumnGrant")]]
        assert warnings == [], f"{iris_cell.name}: {warnings}"
        return
    visible = {table: columns for table, (listed_, columns) in EXPECTED["restricted"].items() if listed_}
    assert cataloged == visible, iris_cell.name
    # One `data` warning per visible table, keyed on its FQN, and nothing else; Hidden is never mentioned.
    assert sorted(key for key, _ in warnings) == sorted(
        f"{SERVICE}.{iris_cell.namespace}.Restricted.{table}" for table in visible
    ), f"{iris_cell.name}: {warnings}"
    for key, reason in warnings:
        table = key.rsplit(".", 1)[1]
        assert reason.startswith(f"IRIS-ACCESS: cannot read data of Restricted.{table}: "), reason
        assert "\n" not in reason and iris_cell.password not in reason
    assert not [w for w in source.status.warnings if "Hidden" in str(w)], iris_cell.name


def test_the_readable_fixtures_give_no_access_warning(source, iris_cell):
    for schema in READER_SCHEMAS:
        objects = [*source.query_table_names_and_types(schema), *source.query_view_names_and_types(schema)]
        cataloged = _catalog(source, schema, [(o.name, o.type_ or TableType.Regular) for o in objects])
        expected = {name for s, name in EXPECTED["objects"] if s == schema}
        assert set(cataloged) == expected, f"{iris_cell.name}: {schema}"
    assert _access_warnings(source) == [], iris_cell.name
