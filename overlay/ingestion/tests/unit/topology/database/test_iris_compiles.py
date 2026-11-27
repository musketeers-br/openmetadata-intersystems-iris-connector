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
Spec 006: IRIS 2026.3 refuses COALESCE(<expr>, ?) with an untyped bound parameter (SQLCODE -378), which
OpenMetadata's null count and between-bounds checker generate. The connector compiles COALESCE for the IRIS
dialect with its bound values written as literals. No IRIS.
"""

from sqlalchemy import Column, Integer, MetaData, Table, column, func, literal, select
from sqlalchemy.dialects import postgresql, registry

import metadata.ingestion.source.database.iris.service_spec  # noqa: F401  (registers the IRIS compiles)
from metadata.profiler.metrics.registry import Metrics

IRIS = registry.load("iris")()
TABLE = Table("Patient", MetaData(), Column("Weight", Integer), schema="Clinic")


def _sql(expression, dialect=IRIS) -> str:
    return str(select(expression).select_from(TABLE).compile(dialect=dialect))


def test_null_count_has_no_parameter_in_coalesce():
    sql = _sql(Metrics.nullCount.value(TABLE.c.Weight).fn())
    coalesce = sql[sql.index("COALESCE(") :]
    assert coalesce.rstrip().endswith(", 0) AS anon_1") or ", 0)" in coalesce
    assert "), ?)" not in sql


def test_literal_argument_is_written_as_a_literal():
    sql = _sql(func.coalesce(func.sum(column("Weight")), literal(0)))
    assert "COALESCE(sum(" in sql and ", 0)" in sql and "?" not in sql


def test_text_values_are_quoted_by_the_dialect():
    sql = _sql(func.coalesce(column("Name"), "n/a"))
    assert "COALESCE(\"Name\", 'n/a')" in sql or "COALESCE(Name, 'n/a')" in sql


def test_column_arguments_are_unchanged():
    sql = _sql(func.coalesce(column("A"), column("B")))
    assert sql.startswith("SELECT COALESCE(") and "?" not in sql


def test_other_dialects_keep_their_parameters():
    sql = _sql(func.coalesce(func.sum(column("Weight")), 0), dialect=postgresql.dialect())
    assert "coalesce(sum(" in sql and ", %(coalesce_" in sql
