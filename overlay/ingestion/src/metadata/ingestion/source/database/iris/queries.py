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
InterSystems IRIS SQL queries: module-level constants with bind parameters, no logic.
"""

# --- 000: connection ---

# Plain-SQL server version for the dialect state preset (ADR-0015, GAP-004).
IRIS_ZVERSION = "SELECT $ZVERSION"

# Real read of the dictionary, used for the dialect preset (GAP-005) and the optional Test connection step.
IRIS_CLASS_DICTIONARY_PROBE = "SELECT TOP 1 Name FROM %Dictionary.PropertyDefinition"

# --- 002: catalog ---

# Unique constraints: with dictionary access the inspector reads %Dictionary.IndexDefinition, which a login
# holding only the documented dictionary grants cannot read (GAP-010). Joined on schema AND name.
IRIS_UNIQUE_CONSTRAINTS = (
    "SELECT tc.CONSTRAINT_NAME, k.COLUMN_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc "
    "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE k ON k.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA "
    "AND k.CONSTRAINT_NAME = tc.CONSTRAINT_NAME AND k.TABLE_SCHEMA = tc.TABLE_SCHEMA AND k.TABLE_NAME = tc.TABLE_NAME "
    "WHERE tc.CONSTRAINT_TYPE = 'UNIQUE' AND tc.TABLE_SCHEMA = :schema AND tc.TABLE_NAME = :table "
    "ORDER BY tc.CONSTRAINT_NAME, k.ORDINAL_POSITION"
)

# --- 003: type map ---

# Raw column types for the type map (ADR-0006): the dialect's reflected types are wrong for VARCHAR(1) and lose
# the name of an unknown type (GAP-008). Bound on the exact (schema, table); callers keep exact-case matches.
IRIS_COLUMN_TYPES = (
    "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, "
    "NUMERIC_SCALE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table"
)

# --- 004: dictionary / VECTOR enrichment ---

# --- 005: access gaps ---

# Readability check (spec 005, research R2): every catalog read succeeds on a table the login holds only REFERENCES or
# a column-level SELECT on, so only a read of the rows tells. TOP 0 prepares the statement and reads no row. Filled
# with identifiers quoted by the dialect; run once per cataloged table and view.
IRIS_READ_PROBE = "SELECT TOP 0 * FROM {schema}.{table}"

# --- 010: query log ---
