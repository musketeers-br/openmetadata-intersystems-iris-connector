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
Spec 006 (ADR-0010): the IRIS dialect in the profiler registry and the IRIS form of MedianFn. IRIS has no
percentile function, so median and quartiles use a window over the schema-qualified table (SPIKE-04). No IRIS.
"""

import pytest
from sqlalchemy import Column, Integer, MetaData, Numeric, Table, column, select
from sqlalchemy.dialects import registry
from sqlalchemy.exc import CompileError

from metadata.profiler.orm.functions.median import MedianFn
from metadata.profiler.orm.registry import Dialects

DIALECT = registry.load("iris")()


def _table(schema: str, name: str) -> Table:
    return Table(name, MetaData(), Column("Id", Integer), Column("Weight", Numeric(5, 2)), schema=schema)


def _sql(selectable, percentile: float, table_name: str = "Patient") -> str:
    statement = select(MedianFn(column("Weight", Numeric(5, 2)), table_name, percentile)).select_from(selectable)
    return str(statement.compile(dialect=DIALECT, compile_kwargs={"literal_binds": True}))


def test_iris_is_a_registered_dialect():
    assert Dialects.Iris == "iris"


@pytest.mark.parametrize("percentile", [0.25, 0.5, 0.75])
def test_window_form_on_the_qualified_table(percentile):
    sql = _sql(_table("Clinic", "Patient"), percentile)
    assert "percentile_cont" not in sql.lower()
    assert f"ROUND({percentile} * " in sql and ", 0)" in sql
    assert "Clinic.Patient" in sql.replace('"', "")
    assert "AS median_value" in sql and "temp.median_value" in sql
    assert "IS NOT NULL" in sql


def test_same_table_name_in_another_schema():
    sql = _sql(_table("Billing", "Patient"), 0.5).replace('"', "")
    assert "Billing.Patient" in sql
    assert "Clinic" not in sql


def test_a_sample_is_read_from_the_sample():
    sample = select(_table("Clinic", "Patient")).cte("s01122a97dca927210827560cb7d76af8_rnd")
    sql = _sql(sample, 0.5)
    assert "FROM s01122a97dca927210827560cb7d76af8_rnd WHERE" in sql
    assert "Clinic.Patient" not in sql.split("WITH", 1)[-1].split(")", 1)[-1].replace('"', "")


def test_the_dimensional_form_is_refused_with_a_reason():
    statement = select(MedianFn(column("Weight"), "Patient", 0.5, "Id")).select_from(_table("Clinic", "Patient"))
    with pytest.raises(CompileError, match="IRIS"):
        statement.compile(dialect=DIALECT)
