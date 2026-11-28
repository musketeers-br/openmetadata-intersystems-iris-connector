#!/usr/bin/env python3
"""What INFORMATION_SCHEMA.COLUMNS.DATA_TYPE reports on one IRIS instance (spec 003, research R1).

For every candidate DDL type, create a one-column table in Scratch, read what the catalog reports for
it, and drop it; then collect every distinct DATA_TYPE of the whole Namespace (system schemas
included). Run it when a release track moves, to find a type the map does not have yet.

    IRIS_PORT=11972 python fixtures/iris/discover_types.py            # report
    IRIS_PORT=11972 .om/env/bin/python fixtures/iris/discover_types.py --check

--check needs the connector (run it with .om/env/bin/python): exit 1, naming each DATA_TYPE that
IRIS_TYPES in iris/types.py does not map. Uses the admin login (IRIS_ADMIN_USER / IRIS_ADMIN_PASSWORD),
IRIS_HOST (127.0.0.1), IRIS_PORT (1972) and IRIS_NAMESPACE (USER). Never leaves a table behind.
"""
import collections
import os
import sys

CANDIDATES = (
    "BIGINT", "BINARY(8)", "BINARY VARYING(8)", "BIT", "BLOB", "BOOLEAN", "CHAR", "CHAR(10)", "CHAR VARYING(10)",
    "CHARACTER(10)", "CHARACTER VARYING(10)", "CLOB", "DATE", "DATETIME", "DATETIME2", "DEC(7,3)", "DECIMAL(7,3)",
    "DOUBLE", "DOUBLE PRECISION", "FLOAT", "FLOAT(10)", "IMAGE", "INT", "INTEGER", "LONG", "LONG BINARY", "LONG RAW",
    "LONG VARCHAR", "LONGTEXT", "LONGVARBINARY", "LONGVARCHAR", "MEDIUMINT", "MEDIUMTEXT", "MONEY",
    "NATIONAL CHAR(10)", "NATIONAL CHARACTER VARYING(10)", "NATIONAL VARCHAR(10)", "NCHAR(10)", "NTEXT", "NUMBER",
    "NUMBER(7,3)", "NUMERIC", "NUMERIC(7,3)", "NVARCHAR(10)", "POSIXTIME", "RAW(8)", "REAL", "ROWVERSION", "SERIAL",
    "SMALLDATETIME", "SMALLINT", "SMALLMONEY", "SYSNAME", "TEXT", "TIME", "TIME(3)", "TIMESTAMP", "TIMESTAMP2",
    "TINYINT", "UNIQUEIDENTIFIER", "VARBINARY", "VARBINARY(8)", "VARCHAR", "VARCHAR(1)", "VARCHAR(10)", "VARCHAR2(10)",
    "VECTOR(DOUBLE, 3)", "VECTOR(INT, 4)", "VECTOR(DECIMAL, 2)", "VECTOR(STRING, 2)", "VECTOR(FLOAT, 2)", "JSON",
    "%Library.String", "%Library.String(MAXLEN=20)", "%Library.Integer", "%Library.BigInt", "%Library.SmallInt",
    "%Library.TinyInt", "%Library.Boolean", "%Library.Date", "%Library.Time", "%Library.TimeStamp",
    "%Library.PosixTime", "%Library.Numeric", "%Library.Decimal", "%Library.Double", "%Library.Float",
    "%Library.Currency", "%Library.Binary", "%Library.List", "%Library.ListOfDataTypes", "%Library.Status",
    "%Library.GlobalCharacterStream", "%Library.GlobalBinaryStream", "%Stream.GlobalCharacter",
    "%Stream.GlobalBinary", "%Library.UniqueIdentifier", "%Library.Vector", "%Library.DateTime",
    "%Library.StringTimeStamp", "%Library.Char", "%Library.Name", "%Library.Username", "%Library.FilemanDate",
    "%Library.FilemanTimeStamp", "%Library.EnumString",
)  # fmt: skip

TYPE_FACTS = (
    "SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE FROM INFORMATION_SCHEMA.COLUMNS "
    "WHERE TABLE_SCHEMA = 'Scratch' AND TABLE_NAME = ? AND COLUMN_NAME = 'C'"
)


def _say(text=""):
    sys.stdout.write(f"{text}\n")


def discover(cursor):
    """({ddl: catalog facts or error}, {DATA_TYPE: (column count, first column)})."""
    by_ddl = {}
    for number, ddl in enumerate(CANDIDATES):
        table = f"DiscoverType{number:03d}"
        try:
            cursor.execute(f"CREATE TABLE Scratch.{table} (C {ddl})")
        except Exception as exc:  # pylint: disable=broad-except
            by_ddl[ddl] = f"not accepted: {str(exc).splitlines()[0][:90]}"
            continue
        try:
            cursor.execute(TYPE_FACTS, [table])
            by_ddl[ddl] = tuple(cursor.fetchall()[0])
        finally:
            cursor.execute(f"DROP TABLE Scratch.{table}")
    counts, first = collections.Counter(), {}
    cursor.execute("SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS")
    for schema, table, column, data_type in cursor.fetchall():
        counts[data_type] += 1
        first.setdefault(data_type, f"{schema}.{table}.{column}")
    return by_ddl, {key: (counts[key], first[key]) for key in sorted(counts, key=str)}


def main(argv):
    import iris  # pylint: disable=import-outside-toplevel

    conn = iris.connect(
        os.environ.get("IRIS_HOST", "127.0.0.1"),
        int(os.environ.get("IRIS_PORT", "1972")),
        os.environ.get("IRIS_NAMESPACE", "USER"),
        os.environ.get("IRIS_ADMIN_USER", "_SYSTEM"),
        os.environ.get("IRIS_ADMIN_PASSWORD", "SYS"),
    )
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT $ZVERSION")
        _say(cursor.fetchone()[0])
        by_ddl, namespace = discover(cursor)
    finally:
        conn.close()
    for ddl, facts in by_ddl.items():
        _say(f"{ddl:32} {facts}")
    reported = {str(f[0]).lower() for f in by_ddl.values() if isinstance(f, tuple)} | {str(k).lower() for k in namespace}
    _say(f"\n{len(reported)} DATA_TYPE values: {', '.join(sorted(reported))}")
    for data_type, (count, column) in namespace.items():
        _say(f"  {data_type}: {count} columns, e.g. {column}")
    if "--check" not in argv:
        return 0
    from metadata.ingestion.source.database.iris.types import (  # pylint: disable=import-outside-toplevel
        IRIS_TYPES,
    )

    missing = sorted(reported - set(IRIS_TYPES))
    if missing:
        sys.stderr.write(f"discover_types: not in IRIS_TYPES: {', '.join(missing)}\n")
        return 1
    _say(f"discover_types: {len(reported)} DATA_TYPE values, all mapped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
