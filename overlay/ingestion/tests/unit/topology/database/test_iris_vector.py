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
VECTOR enrichment (spec 004, ADR-0007): VECTOR columns, which the SQL catalog reports as varchar, are cataloged as
ARRAY of their element type from one read of %Dictionary.PropertyDefinition per run; without access, one hint per run.
No IRIS and no OpenMetadata server needed.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import types as sqltypes
from sqlalchemy.exc import OperationalError

from metadata.generated.schema.entity.data.table import DataType
from metadata.ingestion.api.status import Status
from metadata.ingestion.source.database.column_type_parser import ColumnTypeParser
from metadata.ingestion.source.database.iris.metadata import IrisSource
from metadata.ingestion.source.database.iris.queries import IRIS_COLUMN_TYPES, IRIS_VECTOR_COLUMNS
from metadata.ingestion.source.database.iris.types import (
    VECTOR_ELEMENT_TYPES,
    ColumnFacts,
    VectorFacts,
    parse_vector_parameters,
    resolve,
    resolve_vector,
)
from metadata.ingestion.source.database.sql_column_handler import SqlColumnHandlerMixin

DB_FQN = "iris_test.USER"
GRANT = "IRIS-VECTOR-GRANT: "
PARAMS = "IRIS-VECTOR-PARAMS: "


# --- parsing and resolution ---


@pytest.mark.parametrize(
    ("raw", "facts"),
    [
        ("DATATYPE,DOUBLE,LEN,3", VectorFacts("DOUBLE", 3)),
        ("LEN,384,DATATYPE,FLOAT", VectorFacts("FLOAT", 384)),
        ("datatype,decimal,len,2", VectorFacts("DECIMAL", 2)),
        ("DATATYPE, INTEGER , LEN, 4", VectorFacts("INTEGER", 4)),
        ("MAXLEN,10,DATATYPE,STRING,LEN,8,STORAGEDEFAULT,list", VectorFacts("STRING", 8)),
    ],
)
def test_parameters_are_parsed_as_key_value_pairs(raw, facts):
    assert parse_vector_parameters(raw) == facts


@pytest.mark.parametrize(
    "raw",
    [None, "", "DATATYPE,DOUBLE", "DATATYPE,DOUBLE,LEN,0", "DATATYPE,DOUBLE,LEN,abc", "LEN,3", "DATATYPE,,LEN,3",
     "DATATYPE,DOUBLE,LEN"],
)  # fmt: skip
def test_unusable_parameters_give_no_facts(raw):
    assert parse_vector_parameters(raw) is None


def test_the_element_table_is_the_decided_one():
    assert sorted(VECTOR_ELEMENT_TYPES) == ["DECIMAL", "DOUBLE", "FLOAT", "INT", "INTEGER", "STRING"]


def _framework_array_data_type(sqlalchemy_type):
    handler = SqlColumnHandlerMixin.__new__(SqlColumnHandlerMixin)
    _, array_data_type, _ = handler._process_col_type({"name": "c", "type": sqlalchemy_type}, "S")
    return array_data_type


@pytest.mark.parametrize(
    ("element", "array_data_type", "display"),
    [
        ("DOUBLE", "DOUBLE", "VECTOR(DOUBLE, 3)"),
        ("FLOAT", "FLOAT", "VECTOR(FLOAT, 3)"),
        ("DECIMAL", "DECIMAL", "VECTOR(DECIMAL, 3)"),
        ("INT", "INT", "VECTOR(INT, 3)"),
        ("INTEGER", "INT", "VECTOR(INT, 3)"),
        ("STRING", "STRING", "VECTOR(STRING, 3)"),
    ],
)
def test_each_element_is_an_array_the_framework_reads_back(element, array_data_type, display):
    resolved = resolve_vector(VectorFacts(element, 3))
    assert ColumnTypeParser.get_column_type(resolved.sqlalchemy_type) == "ARRAY"
    assert _framework_array_data_type(resolved.sqlalchemy_type) == array_data_type
    assert VECTOR_ELEMENT_TYPES[element].data_type.value == array_data_type
    assert resolved.display == display
    assert resolved.known


def test_an_unknown_element_is_an_array_of_unknown():
    resolved = resolve_vector(VectorFacts("TIMESTAMP", 2))
    assert _framework_array_data_type(resolved.sqlalchemy_type) == DataType.UNKNOWN.value
    assert resolved.display == "VECTOR(TIMESTAMP, 2)"
    assert not resolved.known


# --- stubs ---


def _db_error(message="[SQLCODE: <-99>:<Privilege violation>]\nsecond line"):
    return OperationalError("SELECT 1", {}, Exception(message))


class _Connection:
    """Answers the dictionary query and the column-type query; counts the dictionary reads."""

    def __init__(self, vectors=(), column_types=(), dictionary_access=True, fail=None):
        self.vectors, self.column_types, self.fail = list(vectors), list(column_types), fail
        self.dialect = SimpleNamespace(_dictionary_access=dictionary_access)
        self.dictionary_reads = 0

    def execute(self, statement, params=None):
        sql = str(statement)
        if sql == IRIS_VECTOR_COLUMNS:
            self.dictionary_reads += 1
            if self.fail is not None:
                raise self.fail
            return iter(self.vectors)
        if sql == IRIS_COLUMN_TYPES:
            return iter(self.column_types)
        return iter(())


def _source(connection):
    source = IrisSource.__new__(IrisSource)
    source.status = Status()
    source.metadata = None
    source.service_connection = SimpleNamespace(username="omd_reader")
    source.context = SimpleNamespace(
        get=lambda: SimpleNamespace(database_service="iris_test", database="USER"),
        get_current_thread_id=lambda: 1,
    )
    source._connection_map = {1: connection}
    return source


def _varchar(name, length=1037):
    return {"name": name, "type": sqltypes.VARCHAR(length), "system_data_type": f"VARCHAR({length})", "comment": "c"}


EMBEDDING = [
    ("AI", "Embedding", None, "Vec", "DATATYPE,DOUBLE,LEN,3"),
    ("AI", "Embedding", None, "Vec4", "DATATYPE,INT,LEN,4"),
    ("AI", "Embedding", "vec_low", "veclow", "DATATYPE,FLOAT,LEN,2"),
]


def _grants(source):
    return [w for w in source.status.warnings for reason in w.values() if reason.startswith(GRANT)]


def _params(source):
    return [w for w in source.status.warnings for reason in w.values() if reason.startswith(PARAMS)]


# --- enrichment (US1) ---


def test_only_the_cached_columns_are_enriched():
    source = _source(_Connection(EMBEDDING))
    columns = [
        {"name": "Id", "type": sqltypes.INTEGER()},
        _varchar("Content", 500),
        _varchar("Vec"),
        _varchar("vec_low", 691),
    ]
    source.enrich_vector_columns("AI", "Embedding", columns)
    by_name = {c["name"]: c for c in columns}
    assert by_name["Vec"]["system_data_type"] == "VECTOR(DOUBLE, 3)"
    assert isinstance(by_name["Vec"]["type"], sqltypes.ARRAY)
    assert by_name["vec_low"]["system_data_type"] == "VECTOR(FLOAT, 2)"
    assert by_name["Content"]["system_data_type"] == "VARCHAR(500)"
    assert isinstance(by_name["Id"]["type"], sqltypes.INTEGER)
    # Names, order and other keys stay.
    assert [c["name"] for c in columns] == ["Id", "Content", "Vec", "vec_low"]
    assert by_name["Vec"]["comment"] == "c"
    assert source.status.warnings == []


def test_matching_is_exact_on_schema_table_and_column():
    vectors = [("AI", "Embedding", None, "Vec", "DATATYPE,DOUBLE,LEN,3")]
    source = _source(_Connection(vectors))
    for schema, table, name in (("Other", "Embedding", "Vec"), ("AI", "embedding", "Vec"), ("AI", "Embedding", "vec")):
        columns = [_varchar(name)]
        source.enrich_vector_columns(schema, table, columns)
        assert columns[0]["system_data_type"] == "VARCHAR(1037)", (schema, table, name)


def test_the_dictionary_is_read_once_for_many_tables():
    connection = _Connection(EMBEDDING)
    source = _source(connection)
    for table in ("Embedding", "Patient", "Encounter", "AllTypes"):
        source.enrich_vector_columns("AI", table, [_varchar("Vec")])
    assert connection.dictionary_reads == 1


def test_a_table_without_varchar_columns_reads_nothing():
    connection = _Connection(EMBEDDING)
    source = _source(connection)
    source.enrich_vector_columns("Clinic", "Patient", [{"name": "Id", "type": sqltypes.INTEGER()}])
    source.enrich_vector_columns("Clinic", "Notes", [{"name": "N", "type": sqltypes.TEXT()}])
    assert connection.dictionary_reads == 0


def test_the_column_hook_enriches_after_the_type_map():
    rows = [("AI", "Embedding", "Vec", "varchar", 1037, None, None)]
    source = _source(_Connection(EMBEDDING, column_types=rows))
    inspector = SimpleNamespace(get_columns=lambda *a, **k: [{"name": "Vec", "type": sqltypes.NullType()}])
    columns = source._get_columns_internal("AI", "Embedding", "USER", inspector)
    assert columns[0]["system_data_type"] == "VECTOR(DOUBLE, 3)"


# --- the hint (US2) ---


def test_without_access_no_query_and_one_hint_naming_the_login():
    connection = _Connection(EMBEDDING, dictionary_access=False)
    source = _source(connection)
    columns = [_varchar("Vec")]
    source.enrich_vector_columns("AI", "Embedding", columns)
    for table in ("Patient", "Encounter"):
        source.enrich_vector_columns("Clinic", table, [_varchar("FullName", 120)])
    assert connection.dictionary_reads == 0
    assert columns[0]["system_data_type"] == "VARCHAR(1037)"
    assert source.status.warnings == [
        {
            DB_FQN: "IRIS-VECTOR-GRANT: if this Namespace has VECTOR columns, GRANT SELECT ON "
            "%Dictionary.PropertyDefinition TO omd_reader to catalog their element type and dimension"
        }
    ]


def test_no_hint_before_a_varchar_column_is_read():
    source = _source(_Connection(dictionary_access=False))
    source.enrich_vector_columns("Clinic", "Patient", [{"name": "Id", "type": sqltypes.INTEGER()}])
    assert source.status.warnings == []


def test_a_failing_query_is_one_hint_with_the_first_line_of_the_error():
    connection = _Connection(fail=_db_error("[SQLCODE: <-400>:<Fatal error>]\nPassword=S3cret"))
    source = _source(connection)
    for table in ("Embedding", "Patient"):
        source.enrich_vector_columns("AI", table, [_varchar("Vec")])
    assert connection.dictionary_reads == 1
    (warning,) = _grants(source)
    assert warning[DB_FQN].endswith("element type and dimension — [SQLCODE: <-400>:<Fatal error>]")
    assert "S3cret" not in warning[DB_FQN]
    assert not [w for w in source.status.warnings for r in w.values() if r.startswith("IRIS-ACCESS")]


def test_a_non_database_error_is_a_bug_and_propagates():
    source = _source(_Connection(fail=ValueError("bug")))
    with pytest.raises(ValueError, match="bug"):
        source.enrich_vector_columns("AI", "Embedding", [_varchar("Vec")])


def test_a_new_run_hints_again():
    for _ in range(2):
        source = _source(_Connection(dictionary_access=False))
        source.enrich_vector_columns("AI", "Embedding", [_varchar("Vec")])
        assert len(_grants(source)) == 1


def test_the_hint_holds_no_password():
    source = _source(_Connection(dictionary_access=False))
    source.service_connection = SimpleNamespace(username="omd_reader", authType=SimpleNamespace(password="S3cret"))
    source.enrich_vector_columns("AI", "Embedding", [_varchar("Vec")])
    assert "S3cret" not in str(source.status.warnings)


# --- odd dictionary values (US3) ---


def test_unusable_parameters_warn_once_per_column_and_keep_the_column():
    vectors = [("AI", "Embedding", None, "Vec", "DATATYPE,DOUBLE,LEN,zero")]
    source = _source(_Connection(vectors))
    for _ in range(2):
        columns = [_varchar("Vec")]
        source.enrich_vector_columns("AI", "Embedding", columns)
        assert columns[0]["system_data_type"] == "VARCHAR(1037)"
    assert _params(source) == [
        {
            "iris_test.USER.AI.Embedding.Vec": "IRIS-VECTOR-PARAMS: could not parse VECTOR parameters "
            "'DATATYPE,DOUBLE,LEN,zero'; cataloged as VARCHAR"
        }
    ]


def test_an_unknown_element_is_array_of_unknown_with_one_warning():
    vectors = [("AI", "Embedding", None, "Vec", "DATATYPE,TIMESTAMP,LEN,2")]
    source = _source(_Connection(vectors))
    for _ in range(2):
        columns = [_varchar("Vec")]
        source.enrich_vector_columns("AI", "Embedding", columns)
        assert _framework_array_data_type(columns[0]["type"]) == DataType.UNKNOWN.value
        assert columns[0]["system_data_type"] == "VECTOR(TIMESTAMP, 2)"
    assert _params(source) == [
        {
            "iris_test.USER.AI.Embedding.Vec": "IRIS-VECTOR-PARAMS: VECTOR element type 'TIMESTAMP' is not "
            "mapped; cataloged as ARRAY of UNKNOWN"
        }
    ]


# --- native metadata (US4) ---


@pytest.mark.parametrize(
    ("data_type", "array_data_type", "display"),
    [
        ("VECTOR(DOUBLE, 3)", "DOUBLE", "VECTOR(DOUBLE, 3)"),
        ("vector(int,4)", "INT", "vector(int,4)"),
        ("vector", "UNKNOWN", "vector"),
    ],
)
def test_a_catalog_that_reports_vector_is_used_as_is(data_type, array_data_type, display):
    resolved = resolve(ColumnFacts(data_type, 1037))
    assert ColumnTypeParser.get_column_type(resolved.sqlalchemy_type) == "ARRAY"
    assert _framework_array_data_type(resolved.sqlalchemy_type) == array_data_type
    assert resolved.display == display
    assert resolved.known  # no IRIS-UNKNOWN-TYPE


def test_native_vector_columns_skip_the_dictionary_and_give_no_hint():
    rows = [("AI", "Embedding", "Vec", "VECTOR(DOUBLE, 3)", None, None, None)]
    connection = _Connection(column_types=rows, dictionary_access=False)
    source = _source(connection)
    inspector = SimpleNamespace(get_columns=lambda *a, **k: [{"name": "Vec", "type": sqltypes.NullType()}])
    columns = source._get_columns_internal("AI", "Embedding", "USER", inspector)
    assert columns[0]["system_data_type"] == "VECTOR(DOUBLE, 3)"
    assert connection.dictionary_reads == 0
    assert source.status.warnings == []
