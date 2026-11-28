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
Type mapping against a real IRIS (spec 003). Needs only an IRIS instance with the shared fixtures: the
connector's column read runs as the framework runs it per table, without an OpenMetadata server, for
the cell's login (conftest: `iris_cell`, `iris_engine`, `iris_service_connection`).
"""

from types import SimpleNamespace

import pytest
from tests.integration.iris.data.seed import EXPECTED, READER_SCHEMAS

from metadata.generated.schema.entity.data.table import TableType
from metadata.ingestion.api.status import Status
from metadata.ingestion.source.database.iris import types as iris_types
from metadata.ingestion.source.database.iris.metadata import IrisSource

pytestmark = pytest.mark.iris

# Types.AllTypes as cataloged (data-model "Fixture catalog v2"): data type, length (character and
# binary types only), (precision, scale) (numeric only), display.
ALL_TYPES = {
    "Id": ("INT", None, None, "INTEGER"),
    "BigIntCol": ("BIGINT", None, None, "BIGINT"),
    "BitCol": ("BOOLEAN", None, None, "BIT"),
    "DateCol": ("DATE", None, None, "DATE"),
    "DoubleCol": ("DOUBLE", None, None, "DOUBLE"),
    "GuidCol": ("UUID", None, None, "GUID"),
    "LongVarBinaryCol": ("BLOB", None, None, "LONGVARBINARY"),
    "LongVarCharCol": ("TEXT", None, None, "LONGVARCHAR"),
    "NumericCol": ("NUMERIC", None, (7, 3), "NUMERIC(7,3)"),
    "SmallIntCol": ("SMALLINT", None, None, "SMALLINT"),
    "TimeCol": ("TIME", None, None, "TIME"),
    "TimestampCol": ("TIMESTAMP", None, None, "TIMESTAMP"),
    "TinyIntCol": ("TINYINT", None, None, "TINYINT"),
    "VarBinaryCol": ("VARBINARY", 16, None, "VARBINARY(16)"),
    "VarCharCol": ("VARCHAR", 40, None, "VARCHAR(40)"),
    "VarChar1Col": ("VARCHAR", 1, None, "VARCHAR(1)"),
}
LENGTH_TYPES = {"VARCHAR", "VARBINARY"}


@pytest.fixture
def source(iris_cell, iris_engine, iris_service_connection):
    """A fresh IrisSource per test (one per run, so the unknown-type record starts empty)."""
    source = IrisSource.__new__(IrisSource)
    source.service_connection = iris_service_connection
    source.engine = iris_engine
    source.status = Status()
    source.metadata = None
    source._connection_map = {}
    source._inspector_map = {}
    current = SimpleNamespace(database_service="iris_test", database=iris_cell.namespace, database_schema=None)
    source.context = SimpleNamespace(get=lambda: current, get_current_thread_id=lambda: 1)
    yield source
    source.connection.close()


def _columns(source, schema, table, table_type=TableType.Regular):
    source.context.get().database_schema = schema  # the framework reads it for column tags
    columns, _, _ = source.get_columns_and_constraints(
        schema_name=schema,
        table_name=table,
        db_name=source.context.get().database,
        inspector=source.inspector,
        table_type=table_type,
    )
    return {column.name.root: column for column in columns}


def _cataloged(column):
    precision = (column.precision, column.scale) if column.precision is not None else None
    length = column.dataLength if column.dataType.value in LENGTH_TYPES else None
    return column.dataType.value, length, precision, column.dataTypeDisplay


def _unknown_type_warnings(source):
    return [w for w in source.status.warnings for reason in w.values() if reason.startswith("IRIS-UNKNOWN-TYPE")]


def test_every_column_of_the_type_fixture(source, iris_cell):
    columns = _columns(source, "Types", "AllTypes")
    assert list(columns) == list(ALL_TYPES), iris_cell.name
    for name, expected in ALL_TYPES.items():
        assert _cataloged(columns[name]) == expected, f"{iris_cell.name}: Types.AllTypes.{name}"


def test_the_other_fixture_columns(source, iris_cell):
    encounter = _columns(source, "Clinic", "Encounter")
    assert _cataloged(encounter["Notes"]) == ("TEXT", None, None, "LONGVARCHAR"), iris_cell.name
    assert _cataloged(encounter["Active"]) == ("BOOLEAN", None, None, "BIT"), iris_cell.name
    patient = _columns(source, "Clinic", "Patient")
    assert _cataloged(patient["Weight"]) == ("NUMERIC", None, (5, 2), "NUMERIC(5,2)"), iris_cell.name
    assert _cataloged(patient["FullName"]) == ("VARCHAR", 120, None, "VARCHAR(120)"), iris_cell.name
    # AI.Embedding's VECTOR columns depend on the dictionary grant: test_vector.py (spec 004).


def test_view_columns_are_mapped_too(source, iris_cell):
    view = _columns(source, "Clinic", "ActivePatient", TableType.View)
    assert _cataloged(view["PatientId"]) == ("INT", None, None, "INTEGER"), iris_cell.name
    assert _cataloged(view["FullName"]) == ("VARCHAR", 120, None, "VARCHAR(120)"), iris_cell.name


def test_the_fixtures_give_no_unknown_type_warning(source, iris_cell):
    # Only the schemas every login can read; Scratch and Restricted have no reader grant (spec 005 covers them).
    readable = [(schema, table) for schema, table in EXPECTED["columns"] if schema in READER_SCHEMAS]
    for schema, table in readable:
        table_type = TableType.View if EXPECTED["objects"][(schema, table)] == "VIEW" else TableType.Regular
        assert _columns(source, schema, table, table_type), f"{iris_cell.name}: {schema}.{table}"
    assert _unknown_type_warnings(source) == [], iris_cell.name


def test_an_unmapped_type_warns_once_per_run(source, iris_cell, monkeypatch):
    monkeypatch.delitem(iris_types.IRIS_TYPES, "numeric")
    all_types = _columns(source, "Types", "AllTypes")
    patient = _columns(source, "Clinic", "Patient")
    assert all_types["NumericCol"].dataType.value == "UNKNOWN", iris_cell.name
    assert patient["Weight"].dataType.value == "UNKNOWN", iris_cell.name
    assert all_types["NumericCol"].dataTypeDisplay == "NUMERIC", iris_cell.name
    warnings = _unknown_type_warnings(source)
    assert len(warnings) == 1, f"{iris_cell.name}: {warnings}"
    key, reason = next(iter(warnings[0].items()))
    assert key == f"iris_test.{iris_cell.namespace}"
    assert "IRIS type 'numeric'" in reason
    assert "first seen on Types.AllTypes.NumericCol" in reason
    # The rest of the table is still mapped.
    assert _cataloged(all_types["VarCharCol"]) == ALL_TYPES["VarCharCol"], iris_cell.name
