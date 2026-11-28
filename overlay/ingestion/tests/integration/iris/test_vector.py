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
VECTOR enrichment against a real IRIS (spec 004, ADR-0007). The connector's column read runs as the framework runs it
per table, without an OpenMetadata server, for the cell's login (conftest: `iris_cell`, `iris_engine`). With the
dictionary grant, AI.Embedding's VECTOR columns are ARRAY of their element type; without it, VARCHAR and one hint.
"""

from types import SimpleNamespace

import pytest
from tests.integration.iris.data.seed import EXPECTED, READER_SCHEMAS

from metadata.generated.schema.entity.data.table import TableType
from metadata.ingestion.api.status import Status
from metadata.ingestion.source.database.iris.metadata import IrisSource

pytestmark = pytest.mark.iris

SERVICE = "iris_test"
# The SQL catalog's varchar length of each fixture VECTOR column (spec 004, research R1).
CATALOG_LENGTHS = {"Vec": 1037, "Vec4": 83, "vec_low": 691}
# AI.Embedding's other columns, as spec 003 catalogs them for every login.
OTHER_COLUMNS = {"Id": ("INT", None, "INTEGER"), "Content": ("VARCHAR", 500, "VARCHAR(500)")}


@pytest.fixture
def source(iris_cell, iris_engine, iris_service_connection):
    """A fresh IrisSource per test: one run, so the dictionary read and the hint start over."""
    source = IrisSource.__new__(IrisSource)
    source.service_connection = iris_service_connection
    source.engine = iris_engine
    source.status = Status()
    source.metadata = None
    source._connection_map = {}
    source._inspector_map = {}
    current = SimpleNamespace(database_service=SERVICE, database=iris_cell.namespace, database_schema=None)
    source.context = SimpleNamespace(get=lambda: current, get_current_thread_id=lambda: 1)
    yield source
    source.connection.close()


def _columns(source, schema, table, table_type=TableType.Regular):
    source.context.get().database_schema = schema
    columns, _, _ = source.get_columns_and_constraints(
        schema_name=schema,
        table_name=table,
        db_name=source.context.get().database,
        inspector=source.inspector,
        table_type=table_type,
    )
    return {column.name.root: column for column in columns}


def _hints(source):
    return [(key, reason) for w in source.status.warnings for key, reason in w.items() if "IRIS-VECTOR" in reason]


def test_the_vector_columns(source, iris_cell):
    embedding = _columns(source, "AI", "Embedding")
    assert list(embedding) == [name for name, _ in EXPECTED["columns"][("AI", "Embedding")]], iris_cell.name
    for name, (data_type, length, display) in OTHER_COLUMNS.items():
        column = embedding[name]
        cataloged = (
            column.dataType.value,
            column.dataLength if data_type == "VARCHAR" else None,
            column.dataTypeDisplay,
        )
        assert cataloged == (data_type, length, display), f"{iris_cell.name}: {name}"
    for (_, _, name), (element, dimension) in EXPECTED["vectors"].items():
        column = embedding[name]
        if iris_cell.has_dict_grant:
            got = (column.dataType.value, column.arrayDataType.value, column.dataTypeDisplay)
            assert got == ("ARRAY", element, f"VECTOR({element}, {dimension})"), f"{iris_cell.name}: {name}"
        else:
            got = (column.dataType.value, column.dataLength, column.dataTypeDisplay)
            want = ("VARCHAR", CATALOG_LENGTHS[name], f"VARCHAR({CATALOG_LENGTHS[name]})")
            assert got == want, f"{iris_cell.name}: {name}"
    if iris_cell.has_dict_grant:
        assert _hints(source) == [], iris_cell.name


def test_one_hint_for_a_run_over_every_readable_fixture(source, iris_cell):
    for schema in READER_SCHEMAS:
        for listed in [*source.query_table_names_and_types(schema), *source.query_view_names_and_types(schema)]:
            _columns(source, schema, listed.name, listed.type_ or TableType.Regular)
    hints = _hints(source)
    if iris_cell.has_dict_grant:
        assert hints == [], f"{iris_cell.name}: {hints}"
        return
    assert len(hints) == 1, f"{iris_cell.name}: {hints}"
    key, reason = hints[0]
    assert key == f"{SERVICE}.{iris_cell.namespace}"
    assert reason.startswith("IRIS-VECTOR-GRANT: if this Namespace has VECTOR columns, ")
    assert f"%Dictionary.PropertyDefinition TO {iris_cell.username} " in reason
    assert iris_cell.password not in reason
