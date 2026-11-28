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
Spec 006, User Story 2: every supported built-in test gives Success with parameters that must pass and Failed
with parameters that must fail, on every cell and for every login (expected.py derives both from the fixture rows).
"""

import pytest
from tests.integration.iris import profiler_harness as harness
from tests.integration.iris.data import expected

pytestmark = pytest.mark.iris


def _id(case: expected.Case) -> str:
    return f"{case.definition}-{case.table}.{case.column or 'table'}"


def _check(connection, case: expected.Case):
    client = harness.StubClient()
    status, text = harness.run_test_case(connection, client, case.table, case.column, case.definition, case.passing)
    assert status == "Success", f"{_id(case)} passing case: {status} {text[:300]}"
    column = case.failing_column or case.column
    params = case.failing if case.failing is not None else case.passing
    status, text = harness.run_test_case(connection, client, case.table, column, case.definition, params)
    assert status == "Failed", f"{_id(case)} failing case: {status} {text[:300]}"


@pytest.mark.parametrize("case", expected.TABLE_CASES, ids=_id)
def test_table_tests(iris_service_connection, case):
    _check(iris_service_connection, case)


@pytest.mark.parametrize("case", expected.COLUMN_CASES, ids=_id)
def test_basic_column_tests(iris_service_connection, case):
    _check(iris_service_connection, case)


@pytest.mark.parametrize("case", expected.ADVANCED_CASES, ids=_id)
def test_advanced_column_tests(iris_service_connection, case):
    """Spec 006 cut candidate: median, mean, standard deviation, sum, max, min and value lengths between."""
    _check(iris_service_connection, case)


def test_aborted_tests(iris_service_connection, run_status):
    """
    Spec 006 FR-012a: the regex tests (any column) and in set, not in set, value lengths, unique and missing count on
    a stream column end Aborted with the reason, never with a verdict, and one warning per test type per run. The
    other tests of the same run keep their verdicts.
    """
    client = harness.StubClient()
    for case in expected.ABORTED_CASES:
        status, text = harness.run_test_case(
            iris_service_connection, client, case.table, case.column, case.definition, case.passing
        )
        assert status == "Aborted", f"{_id(case)}: {status} {text[:200]}"
        assert text.startswith(f"IRIS-PROFILER-UNSUPPORTED: test {case.definition} on "), text
    warnings = harness.warnings_with(run_status, "IRIS-PROFILER-UNSUPPORTED: test ")
    assert len(warnings) == len({c.definition for c in expected.ABORTED_CASES}), warnings
    status, _ = harness.run_test_case(
        iris_service_connection, client, "Clinic.Encounter", "Notes", "columnValuesToBeNotNull", {}
    )
    assert status == "Failed"  # not null is supported on streams: Notes has NULLs
