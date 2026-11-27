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
Spec 006, User Story 3: sampling on IRIS through the IRIS sampler (ADR-0016). Row-count sampling works on every
table, randomized requests run unrandomized with one warning per run, percentage requests skip the table with one
warning per run, and no query reads a skipped table.
"""

import pytest

from metadata.generated.schema.type.basic import ProfileSampleType
from metadata.generated.schema.type.samplingConfig import SampleConfigType
from metadata.generated.schema.type.staticSamplingConfig import StaticSamplingConfig
from metadata.ingestion.source.database.iris.sampler import IrisSamplingSkipped
from metadata.sampler.models import ProfileSampleConfig, SampleConfig
from tests.integration.iris import profiler_harness as harness
from tests.integration.iris.data import expected

pytestmark = pytest.mark.iris

# Clinic.Patient's MD5 digest starts with a digit, Clinic.Encounter's with a letter (research R6).
TABLES = ("Clinic.Patient", "Clinic.Encounter", "Types.AllTypes")
KEY_COLUMN = {"Clinic.Patient": "PatientId", "Clinic.Encounter": "EncounterId", "Types.AllTypes": "Id"}
UNSUPPORTED = "IRIS-PROFILER-UNSUPPORTED"


def _config(kind, amount, randomized=False) -> SampleConfig:
    return SampleConfig(
        profileSampleConfig=ProfileSampleConfig(
            sampleConfigType=SampleConfigType.STATIC,
            config=StaticSamplingConfig(profileSampleType=kind, profileSample=amount),
        ),
        randomizedSample=randomized,
    )


def _rows_seen(connection, client, qualified, config) -> int:
    columns = harness.profile_metrics(connection, client, qualified, ("valuesCount",), sample_config=config)
    return columns[KEY_COLUMN[qualified]]["valuesCount"]


def _table_rows(qualified: str) -> int:
    return expected.ROW_COUNTS.get(tuple(qualified.split(".")), 1)


@pytest.mark.parametrize("randomized", [False, True], ids=["not-randomized", "randomized"])
def test_row_count_sampling(iris_service_connection, run_status, randomized):
    client = harness.StubClient()
    for qualified in TABLES:
        assert _rows_seen(iris_service_connection, client, qualified, _config(ProfileSampleType.ROWS, 10, randomized)) == min(
            10, _table_rows(qualified)
        ), qualified
    warnings = harness.warnings_with(run_status, UNSUPPORTED)
    if randomized:
        assert len(warnings) == 1, warnings
        assert "randomized sampling is not supported on IRIS" in warnings[0]
    else:
        assert warnings == []


def test_row_count_larger_than_the_table(iris_service_connection, run_status):
    config = _config(ProfileSampleType.ROWS, 1000)
    assert _rows_seen(iris_service_connection, harness.StubClient(), "Clinic.Patient", config) == _table_rows("Clinic.Patient")
    assert harness.warnings_with(run_status, UNSUPPORTED) == []


def test_percentage_sampling_skips_the_table(iris_service_connection, run_status):
    client = harness.StubClient()
    with harness.count_statements() as statements:
        for qualified in TABLES:
            with pytest.raises(IrisSamplingSkipped, match=f"{harness.table_fqn(qualified)} was not profiled"):
                harness.profile(iris_service_connection, client, qualified, _config(ProfileSampleType.PERCENTAGE, 50))
    reads = [s for s in statements if any(t.split(".")[1] in s for t in TABLES) and "TOP 0" not in s.upper()]
    assert reads == [], reads
    warnings = harness.warnings_with(run_status, UNSUPPORTED)
    assert len(warnings) == 1 and "percentage sampling is not supported on IRIS" in warnings[0], warnings


def test_percentage_100_is_the_whole_table(iris_service_connection, run_status):
    config = _config(ProfileSampleType.PERCENTAGE, 100)
    assert _rows_seen(iris_service_connection, harness.StubClient(), "Clinic.Patient", config) == _table_rows("Clinic.Patient")
    assert harness.warnings_with(run_status, UNSUPPORTED) == []


def test_the_test_runner_uses_the_same_sampler(iris_service_connection, run_status):
    """US3 scenario 5: data-quality tests on a sampled table, with the same rows and warnings."""
    client = harness.StubClient()
    status, text = harness.run_test_case(
        iris_service_connection, client, "Clinic.Patient", None, "tableRowCountToEqual", {"value": "10"},
        sample_config=_config(ProfileSampleType.ROWS, 10, randomized=True),
    )
    assert status == "Success", text
    assert len(harness.warnings_with(run_status, UNSUPPORTED)) == 1
    with pytest.raises(IrisSamplingSkipped):
        harness.run_test_case(
            iris_service_connection, client, "Clinic.Patient", None, "tableRowCountToEqual", {"value": "10"},
            sample_config=_config(ProfileSampleType.PERCENTAGE, 50),
        )
    assert len(harness.warnings_with(run_status, UNSUPPORTED)) == 2
