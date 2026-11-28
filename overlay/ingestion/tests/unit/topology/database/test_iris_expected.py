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
Spec 006 (T005): the expected-values module agrees with hand counts and with the loader's row counts.
No IRIS needed.
"""

from tests.integration.iris.data import expected
from tests.integration.iris.data.seed import EXPECTED, clinic_rows


def test_hand_counts():
    hand = expected.HAND_COUNTS
    assert (
        expected.METRICS[("Clinic", "Patient", "BirthDate")]["nullCount"]
        == hand[("Clinic", "Patient", "BirthDate", "nullCount")]
    )
    assert (
        expected.METRICS[("Clinic", "Patient", "FullName")]["distinctCount"]
        == hand[("Clinic", "Patient", "FullName", "distinctCount")]
    )
    assert expected.notes_checkup_count() == hand[("Clinic", "Encounter", "Notes", "checkup")]


def test_row_counts_match_the_loader():
    for key, count in expected.ROW_COUNTS.items():
        assert EXPECTED["rows"][key] == count


def test_generator_is_deterministic():
    assert clinic_rows() == clinic_rows()


def test_the_fixture_shapes_the_profiler_needs():
    weight = expected.METRICS[("Clinic", "Patient", "Weight")]
    assert weight["nullCount"] > 0 and weight["duplicateCount"] > 0
    assert any(v is not None and v != int(v) for v in expected.weight_values())
    assert expected.METRICS[("Clinic", "Patient", "FullName")]["duplicateCount"] > 0


def test_percentile_is_the_discrete_position():
    assert expected.percentile([4, None, 1, 3, 2], 0.5) == 2  # ROUND(0.5 * 4) = 2
    assert expected.percentile([1, 2, 3], 0.25) == 1  # ROUND(0.75) = 1
    assert expected.percentile([7], 0.25) is None  # ROUND(0.25) = 0: no row
    assert expected.percentile([None], 0.5) is None


def test_every_case_has_a_failing_side():
    for case in expected.TABLE_CASES + expected.COLUMN_CASES + expected.ADVANCED_CASES:
        assert case.failing is not None or case.failing_column, case.definition
