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
Metadata core ingestion against a real IRIS (spec 002).

Part A needs only an IRIS container with the shared fixtures: it drives the connector's catalog reads
(columns, keys, descriptions, view definitions, filters) directly, as the framework does per table.
Part B runs the real workflow and needs an OpenMetadata server built from the overlay (make om-image):
OM_HOST_PORT (e.g. http://localhost:8585/api) and OM_JWT; it is skipped otherwise.

The cell (release track x login) and the shared fixtures come from spec 001's conftest (`iris_cell`,
`iris_service_connection`, `iris_admin_engine`); the expected objects from `data/seed.py` (`EXPECTED`).
Tests create objects only in `Scratch` and never touch the sentinel `Scratch.Keep`.
"""

import os
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from tests.integration.iris.data.seed import EXPECTED

from metadata.generated.schema.entity.data.table import Constraint, ConstraintType, TableType
from metadata.generated.schema.type.filterPattern import FilterPattern
from metadata.ingestion.api.status import Status
from metadata.ingestion.source.database.iris.metadata import IrisSource
from metadata.utils.filters import filter_by_schema

pytestmark = pytest.mark.iris

SERVICE = "iris_test"
NAMESPACE = os.environ.get("IRIS_NAMESPACE", "USER")


@pytest.fixture(scope="module")
def source(iris_service_connection, iris_engine):
    source = IrisSource.__new__(IrisSource)
    source.service_connection = iris_service_connection
    source.engine = iris_engine
    source.status = Status()
    source.metadata = None
    source._connection_map = {}
    source._inspector_map = {}
    source.context = SimpleNamespace(
        get=lambda: SimpleNamespace(database_service=SERVICE, database=NAMESPACE, database_schema="Clinic"),
        get_current_thread_id=lambda: 1,
    )
    yield source
    source.connection.close()


def _table(source, schema, table, table_type=TableType.Regular):
    return source.get_columns_and_constraints(
        schema_name=schema,
        table_type=table_type,
        table_name=table,
        db_name=NAMESPACE,
        inspector=source.inspector,
    )


# --- Part A: catalog reads against IRIS -----------------------------------------------------------


class TestHierarchy:
    def test_schemas_tables_and_views_are_listed_with_exact_case(self, source):
        inspector = source.inspector
        assert {"Clinic", "Billing", "AI"} <= set(inspector.get_schema_names())
        assert sorted(inspector.get_table_names("Clinic")) == ["Encounter", "Patient"]
        assert inspector.get_table_names("Billing") == ["Patient"]
        assert inspector.get_view_names("Clinic") == ["ActivePatient"]

    def test_same_name_tables_are_distinct_assets(self, source):
        clinic, _, _ = _table(source, "Clinic", "Patient")
        billing, _, _ = _table(source, "Billing", "Patient")
        assert [str(c.name.root) for c in clinic] == ["PatientId", "FullName", "BirthDate", "Weight"]
        assert [str(c.name.root) for c in billing] == ["Code", "Balance"]

    def test_column_attributes(self, source):
        columns, _, _ = _table(source, "Clinic", "Patient")
        by_name = {str(c.name.root): c for c in columns}
        assert by_name["PatientId"].constraint == Constraint.PRIMARY_KEY
        assert by_name["FullName"].constraint == Constraint.NOT_NULL
        assert by_name["BirthDate"].constraint == Constraint.NULL
        assert by_name["FullName"].dataLength == 120
        assert (by_name["Weight"].precision, by_name["Weight"].scale) == (5, 2)
        assert [c.ordinalPosition for c in columns] in ([1, 2, 3, 4], [None] * 4)


class TestKeys:
    def test_primary_foreign_and_unique_keys(self, source):
        _, _, patient_fks = _table(source, "Clinic", "Patient")
        assert patient_fks == []
        _, _, encounter_fks = _table(source, "Clinic", "Encounter")
        assert [(f["constrained_columns"], f["referred_schema"], f["referred_table"]) for f in encounter_fks] == [
            (["PatientId"], "Clinic", "Patient")
        ]
        columns, constraints, _ = _table(source, "Billing", "Patient")
        by_name = {str(c.name.root): c for c in columns}
        assert by_name["Code"].constraint == Constraint.PRIMARY_KEY
        assert by_name["Balance"].constraint == Constraint.NULL
        assert not any(c.constraintType == ConstraintType.FOREIGN_KEY for c in constraints)

    def test_unique_constraint_is_read_for_billing_patient(self, source):
        _, unique, _ = source._get_columns_with_constraints("Billing", "Patient", source.inspector)[0:3]
        assert unique == [["Code"]]


class TestDescriptions:
    def test_table_and_column_descriptions(self, source):
        assert (
            source.get_table_description("Clinic", "Patient", source.inspector) == "Patients registered in the clinic"
        )
        assert source.get_table_description("Billing", "Patient", source.inspector) in (None, "")
        columns, _, _ = _table(source, "Clinic", "Patient")
        descriptions = {str(c.name.root): c.description for c in columns}
        assert descriptions["PatientId"].root == "Patient identifier"
        assert descriptions["FullName"] is None
        billing, _, _ = _table(source, "Billing", "Patient")
        assert all(c.description is None for c in billing)


class TestViewDefinition:
    def test_view_definition_for_the_active_patient_view(self, source):
        definition = source.get_schema_definition(TableType.View, "ActivePatient", "Clinic", source.inspector)
        # Readable for admin and for a SELECT-only login on this IRIS: assert the content, and that no warning was raised.
        assert definition is not None
        assert "Clinic.Patient" in definition and "Clinic.Encounter" in definition
        assert not [w for w in source.status.warnings if "view definition" in str(w)]

    def test_tables_have_no_view_definition(self, source):
        assert source.get_schema_definition(TableType.Regular, "Patient", "Clinic", source.inspector) is None


class TestFilters:
    def test_default_filters_exclude_system_schemas(self, source):
        pattern = source.service_connection.schemaFilterPattern
        names = source.inspector.get_schema_names()
        kept = [n for n in names if not filter_by_schema(pattern, n)]
        assert {"Clinic", "Billing", "AI"} <= set(kept)
        assert not [n for n in kept if n.startswith(("%", "Ens")) or n == "INFORMATION_SCHEMA"]
        assert len(kept) < len(names)

    def test_include_pattern_yields_only_clinic(self, source):
        pattern = FilterPattern(includes=["^Clinic$"], excludes=[])
        kept = [n for n in source.inspector.get_schema_names() if not filter_by_schema(pattern, n)]
        assert kept == ["Clinic"]

    def test_clearing_the_default_excludes_brings_system_schemas_back(self, source):
        pattern = FilterPattern(includes=[], excludes=[])
        kept = [n for n in source.inspector.get_schema_names() if not filter_by_schema(pattern, n)]
        assert "INFORMATION_SCHEMA" in kept and any(n.startswith("%") for n in kept)


class TestAccessGaps:
    def test_no_access_problem_for_the_readable_fixtures(self, source):
        for schema, table in (
            ("Clinic", "Patient"),
            ("Clinic", "Encounter"),
            ("Billing", "Patient"),
            ("AI", "Embedding"),
        ):
            _table(source, schema, table)
        # Spec 004 adds one IRIS-VECTOR-GRANT hint for a login without the dictionary grant; it is not an access gap.
        assert [w for w in source.status.warnings if "IRIS-ACCESS" in str(w)] == []

    def test_a_real_privilege_error_is_reported_not_raised(self, source, iris_cell):
        if iris_cell.has_dict_grant:
            pytest.skip(f"{iris_cell.name}: needs the login without the dictionary grant")
        fqn = f"{SERVICE}.{NAMESPACE}.Restricted.Secret"
        with source.report_access_gap(fqn, "columns", "Restricted", "Secret"):
            source.connection.execute(text("SELECT TOP 1 Name FROM %Dictionary.CompiledProperty"))
        (warning,) = [w for w in source.status.warnings if fqn in w]
        assert warning[fqn].startswith("IRIS-ACCESS: cannot read columns of Restricted.Secret: ")
        assert "\n" not in warning[fqn]
        assert "Reader123" not in warning[fqn]
        source.connection.rollback()


# --- Part B: the real workflow against an OpenMetadata server built from the overlay ----------------

OM_HOST_PORT, OM_JWT = os.environ.get("OM_HOST_PORT"), os.environ.get("OM_JWT")
needs_server = pytest.mark.skipif(
    not (OM_HOST_PORT and OM_JWT), reason="OM_HOST_PORT and OM_JWT are not set: needs a server built from the overlay"
)


def _workflow_config(iris, source_type="iris", source_config=None, service=SERVICE):
    password = iris.authType.password.get_secret_value()
    return {
        "source": {
            "type": source_type,
            "serviceName": service,
            "serviceConnection": {
                "config": {
                    "type": "Iris",
                    "hostPort": iris.hostPort,
                    "username": iris.username,
                    "authType": {"password": password},
                    "namespace": iris.namespace,
                }
            },
            "sourceConfig": {
                "config": {
                    "type": "DatabaseMetadata",
                    "includeViews": True,
                    # The framework applies only the pipeline's patterns, not the connection's defaults, so the
                    # run is limited to the fixture schemas unless a test sets its own patterns.
                    "schemaFilterPattern": {"includes": ["^(Clinic|Billing|AI|Scratch)$"]},
                    **(source_config or {}),
                }
            },
        },
        "sink": {"type": "metadata-rest", "config": {}},
        "workflowConfig": {
            "openMetadataServerConfig": {
                "hostPort": OM_HOST_PORT,
                "authProvider": "openmetadata",
                "securityConfig": {"jwtToken": OM_JWT},
            }
        },
    }


def _run(config, lineage=False):
    from metadata.workflow.metadata import MetadataWorkflow  # pylint: disable=import-outside-toplevel

    if lineage:
        config["source"]["type"] = "iris-lineage"
        # Query-log lineage is spec 010: its defaults would make the run report an error here.
        config["source"]["sourceConfig"]["config"] = {
            "type": "DatabaseLineage",
            "processViewLineage": True,
            "processQueryLineage": False,
            "processStoredProcedureLineage": False,
            "schemaFilterPattern": {"includes": ["^(Clinic|Billing|AI)$"]},
        }
    workflow = MetadataWorkflow.create(config)
    workflow.execute()
    workflow.raise_from_status()
    workflow.stop()
    return workflow


@pytest.fixture
def om():
    from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
        AuthProvider,
        OpenMetadataConnection,
    )
    from metadata.generated.schema.entity.services.databaseService import DatabaseService
    from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
        OpenMetadataJWTClientConfig,
    )
    from metadata.ingestion.ometa.ometa_api import OpenMetadata

    client = OpenMetadata(
        OpenMetadataConnection(
            hostPort=OM_HOST_PORT,
            authProvider=AuthProvider.openmetadata,
            securityConfig=OpenMetadataJWTClientConfig(jwtToken=OM_JWT),
        )
    )

    def clean():
        service = client.get_by_name(DatabaseService, SERVICE)
        if service:
            client.delete(DatabaseService, service.id.root, recursive=True, hard_delete=True)

    clean()
    yield client
    clean()


def _table_entity(om, name, fields=("columns", "tableConstraints")):
    from metadata.generated.schema.entity.data.table import Table

    return om.get_by_name(Table, f"{SERVICE}.{NAMESPACE}.{name}", fields=list(fields))


def _require_admin(iris_cell, why):
    if not iris_cell.is_admin:
        pytest.skip(f"{iris_cell.name}: {why} is asserted once, as admin")


def _schema_names(om, namespace):
    from metadata.generated.schema.entity.data.databaseSchema import DatabaseSchema

    return [s.name.root for s in om.list_all_entities(DatabaseSchema, params={"database": f"{SERVICE}.{namespace}"})]


@needs_server
class TestWorkflow:
    def test_hierarchy_columns_keys_descriptions_and_definition(self, om, iris_service_connection):
        from metadata.generated.schema.entity.data.databaseSchema import DatabaseSchema

        iris = iris_service_connection
        _run(_workflow_config(iris))
        for schema in ("Clinic", "Billing", "AI"):
            assert om.get_by_name(DatabaseSchema, f"{SERVICE}.{iris.namespace}.{schema}") is not None
        clinic, billing = _table_entity(om, "Clinic.Patient"), _table_entity(om, "Billing.Patient")
        assert [c.name.root for c in clinic.columns] == [n for n, _ in EXPECTED["columns"][("Clinic", "Patient")]]
        assert [c.name.root for c in billing.columns] == [n for n, _ in EXPECTED["columns"][("Billing", "Patient")]]
        assert clinic.description.root == EXPECTED["table_descriptions"][("Clinic", "Patient")]
        assert clinic.columns[0].description.root == EXPECTED["column_descriptions"][("Clinic", "Patient", "PatientId")]
        assert clinic.columns[0].constraint == Constraint.PRIMARY_KEY
        encounter = _table_entity(om, "Clinic.Encounter")
        foreign = [c for c in encounter.tableConstraints if c.constraintType == ConstraintType.FOREIGN_KEY]
        assert [str(r.root) for r in foreign[0].referredColumns] == [
            f"{SERVICE}.{iris.namespace}.Clinic.Patient.PatientId"
        ]
        view = _table_entity(om, "Clinic.ActivePatient", fields=("columns", "schemaDefinition"))
        assert view.tableType == TableType.View
        assert view.schemaDefinition is not None

    def test_view_lineage(self, om, iris_service_connection):
        iris = iris_service_connection
        _run(_workflow_config(iris))
        _run(_workflow_config(iris), lineage=True)
        view = _table_entity(om, "Clinic.ActivePatient", fields=())
        lineage = om.get_lineage_by_id(type(view), str(view.id.root), up_depth=1, down_depth=0)
        upstream = {node["fullyQualifiedName"] for node in lineage["nodes"] if node["id"] != str(view.id.root)}
        expected = {
            f"{SERVICE}.{iris.namespace}.{source}" for source in EXPECTED["view_sources"][("Clinic", "ActivePatient")]
        }
        assert upstream == expected

    def test_filters(self, om, iris_cell, iris_service_connection):
        _require_admin(iris_cell, "filters")
        iris = iris_service_connection
        _run(_workflow_config(iris, source_config={"schemaFilterPattern": {"includes": ["^Clinic$"]}}))
        assert _schema_names(om, iris.namespace) == ["Clinic"]

    def test_default_run_excludes_system_schemas(self, om, iris_cell, iris_service_connection):
        _require_admin(iris_cell, "the default filters")
        iris = iris_service_connection
        config = _workflow_config(iris)
        del config["source"]["sourceConfig"]["config"]["schemaFilterPattern"]
        _run(config)
        names = _schema_names(om, iris.namespace)
        assert {"Clinic", "Billing", "AI", "Scratch"} <= set(names)
        assert not [n for n in names if n.startswith(("%", "Ens")) or n == "INFORMATION_SCHEMA"]

    def test_an_explicit_pipeline_pattern_brings_system_schemas_back(self, om, iris_cell, iris_service_connection):
        _require_admin(iris_cell, "an explicit pipeline pattern")
        iris = iris_service_connection
        _run(_workflow_config(iris, source_config={"schemaFilterPattern": {"includes": ["^INFORMATION_SCHEMA$"]}}))
        assert _schema_names(om, iris.namespace) == ["INFORMATION_SCHEMA"]

    @pytest.mark.parametrize("mark_deleted", [True, False])
    def test_mark_deleted_after_drop_table(
        self, om, iris_cell, iris_service_connection, iris_admin_engine, mark_deleted
    ):
        _require_admin(iris_cell, "mark-deleted")
        iris = iris_service_connection
        # Scratch.Keep (the sentinel) keeps the schema listed, so mark-deleted visits Scratch on the second run.
        with iris_admin_engine.begin() as connection:
            connection.execute(text("CREATE TABLE Scratch.Tmp (Id INT PRIMARY KEY)"))
        config = {"markDeletedTables": mark_deleted, "schemaFilterPattern": {"includes": ["^Scratch$", "^Clinic$"]}}
        try:
            _run(_workflow_config(iris, source_config=config))
            assert _table_entity(om, "Scratch.Tmp") is not None
            with iris_admin_engine.begin() as connection:
                connection.execute(text("DROP TABLE Scratch.Tmp"))
            _run(_workflow_config(iris, source_config=config))
            from metadata.generated.schema.entity.data.table import Table

            entity = om.get_by_name(Table, f"{SERVICE}.{iris.namespace}.Scratch.Tmp", include="all")
            assert (entity is None or entity.deleted is True) == mark_deleted
            assert _table_entity(om, "Clinic.Patient") is not None
            assert _table_entity(om, "Scratch.Keep") is not None
        finally:
            with iris_admin_engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS Scratch.Tmp"))

    @pytest.mark.parametrize("override", [False, True])
    def test_description_override(self, om, iris_cell, iris_service_connection, override):
        _require_admin(iris_cell, "description override")
        from metadata.generated.schema.entity.data.table import Table

        iris = iris_service_connection
        _run(_workflow_config(iris))
        table = _table_entity(om, "Clinic.Patient", fields=())
        om.patch_description(entity=Table, source=table, description="Curated in OpenMetadata", force=True)
        _run(_workflow_config(iris, source_config={"overrideMetadata": override}))
        description = _table_entity(om, "Clinic.Patient", fields=("description",)).description.root
        assert description == (
            EXPECTED["table_descriptions"][("Clinic", "Patient")] if override else "Curated in OpenMetadata"
        )
