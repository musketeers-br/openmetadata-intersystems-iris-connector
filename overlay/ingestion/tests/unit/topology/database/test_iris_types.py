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
Unit tests for the IRIS type map (spec 003, ADR-0006): the table, the resolver, the unknown-type
warning, the call from the column read, and the rendered docs table. No IRIS needed.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from metadata.generated.schema.entity.data.table import DataType
from metadata.ingestion.api.status import Status
from metadata.ingestion.source.database.column_type_parser import ColumnTypeParser
from metadata.ingestion.source.database.iris.metadata import IrisSource
from metadata.ingestion.source.database.iris.types import (
    IRIS_TYPES,
    LENGTH,
    PRECISION,
    ColumnFacts,
    UnknownTypes,
    render_markdown_table,
    resolve,
    unknown_type_message,
)
from metadata.ingestion.source.database.sql_column_handler import SqlColumnHandlerMixin

# What the IRIS SQL catalog reports on latest-em, latest-cd and latest-preview (research R1).
CATALOG_TYPES = [
    "bigint",
    "bit",
    "date",
    "double",
    "guid",
    "integer",
    "longvarbinary",
    "longvarchar",
    "numeric",
    "smallint",
    "time",
    "timestamp",
    "tinyint",
    "varbinary",
    "varchar",
]

# Expected resolution per row: (facts, OpenMetadata type, data length, precision, display).
EXPECTED = {
    "bigint": (ColumnFacts("bigint", None, 19, 0), "BIGINT", None, None, "BIGINT"),
    "bit": (ColumnFacts("bit"), "BOOLEAN", None, None, "BIT"),
    "date": (ColumnFacts("date"), "DATE", None, None, "DATE"),
    "double": (ColumnFacts("double", None, 15, None), "DOUBLE", None, None, "DOUBLE"),
    "guid": (ColumnFacts("guid"), "UUID", None, None, "GUID"),
    "integer": (ColumnFacts("integer", None, 10, 0), "INT", None, None, "INTEGER"),
    "longvarbinary": (ColumnFacts("longvarbinary", 2147483647), "BLOB", None, None, "LONGVARBINARY"),
    "longvarchar": (ColumnFacts("longvarchar", 2147483647), "TEXT", None, None, "LONGVARCHAR"),
    "numeric": (ColumnFacts("numeric", None, 7, 3), "NUMERIC", None, ("7", "3"), "NUMERIC(7,3)"),
    "smallint": (ColumnFacts("smallint", None, 5, 0), "SMALLINT", None, None, "SMALLINT"),
    "time": (ColumnFacts("time"), "TIME", None, None, "TIME"),
    "timestamp": (ColumnFacts("timestamp"), "TIMESTAMP", None, None, "TIMESTAMP"),
    "tinyint": (ColumnFacts("tinyint", None, 3, 0), "TINYINT", None, None, "TINYINT"),
    "varbinary": (ColumnFacts("varbinary", 16), "VARBINARY", 16, None, "VARBINARY(16)"),
    "varchar": (ColumnFacts("varchar", 40), "VARCHAR", 40, None, "VARCHAR(40)"),
}

# The dev repository holds the spec folder next to .om/; an upstream tree has no such file and skips.
CONTRACT = Path(__file__).resolve().parents[6] / "specs" / "003-type-mapping" / "contracts" / "type-mapping.md"
BEGIN, END = "<!-- BEGIN GENERATED: render_markdown_table() -->", "<!-- END GENERATED -->"


def _om_column(resolved):
    """What the framework derives from the column dict (SqlColumnHandlerMixin, OpenMetadata 2.1.1)."""
    col_type = ColumnTypeParser.get_column_type(resolved.sqlalchemy_type)
    return (
        col_type,
        SqlColumnHandlerMixin._check_col_length(col_type, resolved.sqlalchemy_type),
        ColumnTypeParser.check_col_precision(col_type, resolved.sqlalchemy_type),
    )


# --- 003: the table ---


class TestTable:
    def test_one_row_per_reported_catalog_type(self):
        assert sorted(IRIS_TYPES) == CATALOG_TYPES

    def test_every_target_is_an_openmetadata_data_type(self):
        assert all(isinstance(row.data_type, DataType) for row in IRIS_TYPES.values())

    def test_only_character_and_binary_rows_keep_length_and_only_numeric_keeps_precision(self):
        assert {key for key, row in IRIS_TYPES.items() if row.keeps == LENGTH} == {"varchar", "varbinary"}
        assert {key for key, row in IRIS_TYPES.items() if row.keeps == PRECISION} == {"numeric"}

    def test_decided_rows(self):
        assert IRIS_TYPES["bit"].data_type == DataType.BOOLEAN
        assert IRIS_TYPES["longvarchar"].data_type == DataType.TEXT
        assert IRIS_TYPES["longvarbinary"].data_type == DataType.BLOB

    @pytest.mark.parametrize("key", sorted(IRIS_TYPES))
    def test_the_framework_derives_the_row_type(self, key):
        facts, om_type, length, precision, display = EXPECTED[key]
        resolved = resolve(facts)
        assert resolved.known
        assert IRIS_TYPES[key].data_type.value == om_type
        assert _om_column(resolved) == (om_type, length, precision)
        assert resolved.display == display


# --- 003: resolving one column ---


class TestResolve:
    def test_matching_ignores_case(self):
        assert resolve(ColumnFacts("VARCHAR", 10)).display == resolve(ColumnFacts("varchar", 10)).display

    def test_varchar_of_one_stays_varchar_of_one(self):
        assert _om_column(resolve(ColumnFacts("varchar", 1))) == ("VARCHAR", 1, None)

    def test_longvarchar_is_text_without_length(self):
        resolved = resolve(ColumnFacts("longvarchar", 2147483647))
        assert _om_column(resolved) == ("TEXT", None, None)
        assert resolved.display == "LONGVARCHAR"

    def test_vector_as_reported_is_varchar_with_its_length(self):
        assert _om_column(resolve(ColumnFacts("varchar", 1037))) == ("VARCHAR", 1037, None)

    def test_numeric_without_scale_shows_zero(self):
        assert resolve(ColumnFacts("numeric", None, 15, None)).display == "NUMERIC(15,0)"

    def test_an_unmapped_type_is_unknown_and_keeps_its_name(self):
        resolved = resolve(ColumnFacts("geography", 100))
        assert not resolved.known
        assert _om_column(resolved)[0] == "UNKNOWN"
        assert resolved.display == "GEOGRAPHY"


# --- 003: unknown types ---


class TestUnknownTypes:
    def test_first_is_true_once_per_type_ignoring_case(self):
        record = UnknownTypes()
        assert record.first("geography", "S.T.A")
        assert not record.first("GEOGRAPHY", "S.T.B")
        assert record.first("json", "S.T.C")
        assert record.first_seen == {"geography": "S.T.A", "json": "S.T.C"}

    def test_message_follows_the_contract(self):
        assert unknown_type_message("geography", "Geo.Place.Shape") == (
            "IRIS-UNKNOWN-TYPE: IRIS type 'geography' is not mapped; cataloged as UNKNOWN "
            "(first seen on Geo.Place.Shape)"
        )


# --- 003: the call from IrisSource ---


class _Connection:
    """Answers the type query with catalog rows for the bound (schema, table)."""

    def __init__(self, rows=(), fail=False):
        self.rows, self.fail, self.calls = list(rows), fail, []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        if self.fail:
            raise OperationalError("SELECT", {}, Exception("[SQLCODE: <-99>:<Privilege violation>]"))
        return iter([r for r in self.rows if (r[0], r[1]) == (params["schema"], params["table"])])


def _source(connection):
    source = IrisSource.__new__(IrisSource)
    source.status = Status()
    source.metadata = None
    source.context = SimpleNamespace(
        get=lambda: SimpleNamespace(database_service="iris_test", database="USER"),
        get_current_thread_id=lambda: 1,
    )
    source._connection_map = {1: connection}
    return source


def _row(table, column, data_type, length=None, precision=None, scale=None, schema="Types"):
    return (schema, table, column, data_type, length, precision, scale)


class TestMapColumnTypes:
    def test_each_column_gets_its_own_catalog_row(self):
        connection = _Connection([_row("T", "Name", "varchar", 40), _row("T", "Amount", "numeric", None, 7, 3)])
        columns = [{"name": "Name", "type": "dialect", "comment": "c"}, {"name": "Amount", "type": "dialect"}]
        _source(connection).map_column_types("Types", "T", columns)
        assert [c["system_data_type"] for c in columns] == ["VARCHAR(40)", "NUMERIC(7,3)"]
        assert [_om_column(resolve(ColumnFacts(*r[3:])))[0] for r in connection.rows] == ["VARCHAR", "NUMERIC"]
        assert ColumnTypeParser.get_column_type(columns[0]["type"]) == "VARCHAR"
        assert columns[0]["comment"] == "c"

    def test_the_query_is_bound_on_schema_and_table(self):
        connection = _Connection()
        _source(connection).map_column_types("Clinic", "Patient", [{"name": "A", "type": "x"}])
        assert connection.calls[0][1] == {"schema": "Clinic", "table": "Patient"}
        assert "INFORMATION_SCHEMA.COLUMNS" in connection.calls[0][0]

    def test_rows_of_a_same_name_table_in_another_case_are_ignored(self):
        connection = _Connection([_row("T", "A", "varchar", 5), _row("t", "A", "integer")])
        connection.execute = lambda statement, params: iter(connection.rows)
        columns = [{"name": "A", "type": "x"}]
        _source(connection).map_column_types("Types", "T", columns)
        assert columns[0]["system_data_type"] == "VARCHAR(5)"

    def test_a_column_without_a_catalog_row_keeps_the_dialect_type(self):
        columns = [{"name": "A", "type": "dialect-type"}]
        _source(_Connection()).map_column_types("Types", "T", columns)
        assert columns == [{"name": "A", "type": "dialect-type"}]

    def test_names_order_and_other_keys_are_untouched(self):
        connection = _Connection([_row("T", "B", "bit"), _row("T", "A", "date")])
        columns = [{"name": "B", "type": "x", "nullable": True}, {"name": "A", "type": "y", "comment": "d"}]
        _source(connection).map_column_types("Types", "T", columns)
        assert [(c["name"], c.get("nullable"), c.get("comment")) for c in columns] == [
            ("B", True, None),
            ("A", None, "d"),
        ]

    def test_no_columns_no_query(self):
        connection = _Connection()
        _source(connection).map_column_types("Types", "T", [])
        assert connection.calls == []

    def test_an_unreadable_catalog_is_one_access_warning_and_keeps_the_columns(self):
        source = _source(_Connection(fail=True))
        columns = [{"name": "A", "type": "dialect-type"}]
        source.map_column_types("S", "T", columns)
        assert columns == [{"name": "A", "type": "dialect-type"}]
        assert source.status.warnings == [
            {"iris_test.USER.S.T": "IRIS-ACCESS: cannot read columns of S.T: [SQLCODE: <-99>:<Privilege violation>]"}
        ]

    def test_mapped_types_give_no_warning(self):
        source = _source(_Connection([_row("T", c, c) for c in CATALOG_TYPES]))
        source.map_column_types("Types", "T", [{"name": c, "type": "x"} for c in CATALOG_TYPES])
        assert source.status.warnings == []


class TestUnknownTypeWarning:
    def test_one_warning_per_type_per_run_naming_the_first_column(self):
        connection = _Connection(
            [_row("T1", "A", "geography"), _row("T1", "B", "geography"), _row("T2", "C", "GEOGRAPHY")]
        )
        source = _source(connection)
        first = [{"name": "A", "type": "x"}, {"name": "B", "type": "x"}]
        second = [{"name": "C", "type": "x"}]
        source.map_column_types("Types", "T1", first)
        source.map_column_types("Types", "T2", second)
        assert source.status.warnings == [{"iris_test.USER": unknown_type_message("geography", "Types.T1.A")}]
        assert [ColumnTypeParser.get_column_type(c["type"]) for c in first + second] == ["UNKNOWN"] * 3
        assert [c["system_data_type"] for c in first + second] == ["GEOGRAPHY"] * 3

    def test_two_unmapped_types_give_two_warnings(self):
        source = _source(_Connection([_row("T", "A", "geography"), _row("T", "B", "json")]))
        source.map_column_types("Types", "T", [{"name": "A", "type": "x"}, {"name": "B", "type": "x"}])
        assert [re.search(r"type '(\w+)'", next(iter(w.values()))).group(1) for w in source.status.warnings] == [
            "geography",
            "json",
        ]

    def test_a_new_run_warns_again(self):
        rows = [_row("T", "A", "geography")]
        for _ in range(2):
            source = _source(_Connection(rows))
            source.map_column_types("Types", "T", [{"name": "A", "type": "x"}])
            assert len(source.status.warnings) == 1

    def test_the_run_goes_on(self):
        source = _source(_Connection([_row("T", "A", "geography"), _row("T", "B", "varchar", 3)]))
        columns = [{"name": "A", "type": "x"}, {"name": "B", "type": "x"}]
        source.map_column_types("Types", "T", columns)
        assert columns[1]["system_data_type"] == "VARCHAR(3)"


# --- 003: the docs table ---


class TestRenderedTable:
    def test_one_row_per_type_in_key_order(self):
        lines = render_markdown_table().splitlines()
        assert lines[0].startswith("| IRIS `DATA_TYPE` |")
        keys = [re.match(r"\| `(\w+)` \|", line).group(1) for line in lines[2:]]
        assert keys == sorted(IRIS_TYPES)

    def test_the_committed_contract_table_is_current(self):
        if not CONTRACT.is_file():
            pytest.skip(f"{CONTRACT} is not in this tree (the spec folder lives in the dev repository)")
        text = CONTRACT.read_text(encoding="utf-8")
        committed = text.split(BEGIN, 1)[1].split(END, 1)[0].strip()
        assert committed == render_markdown_table().strip(), (
            "contracts/type-mapping.md is stale: paste the output of "
            "`python -c 'from metadata.ingestion.source.database.iris.types import render_markdown_table as r; "
            "print(r())'` between its markers"
        )
