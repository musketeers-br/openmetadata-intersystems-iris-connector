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
Spec 006, User Story 1: the profiler on the IRIS fixtures gives the values derived from the fixture rows
(tests/integration/iris/data/expected.py), on every cell and for every login.
"""

import pytest

from tests.integration.iris import profiler_harness as harness
from tests.integration.iris.data import expected

pytestmark = pytest.mark.iris


def test_harness_smoke(iris_service_connection, om_client):
    table, _, _ = harness.profile(iris_service_connection, om_client, "Clinic.Patient")
    assert table["rowCount"] == expected.ROW_COUNTS[("Clinic", "Patient")]
