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
SQL compilation the IRIS connector needs for OpenMetadata's profiler and data-quality expressions (spec 006).

IRIS 2026.3 refuses COALESCE(<expr>, ?) when the second argument is an untyped bound parameter
(SQLCODE -378, "Datatype mismatch, explicit CAST is required"); 2026.1 accepts it. OpenMetadata's null count
(`coalesce(SUM(...), 0)`) and between-bounds checker (`coalesce(sum(...), literal(0))`) generate exactly that, and
the profiler computes all of a column's static metrics in one query, so the column lost all of them.

For the IRIS dialect only, COALESCE is compiled with its bound values written as literals: the same SQL, a constant
in place of `?`. Recorded in GAP-REPORT.md; removable when IRIS accepts the parameter again.
Imported by service_spec.py so that it is registered whenever the connector is used.
"""

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import BindParameter
from sqlalchemy.sql.functions import coalesce

IRIS_DIALECT = "iris"


@compiles(coalesce, IRIS_DIALECT)
def compile_coalesce(element, compiler, **kw):
    """COALESCE with literal constants instead of bound parameters (IRIS 2026.3, SQLCODE -378)."""
    literal_kw = {**kw, "literal_binds": True}
    arguments = [
        compiler.process(clause, **(literal_kw if isinstance(clause, BindParameter) else kw))
        for clause in element.clauses
    ]
    return f"COALESCE({', '.join(arguments)})"
