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
Spec 006: the profiler and data-quality values expected on the shared fixtures, derived from the loader's own
row generator (seed.clinic_rows), never typed in by hand.

Metric semantics follow OpenMetadata 2.1.1: text columns get min, max, mean, sum and standard deviation of their
value length; standard deviation is the population one (STDDEV_POP); median and quartiles are the discrete
percentile of the IRIS override (the non-NULL value at position ROUND(p * n, 0), counting from 1); proportions
are over the non-NULL values, except null proportion, which is over the row count.
"""

import datetime
import json
import math
from dataclasses import dataclass, field
from statistics import pstdev

from tests.integration.iris.data.seed import NAMES, clinic_rows

PATIENTS, ENCOUNTERS = clinic_rows()

# (schema, table) -> [(column, kind, values)]; kind is number, text, date, timestamp or bool. Stream columns
# (Clinic.Encounter.Notes) are not profiled on IRIS (spec 006 FR-012) and are left out.
COLUMNS = {
    ("Clinic", "Patient"): [
        ("PatientId", "number", [r[0] for r in PATIENTS]),
        ("FullName", "text", [r[1] for r in PATIENTS]),
        ("BirthDate", "date", [r[2] for r in PATIENTS]),
        ("Weight", "number", [r[3] for r in PATIENTS]),
    ],
    ("Clinic", "Encounter"): [
        ("EncounterId", "number", [r[0] for r in ENCOUNTERS]),
        ("PatientId", "number", [r[1] for r in ENCOUNTERS]),
        ("StartedAt", "timestamp", [r[2] for r in ENCOUNTERS]),
        ("Active", "bool", [r[4] for r in ENCOUNTERS]),
    ],
}
ROW_COUNTS = {("Clinic", "Patient"): len(PATIENTS), ("Clinic", "Encounter"): len(ENCOUNTERS)}
COLUMN_COUNTS = {("Clinic", "Patient"): 4, ("Clinic", "Encounter"): 5}


def percentile(values: list, p: float):
    """The IRIS median override: the value at position ROUND(p * n, 0) of the sorted non-NULL values."""
    ordered = sorted(v for v in values if v is not None)
    position = math.floor(p * len(ordered) + 0.5)
    return ordered[position - 1] if position >= 1 else None


def _parse(kind: str, value):
    if value is None:
        return None
    if kind == "date":
        return datetime.date.fromisoformat(value)
    if kind == "timestamp":
        return datetime.datetime.fromisoformat(value)
    return value


def column_metrics(kind: str, values: list) -> dict:
    """Every supported metric of the matrix for one column, by OpenMetadata's definitions."""
    present = [_parse(kind, v) for v in values if v is not None]
    counts = {}
    for v in present:
        counts[v] = counts.get(v, 0) + 1
    unique = sum(1 for c in counts.values() if c == 1)
    metrics = {
        "valuesCount": len(present),
        "nullCount": len(values) - len(present),
        "nullProportion": (len(values) - len(present)) / len(values),
        "distinctCount": len(counts),
        "distinctProportion": len(counts) / len(present),
        "uniqueCount": unique,
        "uniqueProportion": unique / len(present),
        "duplicateCount": len(present) - len(counts),
    }
    if kind in ("number", "text"):
        # Text columns: every quantity is over the value length (OpenMetadata wraps the column in LEN).
        numbers = present if kind == "number" else [len(v) for v in present]
        mean, std = sum(numbers) / len(numbers), pstdev(numbers)
        q1, median, q3 = (percentile(numbers, p) for p in (0.25, 0.5, 0.75))
        metrics.update(
            min=min(numbers),
            max=max(numbers),
            mean=mean,
            # OpenMetadata's generic SUM is SUM(CAST(x AS BIGINT)); IRIS's CAST to BIGINT truncates each value.
            sum=sum(math.trunc(v) for v in numbers),
            stddev=std,
            firstQuartile=q1,
            median=median,
            thirdQuartile=q3,
            interQuartileRange=q3 - q1,
            nonParametricSkew=(mean - median) / std if std else None,
        )
        if kind == "text":
            metrics.update(minLength=min(numbers), maxLength=max(numbers))
    elif kind in ("date", "timestamp"):
        metrics.update(min=min(present), max=max(present))
    return metrics


# The column metrics of OpenMetadata's default profiler (profiler/processor/default.py); the others of the matrix
# (duplicateCount, minLength, maxLength) are computed by asking for them.
DEFAULT_METRICS = (
    "median", "firstQuartile", "thirdQuartile", "mean", "valuesCount", "distinctCount", "distinctProportion",
    "min", "max", "nullCount", "nullProportion", "stddev", "sum", "uniqueCount", "uniqueProportion",
    "interQuartileRange", "nonParametricSkew",
)
EXTRA_METRICS = ("duplicateCount", "minLength", "maxLength")

METRICS = {
    (schema, table, column): column_metrics(kind, values)
    for (schema, table), columns in COLUMNS.items()
    for column, kind, values in columns
}


def _values(table: str, column: str) -> list:
    return next(v for c, _, v in COLUMNS[("Clinic", table)] if c == column)


@dataclass(frozen=True)
class Case:
    """One built-in test with parameters that must give Success and parameters that must give Failed."""

    definition: str
    table: str  # schema-qualified
    column: str | None
    passing: dict = field(default_factory=dict)
    failing: dict | None = None  # None: the failing case uses another column (failing_column)
    failing_column: str | None = None
    advanced: bool = False  # spec 006 cut candidate (median, mean, stddev, sum, lengths between)


def _num(value) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _epoch_ms(value: datetime.datetime) -> str:
    return str(int(value.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000))


_P, _E = ROW_COUNTS[("Clinic", "Patient")], ROW_COUNTS[("Clinic", "Encounter")]
_W = METRICS[("Clinic", "Patient", "Weight")]
_N = METRICS[("Clinic", "Patient", "FullName")]
_S = METRICS[("Clinic", "Encounter", "StartedAt")]
_BIRTH_NULLS = METRICS[("Clinic", "Patient", "BirthDate")]["nullCount"]


def _around(value, margin: float = 0.5) -> tuple[str, str]:
    return _num(value - margin), _num(value + margin)


def _between(prefix: str, value) -> tuple[dict, dict]:
    """Parameters `minValueFor<prefix>` / `maxValueFor<prefix>` around a value, and a window just above it."""
    low, high = _around(value)
    passing = {f"minValueFor{prefix}": low, f"maxValueFor{prefix}": high}
    failing = {f"minValueFor{prefix}": _num(value + 1), f"maxValueFor{prefix}": _num(value + 2)}
    return passing, failing


TABLE_CASES = [
    Case("tableRowCountToBeBetween", "Clinic.Patient", None,
         {"minValue": str(_P - 1), "maxValue": str(_P + 1)}, {"minValue": str(_P + 1), "maxValue": str(_P + 10)}),
    Case("tableRowCountToEqual", "Clinic.Patient", None, {"value": str(_P)}, {"value": str(_P + 1)}),
    Case("tableColumnCountToBeBetween", "Clinic.Patient", None,
         {"minColValue": "1", "maxColValue": "4"}, {"minColValue": "5", "maxColValue": "9"}),
    Case("tableColumnCountToEqual", "Clinic.Patient", None, {"columnCount": "4"}, {"columnCount": "5"}),
    Case("tableColumnNameToExist", "Clinic.Patient", None, {"columnName": "FullName"}, {"columnName": "Nobody"}),
    Case("tableColumnToMatchSet", "Clinic.Patient", None,
         {"columnNames": "PatientId,FullName,BirthDate,Weight", "ordered": "false"},
         {"columnNames": "PatientId,FullName", "ordered": "false"}),
    Case("tableCustomSQLQuery", "Clinic.Patient", None,
         {"sqlExpression": "SELECT * FROM Clinic.Patient WHERE Weight < 0", "strategy": "ROWS"},
         {"sqlExpression": "SELECT * FROM Clinic.Patient WHERE Weight IS NULL", "strategy": "ROWS"}),
]

COLUMN_CASES = [
    Case("columnValuesToBeNotNull", "Clinic.Patient", "FullName", failing_column="BirthDate"),
    Case("columnValuesToBeUnique", "Clinic.Patient", "PatientId", failing_column="FullName"),
    Case("columnValuesMissingCount", "Clinic.Patient", "BirthDate",
         {"missingCountValue": str(_BIRTH_NULLS)}, {"missingCountValue": "0"}),
    Case("columnValuesToBeBetween", "Clinic.Patient", "Weight",
         {"minValue": _num(_W["min"]), "maxValue": _num(_W["max"])},
         {"minValue": _num(_W["min"] + 1), "maxValue": _num(_W["max"])}),
    Case("columnValuesToBeBetween", "Clinic.Encounter", "StartedAt",
         {"minValue": _epoch_ms(_S["min"]), "maxValue": _epoch_ms(_S["max"])},
         {"minValue": _epoch_ms(_S["min"] + datetime.timedelta(hours=1)), "maxValue": _epoch_ms(_S["max"])}),
    # matchEnum: every value must be in the set (without it the test passes when any value is).
    Case("columnValuesToBeInSet", "Clinic.Patient", "FullName",
         {"allowedValues": json.dumps(list(NAMES)), "matchEnum": "true"},
         {"allowedValues": json.dumps(list(NAMES[:2])), "matchEnum": "true"}),
    Case("columnValuesToBeNotInSet", "Clinic.Patient", "FullName",
         {"forbiddenValues": json.dumps(["Nobody"])}, {"forbiddenValues": json.dumps(["Ana Souza"])}),
]

_ADVANCED = [
    ("columnValueMaxToBeBetween", "MaxInCol", _W["max"]),
    ("columnValueMinToBeBetween", "MinInCol", _W["min"]),
    ("columnValueMeanToBeBetween", "MeanInCol", _W["mean"]),
    ("columnValueMedianToBeBetween", "MedianInCol", _W["median"]),
    ("columnValueStdDevToBeBetween", "StdDevInCol", _W["stddev"]),
]
ADVANCED_CASES = [
    Case(definition, "Clinic.Patient", "Weight", *_between(prefix, value), advanced=True)
    for definition, prefix, value in _ADVANCED
] + [
    Case("columnValuesSumToBeBetween", "Clinic.Patient", "Weight",
         {"minValueForColSum": _num(_W["sum"] - 1), "maxValueForColSum": _num(_W["sum"] + 1)},
         {"minValueForColSum": _num(_W["sum"] + 1), "maxValueForColSum": _num(_W["sum"] + 2)}, advanced=True),
    Case("columnValueLengthsToBeBetween", "Clinic.Patient", "FullName",
         {"minLength": str(_N["minLength"]), "maxLength": str(_N["maxLength"])},
         {"minLength": str(_N["minLength"] + 1), "maxLength": str(_N["maxLength"])}, advanced=True),
]

# Spec 006 FR-012a: aborted by the IRIS test-suite interface, never a pass or fail verdict.
ABORTED_CASES = [
    Case("columnValuesToMatchRegex", "Clinic.Patient", "FullName", {"regex": "^[A-Z][a-z]+ [A-Z][a-z]+$"}),
    Case("columnValuesToNotMatchRegex", "Clinic.Patient", "FullName", {"forbiddenRegex": "[0-9]"}),
    Case("columnValuesToBeInSet", "Clinic.Encounter", "Notes", {"allowedValues": json.dumps(["checkup"])}),
    Case("columnValuesToBeNotInSet", "Clinic.Encounter", "Notes", {"forbiddenValues": json.dumps(["none"])}),
    Case("columnValueLengthsToBeBetween", "Clinic.Encounter", "Notes", {"minLength": "1", "maxLength": "50"}),
    Case("columnValuesToBeUnique", "Clinic.Encounter", "Notes"),
    Case("columnValuesMissingCount", "Clinic.Encounter", "Notes", {"missingCountValue": "7"}),
]

# Hand-counted from the generator's rules (seed.clinic_rows), to check this module against something it did not
# compute: BirthDate is NULL for 10, 20, ..., 60; the 12 names cycle; Notes is 'checkup' for every third id from
# 12 that is not a multiple of 8, plus id 10.
HAND_COUNTS = {
    ("Clinic", "Patient", "BirthDate", "nullCount"): 6,
    ("Clinic", "Patient", "FullName", "distinctCount"): 12,
    ("Clinic", "Encounter", "Notes", "checkup"): 1 + len([e for e in range(12, 70, 3) if e % 8]),
}


def notes_checkup_count() -> int:
    return sum(1 for r in ENCOUNTERS if r[3] == "checkup")


def weight_values() -> list:
    return _values("Patient", "Weight")
