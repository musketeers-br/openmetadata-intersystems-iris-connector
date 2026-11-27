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
(tests/integration/iris/data/expected.py), on every cell and for every login. No sampling here (test_sampling.py).
"""

import datetime
import math
import re

import pytest
from sqlalchemy import text
from tests.integration.iris import profiler_harness as harness
from tests.integration.iris.data import expected

pytestmark = pytest.mark.iris

TABLES = [f"{schema}.{table}" for schema, table in expected.COLUMNS]


def _same(actual, wanted) -> bool:
    if wanted is None or actual is None:
        return actual is wanted
    if isinstance(wanted, datetime.datetime):
        return str(actual)[:19] == wanted.isoformat(sep=" ")[:19]
    if isinstance(wanted, datetime.date):
        return str(actual)[:10] == wanted.isoformat()
    return math.isclose(float(actual), float(wanted), rel_tol=1e-6, abs_tol=1e-6)


@pytest.fixture(scope="module")
def profiles(iris_service_connection):
    """One unsampled default profile per table, shared by the tests of this module."""
    client = harness.StubClient()
    return {qualified: harness.profile(iris_service_connection, client, qualified) for qualified in TABLES}


@pytest.mark.parametrize("qualified", TABLES)
def test_table_metrics(profiles, qualified):
    table, _, _ = profiles[qualified]
    key = tuple(qualified.split("."))
    assert table["rowCount"] == expected.ROW_COUNTS[key]
    assert table["columnCount"] == expected.COLUMN_COUNTS[key]


@pytest.mark.parametrize(
    "qualified,column",
    [(f"{s}.{t}", c) for (s, t), columns in expected.COLUMNS.items() for c, _, _ in columns],
)
def test_column_metrics(profiles, qualified, column):
    _, columns, _ = profiles[qualified]
    schema, table = qualified.split(".")
    wanted = {m: v for m, v in expected.METRICS[(schema, table, column)].items() if m in expected.DEFAULT_METRICS}
    got = columns.get(column, {})
    wrong = {m: (got.get(m), v) for m, v in wanted.items() if not _same(got.get(m), v)}
    assert not wrong, f"{qualified}.{column}: metric -> (actual, expected): {wrong}"


@pytest.mark.parametrize("qualified", TABLES)
def test_metrics_outside_the_default_profiler(iris_service_connection, qualified):
    """duplicateCount, minLength and maxLength, which a profiler configuration can ask for."""
    columns = harness.profile_metrics(iris_service_connection, harness.StubClient(), qualified, expected.EXTRA_METRICS)
    schema, table = qualified.split(".")
    for column, _, _ in expected.COLUMNS[(schema, table)]:
        wanted = {m: v for m, v in expected.METRICS[(schema, table, column)].items() if m in expected.EXTRA_METRICS}
        got = columns.get(column, {})
        wrong = {m: (got.get(m), v) for m, v in wanted.items() if not _same(got.get(m), v)}
        assert not wrong, f"{qualified}.{column}: metric -> (actual, expected): {wrong}"


def test_median_and_quartiles_of_weight(profiles):
    """The values the IRIS median override gives (spec FR-002), checked on their own so a failure names them."""
    _, columns, _ = profiles["Clinic.Patient"]
    wanted = expected.METRICS[("Clinic", "Patient", "Weight")]
    for metric in ("median", "firstQuartile", "thirdQuartile", "interQuartileRange", "nonParametricSkew"):
        assert _same(columns["Weight"].get(metric), wanted[metric]), metric


def test_no_failure_on_the_non_stream_columns(profiles):
    """Only the stream column of Clinic.Encounter and the histogram may fail (spec FR-012)."""
    for qualified in TABLES:
        _, _, failures = profiles[qualified]
        unexpected = [f.error for f in failures if "Notes" not in f.error and "histogram" not in f.error.lower()]
        assert not unexpected, f"{qualified}: {unexpected}"


def test_all_null_column(iris_cell, iris_admin_service_connection, iris_admin_engine):
    """An all-NULL numeric column: counts as on other databases, and the median does not fail."""
    if not iris_cell.is_admin:
        pytest.skip(f"{iris_cell.name}: creates a Scratch table, which only the administrator can read")
    with iris_admin_engine.begin() as conn:
        conn.execute(text("CREATE TABLE Scratch.AllNull (Id INT PRIMARY KEY, Val NUMERIC(5,2))"))
        conn.execute(text("INSERT INTO Scratch.AllNull (Id) VALUES (1)"))
        conn.execute(text("INSERT INTO Scratch.AllNull (Id) VALUES (2)"))
    harness.TABLES["Scratch.AllNull"] = [("Id", harness.DataType.INT), ("Val", harness.DataType.NUMERIC)]
    try:
        _, columns, failures = harness.profile(iris_admin_service_connection, harness.StubClient(), "Scratch.AllNull")
    finally:
        harness.TABLES.pop("Scratch.AllNull")
        with iris_admin_engine.begin() as conn:
            conn.execute(text("DROP TABLE Scratch.AllNull"))
    assert columns["Val"]["nullCount"] == 2
    assert columns["Val"]["valuesCount"] == 0
    assert columns["Val"].get("median") is None
    assert not failures, [f.error for f in failures]


# --- spec 006 User Story 4: unreadable tables and the success threshold ---


def test_unreadable_table_is_skipped_with_one_access_warning(iris_cell, iris_service_connection, run_status):
    """FR-013a: Restricted.Secret is visible to the readers but not readable; Restricted.ColumnGrant is cataloged
    with the one column they may read, so it is profiled on that column."""
    from metadata.ingestion.source.database.iris.sampler import IrisSamplingSkippedError

    client = harness.StubClient()
    if iris_cell.is_admin:
        _, columns, _ = harness.profile(iris_service_connection, client, "Restricted.Secret")
        assert columns["Id"]["valuesCount"] == 1
        assert harness.warnings_with(run_status, "IRIS-ACCESS") == []
        return
    with harness.count_statements() as statements:
        for _ in range(2):  # the same table twice in a run: still one warning
            with pytest.raises(
                IrisSamplingSkippedError, match=re.escape("IRIS-ACCESS: cannot read profile of Restricted.Secret")
            ):
                harness.profile(iris_service_connection, client, "Restricted.Secret")
    # Only the readability check (SELECT TOP ? <cataloged columns>, limit 0) touched the table.
    assert [s for s in statements if "Secret" in s and not s.upper().startswith("SELECT TOP ?")] == []
    access = harness.warnings_with(run_status, "IRIS-ACCESS")
    assert len(access) == 1 and access[0].startswith("IRIS-ACCESS: cannot read profile of Restricted.Secret: "), access
    _, columns, failures = harness.profile(iris_service_connection, client, "Restricted.ColumnGrant")
    assert columns["Id"]["valuesCount"] == 1
    # IRIS refuses COUNT(*) without a table-level SELECT: the row count is the one failure, with the IRIS error.
    assert len(failures) == 1 and "<-99>" in failures[0].error and "count(*)" in failures[0].error, failures


def test_run_meets_the_success_threshold(iris_cell, iris_service_connection, run_status):
    """
    FR-013: a profiler run over every fixture table the login sees completes and meets the default threshold (90%).
    The step's records and failures are counted as ProfilerProcessor._run copies them, and a table the sampler skips
    counts as one failure, as Step.run records it (T-probe).
    """
    from metadata.ingestion.source.database.iris.sampler import IrisSamplingSkippedError

    tables = list(harness.PROFILED) + list(harness.RESTRICTED) + ["AI.Embedding"]
    vector = harness.DataType.ARRAY if iris_cell.has_dict_grant else harness.DataType.VARCHAR
    harness.TABLES["AI.Embedding"] = [("Id", harness.DataType.INT), ("Content", harness.DataType.VARCHAR)] + [
        (c, vector, harness.DataType.DOUBLE) if vector == harness.DataType.ARRAY else (c, vector)
        for c in ("Vec", "Vec4", "vec_low")
    ]
    records, failures, skipped, failed_on = 0, 0, [], []
    client = harness.StubClient()
    try:
        for qualified in tables:
            interface = None
            try:
                interface = harness.profiler_interface(iris_service_connection, client, qualified)
            except IrisSamplingSkippedError:
                failures += 1
                skipped.append(qualified)
                continue
            try:
                # Without the dictionary grant VECTOR columns look like VARCHAR and their metrics fail (research);
                # the docs tell such users to exclude them, as this run does.
                exclude = (
                    ["Vec", "Vec4", "vec_low"] if qualified == "AI.Embedding" and not iris_cell.has_dict_grant else None
                )
                harness.DefaultProfiler(
                    profiler_interface=interface, metrics_registry=harness.Metrics, exclude_columns=exclude
                ).compute_metrics()
                records += len(interface.status.records)
                failures += len(interface.status.failures)
                failed_on += [f.error.split(" metric_type")[0] for f in interface.status.failures]
            finally:
                harness.release(interface)
    finally:
        harness.TABLES.pop("AI.Embedding")
    ratio = 100 * records / (records + failures)
    assert ratio >= 90, (
        f"{iris_cell.name}: {ratio:.1f}% (records={records}, failures={failures}, skipped={skipped}, "
        f"failed_on={sorted(failed_on)})"
    )
    assert skipped == ([] if iris_cell.is_admin else ["Restricted.Secret"])
