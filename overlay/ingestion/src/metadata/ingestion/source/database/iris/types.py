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
InterSystems IRIS type mapping. One mapping module for the connector (ADR-0006).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple

from sqlalchemy import types as sqltypes

from metadata.generated.schema.entity.data.table import DataType

# --- 003: type map ---

LENGTH = "length"
PRECISION = "precision, scale"


@dataclass(frozen=True)
class IrisTypeRow:
    """One INFORMATION_SCHEMA.COLUMNS.DATA_TYPE value and how it is cataloged."""

    data_type: DataType
    keeps: str  # LENGTH, PRECISION or ""
    ddl: str  # IRIS DDL the catalog reports as this value (examples, for the docs)
    note: str = ""


# Every DATA_TYPE the IRIS SQL catalog reports on latest-em, latest-cd and latest-preview; every DDL type and
# synonym collapses onto one of these (spec 003, research R1). Keys are lower case; lookups lower-case the value.
IRIS_TYPES: dict[str, IrisTypeRow] = {
    "bigint": IrisTypeRow(DataType.BIGINT, "", "BIGINT, SERIAL, ROWVERSION"),
    "bit": IrisTypeRow(DataType.BOOLEAN, "", "BIT, %Library.Boolean", "IRIS has no BOOLEAN DDL type"),
    "date": IrisTypeRow(DataType.DATE, "", "DATE"),
    "double": IrisTypeRow(DataType.DOUBLE, "", "DOUBLE, DOUBLE PRECISION, FLOAT, REAL"),
    "guid": IrisTypeRow(DataType.UUID, "", "UNIQUEIDENTIFIER"),
    "integer": IrisTypeRow(DataType.INT, "", "INT, INTEGER, MEDIUMINT"),
    "longvarbinary": IrisTypeRow(DataType.BLOB, "", "LONGVARBINARY, BLOB, IMAGE, LONG RAW", "binary stream"),
    "longvarchar": IrisTypeRow(DataType.TEXT, "", "LONGVARCHAR, TEXT, CLOB, LONG VARCHAR", "character stream"),
    "numeric": IrisTypeRow(DataType.NUMERIC, PRECISION, "NUMERIC(p,s), DECIMAL(p,s), NUMBER, MONEY"),
    "smallint": IrisTypeRow(DataType.SMALLINT, "", "SMALLINT"),
    "time": IrisTypeRow(DataType.TIME, "", "TIME"),
    "timestamp": IrisTypeRow(DataType.TIMESTAMP, "", "TIMESTAMP, DATETIME, SMALLDATETIME, POSIXTIME"),
    "tinyint": IrisTypeRow(DataType.TINYINT, "", "TINYINT"),
    "varbinary": IrisTypeRow(DataType.VARBINARY, LENGTH, "VARBINARY(n), BINARY(n), RAW(n)"),
    "varchar": IrisTypeRow(
        DataType.VARCHAR,
        LENGTH,
        "VARCHAR(n), CHAR(n), NVARCHAR(n), %Library.String",
        "also VECTOR columns (enriched by spec 004) and %List projections",
    ),
}


class ColumnFacts(NamedTuple):
    """One column as INFORMATION_SCHEMA.COLUMNS reports it."""

    data_type: str | None
    length: int | None = None
    precision: int | None = None
    scale: int | None = None


class ResolvedType(NamedTuple):
    sqlalchemy_type: sqltypes.TypeEngine
    display: str
    known: bool


class _NamedType(sqltypes.UserDefinedType):
    """A type the framework knows only by name: TINYINT has no generic SQLAlchemy type."""

    cache_ok = True

    def __init__(self, name: str):
        self.name = name

    def get_col_spec(self, **_kw) -> str:
        return self.name


def iris_unmapped_type() -> sqltypes.TypeEngine:
    """A type whose name matches nothing in ColumnTypeParser, so the framework catalogs it as UNKNOWN."""
    return _NamedType("IRIS_UNMAPPED")


# The SQLAlchemy type the framework's ColumnTypeParser maps to each row's DataType (research R3).
_PLAIN_TYPES = {
    DataType.BIGINT: sqltypes.BIGINT,
    DataType.BOOLEAN: sqltypes.BOOLEAN,
    DataType.DATE: sqltypes.DATE,
    DataType.DOUBLE: sqltypes.DOUBLE,
    DataType.UUID: sqltypes.UUID,
    DataType.INT: sqltypes.INTEGER,
    DataType.BLOB: sqltypes.BLOB,
    DataType.TEXT: sqltypes.TEXT,
    DataType.SMALLINT: sqltypes.SMALLINT,
    DataType.TIME: sqltypes.TIME,
    DataType.TIMESTAMP: sqltypes.TIMESTAMP,
    DataType.TINYINT: lambda: _NamedType("TINYINT"),
}


def _sqlalchemy_type(row: IrisTypeRow, facts: ColumnFacts) -> sqltypes.TypeEngine:
    if row.data_type == DataType.VARCHAR:
        return sqltypes.VARCHAR(facts.length)
    if row.data_type == DataType.VARBINARY:
        return sqltypes.VARBINARY(facts.length)
    if row.data_type == DataType.NUMERIC:
        return sqltypes.NUMERIC(facts.precision, facts.scale or 0)
    return _PLAIN_TYPES[row.data_type]()


def _display(name: str, row: IrisTypeRow, facts: ColumnFacts) -> str:
    if row.keeps == LENGTH and facts.length is not None:
        return f"{name}({facts.length})"
    if row.keeps == PRECISION and facts.precision is not None:
        return f"{name}({facts.precision},{facts.scale or 0})"
    return name


def resolve(facts: ColumnFacts) -> ResolvedType:
    """The type the framework should catalog for one column, from its raw catalog facts (not the dialect's)."""
    raw = facts.data_type or ""
    native = native_vector(raw)  # spec 004: a release that reports VECTOR in the SQL catalog
    if native is not None:
        return native
    row = IRIS_TYPES.get(raw.lower())
    if row is None:
        return ResolvedType(iris_unmapped_type(), raw.upper(), known=False)
    return ResolvedType(_sqlalchemy_type(row, facts), _display(raw.upper(), row, facts), known=True)


class UnknownTypes:
    """Unmapped types already reported in this run, with the first column each was seen on."""

    def __init__(self):
        self.first_seen: dict[str, str] = {}

    def first(self, raw_type: str, where: str) -> bool:
        key = raw_type.lower()
        if key in self.first_seen:
            return False
        self.first_seen[key] = where
        return True


def unknown_type_message(raw_type: str, where: str) -> str:
    return f"IRIS-UNKNOWN-TYPE: IRIS type '{raw_type}' is not mapped; cataloged as UNKNOWN (first seen on {where})"


def render_markdown_table() -> str:
    """The type table for the documentation, generated from IRIS_TYPES (ADR-0006)."""
    lines = [
        "| IRIS `DATA_TYPE` | OpenMetadata type | Kept | IRIS DDL reported as it | Note |",
        "|---|---|---|---|---|",
    ]
    for key in sorted(IRIS_TYPES):
        row = IRIS_TYPES[key]
        lines.append(f"| `{key}` | `{row.data_type.value}` | {row.keeps or '—'} | {row.ddl} | {row.note} |")
    return "\n".join(lines)


# --- 004: VECTOR enrichment ---


class VectorElement(NamedTuple):
    """One VECTOR element type: the arrayDataType the framework derives, and the SQLAlchemy item type that gives it."""

    data_type: DataType
    item_type: Callable[[], sqltypes.TypeEngine]


# The element types IRIS DDL accepts (research R3). The framework reads arrayDataType from the ARRAY's item type
# (SqlColumnHandlerMixin); each item type here is the one ColumnTypeParser maps to the row's DataType.
VECTOR_ELEMENT_TYPES: dict[str, VectorElement] = {
    "DOUBLE": VectorElement(DataType.DOUBLE, sqltypes.DOUBLE),
    "FLOAT": VectorElement(DataType.FLOAT, sqltypes.FLOAT),
    "DECIMAL": VectorElement(DataType.DECIMAL, sqltypes.DECIMAL),
    "INT": VectorElement(DataType.INT, sqltypes.INTEGER),
    "INTEGER": VectorElement(DataType.INT, sqltypes.INTEGER),
    "STRING": VectorElement(DataType.STRING, sqltypes.String),
}


class VectorFacts(NamedTuple):
    element: str  # the DATATYPE parameter, upper case
    dimension: int


def parse_vector_parameters(raw: str | None) -> VectorFacts | None:
    """
    A %Library.Vector property's Parameters ("DATATYPE,DOUBLE,LEN,3"): comma-separated key/value pairs, keys matched
    case-insensitively. None when DATATYPE or a positive LEN is missing, or the pairs do not pair up.
    """
    items = [item.strip() for item in (raw or "").split(",")]
    if len(items) < 2 or len(items) % 2:
        return None
    pairs = {key.upper(): value for key, value in zip(items[0::2], items[1::2], strict=True)}
    element, length = pairs.get("DATATYPE", ""), pairs.get("LEN", "")
    if not element or not length.isdigit() or int(length) <= 0:
        return None
    return VectorFacts(element.upper(), int(length))


def resolve_vector(facts: VectorFacts) -> ResolvedType:
    """ARRAY of the element type, shown as VECTOR(<TYPE>, <dim>) (ADR-0007). An unknown element is ARRAY of UNKNOWN."""
    element = VECTOR_ELEMENT_TYPES.get(facts.element)
    if element is None:
        return ResolvedType(sqltypes.ARRAY(iris_unmapped_type()), f"VECTOR({facts.element}, {facts.dimension})", False)
    return ResolvedType(
        sqltypes.ARRAY(element.item_type()), f"VECTOR({element.data_type.value}, {facts.dimension})", known=True
    )


_NATIVE_VECTOR = re.compile(r"^\s*vector\s*(?:\(\s*(\w+)\s*,\s*(\d+)\s*\))?\s*$", re.IGNORECASE)


def native_vector(raw: str) -> ResolvedType | None:
    """
    FR-009: a DATA_TYPE that names VECTOR, which no IRIS release reports yet, is cataloged as ARRAY from the catalog's
    own text, shown as that text; without element and dimension in it, ARRAY of UNKNOWN. None for any other type.
    """
    match = _NATIVE_VECTOR.match(raw)
    if match is None:
        return None
    element = VECTOR_ELEMENT_TYPES.get((match[1] or "").upper())
    item_type = element.item_type() if element is not None else iris_unmapped_type()
    return ResolvedType(sqltypes.ARRAY(item_type), raw, known=True)


def vector_grant_message(username: str, reason: str | None = None) -> str:
    """The one hint per run when the dictionary cannot be read (review decision of 2026-11-26: conditional text)."""
    message = (
        f"IRIS-VECTOR-GRANT: if this Namespace has VECTOR columns, GRANT SELECT ON %Dictionary.PropertyDefinition "
        f"TO {username} to catalog their element type and dimension"
    )
    return f"{message} — {reason}" if reason else message


def vector_params_message(raw: str | None) -> str:
    return f"IRIS-VECTOR-PARAMS: could not parse VECTOR parameters '{raw}'; cataloged as VARCHAR"


def vector_element_message(element: str) -> str:
    return f"IRIS-VECTOR-PARAMS: VECTOR element type '{element}' is not mapped; cataloged as ARRAY of UNKNOWN"
