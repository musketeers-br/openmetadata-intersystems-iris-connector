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

Environment: IRIS_HOST, IRIS_PORT, IRIS_NAMESPACE, IRIS_LOGIN (admin | reader | reader_dict, default reader).
spec 001's conftest (`iris_cell`, `iris_service_connection`, `iris_admin_engine`) replaces this ad-hoc setup.
"""

import os
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text

from metadata.generated.schema.entity.data.table import Constraint, ConstraintType, TableType
from metadata.generated.schema.entity.services.connections.database.common.basicAuth import (
    BasicAuth,
)
from metadata.generated.schema.entity.services.connections.database.irisConnection import (
    IrisConnection as IrisConnectionConfig,
)
from metadata.ingestion.api.status import Status
from metadata.ingestion.source.database.iris.connection import (
    IrisConnection,
    preset_dialect_state,
)
from metadata.ingestion.source.database.iris.metadata import IrisSource
from metadata.utils.filters import filter_by_schema

pytestmark = pytest.mark.iris

LOGINS = {
    "admin": ("_SYSTEM", "SYS"),
    "reader": ("omd_reader", "Reader123"),
    "reader_dict": ("omd_reader_dict", "Reader123"),
}
SERVICE = "iris_test"
NAMESPACE = os.environ.get("IRIS_NAMESPACE", "USER")


def _login(login=None):
    return login or os.environ.get("IRIS_LOGIN", "reader")


def _hostport():
    return f"{os.environ.get('IRIS_HOST', '127.0.0.1')}:{os.environ.get('IRIS_PORT', '1972')}"


def _config(login=None, **overrides) -> IrisConnectionConfig:
    username, password = LOGINS[_login(login)]
    values = {
        "username": username,
        "authType": BasicAuth(password=password),
        "hostPort": _hostport(),
        "namespace": NAMESPACE,
    }
    values.update(overrides)
    return IrisConnectionConfig(**values)


def _admin_engine():
    username, password = LOGINS["admin"]
    engine = create_engine(f"iris://{username}:{password}@{_hostport()}/{NAMESPACE}")
    event.listen(engine, "do_connect", lambda dialect, _r, args, kwargs: preset_dialect_state(dialect, args, kwargs))
    return engine


@pytest.fixture(scope="module")
def source():
    config = _config()
    engine = IrisConnection(config).client
    source = IrisSource.__new__(IrisSource)
    source.service_connection = config
    source.engine = engine
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
    engine.dispose()


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
        pattern = _config(schemaFilterPattern={"includes": ["^Clinic$"], "excludes": []}).schemaFilterPattern
        kept = [n for n in source.inspector.get_schema_names() if not filter_by_schema(pattern, n)]
        assert kept == ["Clinic"]

    def test_clearing_the_default_excludes_brings_system_schemas_back(self, source):
        pattern = _config(schemaFilterPattern={"includes": [], "excludes": []}).schemaFilterPattern
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
        assert source.status.warnings == []

    def test_a_real_privilege_error_is_reported_not_raised(self, source):
        if _login() != "reader":
            pytest.skip("needs the login without the dictionary grant")
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


def _workflow_config(source_type="iris", source_config=None, login=None, service=SERVICE):
    username, password = LOGINS[_login(login)]
    return {
        "source": {
            "type": source_type,
            "serviceName": service,
            "serviceConnection": {
                "config": {
                    "type": "Iris",
                    "hostPort": _hostport(),
                    "username": username,
                    "authType": {"password": password},
                    "namespace": NAMESPACE,
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


@needs_server
class TestWorkflow:
    def test_hierarchy_columns_keys_descriptions_and_definition(self, om):
        from metadata.generated.schema.entity.data.databaseSchema import DatabaseSchema

        _run(_workflow_config())
        for schema in ("Clinic", "Billing", "AI"):
            assert om.get_by_name(DatabaseSchema, f"{SERVICE}.{NAMESPACE}.{schema}") is not None
        clinic, billing = _table_entity(om, "Clinic.Patient"), _table_entity(om, "Billing.Patient")
        assert len(clinic.columns) == 4 and len(billing.columns) == 2
        assert clinic.columns[0].name.root == "PatientId"
        assert clinic.description.root == "Patients registered in the clinic"
        assert clinic.columns[0].description.root == "Patient identifier"
        assert clinic.columns[0].constraint == Constraint.PRIMARY_KEY
        encounter = _table_entity(om, "Clinic.Encounter")
        foreign = [c for c in encounter.tableConstraints if c.constraintType == ConstraintType.FOREIGN_KEY]
        assert [str(r.root) for r in foreign[0].referredColumns] == [f"{SERVICE}.{NAMESPACE}.Clinic.Patient.PatientId"]
        view = _table_entity(om, "Clinic.ActivePatient", fields=("columns", "schemaDefinition"))
        assert view.tableType == TableType.View
        assert view.schemaDefinition is not None

    def test_view_lineage(self, om):
        _run(_workflow_config())
        _run(_workflow_config(), lineage=True)
        view = _table_entity(om, "Clinic.ActivePatient", fields=())
        lineage = om.get_lineage_by_id(type(view), str(view.id.root), up_depth=1, down_depth=0)
        upstream = {node["fullyQualifiedName"] for node in lineage["nodes"] if node["id"] != str(view.id.root)}
        assert upstream == {f"{SERVICE}.{NAMESPACE}.Clinic.Patient", f"{SERVICE}.{NAMESPACE}.Clinic.Encounter"}

    @pytest.mark.skipif(_login() != "admin", reason="filters are asserted once, as admin")
    def test_filters(self, om):
        from metadata.generated.schema.entity.data.databaseSchema import DatabaseSchema

        _run(_workflow_config(source_config={"schemaFilterPattern": {"includes": ["^Clinic$"]}}))
        schemas = om.list_all_entities(DatabaseSchema, params={"database": f"{SERVICE}.{NAMESPACE}"})
        assert [s.name.root for s in schemas] == ["Clinic"]

    @pytest.mark.skipif(_login() != "admin", reason="asserted once, as admin")
    def test_default_run_excludes_system_schemas(self, om):
        from metadata.generated.schema.entity.data.databaseSchema import DatabaseSchema

        config = _workflow_config()
        del config["source"]["sourceConfig"]["config"]["schemaFilterPattern"]
        _run(config)
        schemas = om.list_all_entities(DatabaseSchema, params={"database": f"{SERVICE}.{NAMESPACE}"})
        names = [s.name.root for s in schemas]
        assert {"Clinic", "Billing", "AI"} <= set(names)
        assert not [n for n in names if n.startswith(("%", "Ens")) or n == "INFORMATION_SCHEMA"]

    @pytest.mark.skipif(_login() != "admin", reason="asserted once, as admin")
    def test_an_explicit_pipeline_pattern_brings_system_schemas_back(self, om):
        from metadata.generated.schema.entity.data.databaseSchema import DatabaseSchema

        _run(_workflow_config(source_config={"schemaFilterPattern": {"includes": ["^INFORMATION_SCHEMA$"]}}))
        schemas = om.list_all_entities(DatabaseSchema, params={"database": f"{SERVICE}.{NAMESPACE}"})
        assert [s.name.root for s in schemas] == ["INFORMATION_SCHEMA"]

    @pytest.mark.skipif(_login() != "admin", reason="mark-deleted is asserted once, as admin")
    @pytest.mark.parametrize("mark_deleted", [True, False])
    def test_mark_deleted_after_drop_table(self, om, mark_deleted):
        engine = _admin_engine()
        with engine.begin() as connection:
            # IRIS stops listing a schema once its last table is gone, and mark-deleted only visits listed
            # schemas: keep one table in Scratch so the dropped one is in scope on the second run.
            connection.execute(text("CREATE TABLE Scratch.Keep (Id INT PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE Scratch.Tmp (Id INT PRIMARY KEY)"))
        config = {"markDeletedTables": mark_deleted, "schemaFilterPattern": {"includes": ["^Scratch$", "^Clinic$"]}}
        try:
            _run(_workflow_config(source_config=config))
            assert _table_entity(om, "Scratch.Tmp") is not None
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE Scratch.Tmp"))
            _run(_workflow_config(source_config=config))
            from metadata.generated.schema.entity.data.table import Table

            entity = om.get_by_name(Table, f"{SERVICE}.{NAMESPACE}.Scratch.Tmp", include="all")
            assert (entity is None or entity.deleted is True) == mark_deleted
            assert _table_entity(om, "Clinic.Patient") is not None
        finally:
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS Scratch.Tmp"))
                connection.execute(text("DROP TABLE IF EXISTS Scratch.Keep"))

    @pytest.mark.skipif(_login() != "admin", reason="override is asserted once, as admin")
    @pytest.mark.parametrize("override", [False, True])
    def test_description_override(self, om, override):
        from metadata.generated.schema.entity.data.table import Table
        from metadata.ingestion.ometa.mixins.patch_mixin_utils import PatchOperation  # noqa: F401

        _run(_workflow_config())
        table = _table_entity(om, "Clinic.Patient", fields=())
        om.patch_description(entity=Table, source=table, description="Curated in OpenMetadata", force=True)
        _run(_workflow_config(source_config={"overrideMetadata": override}))
        description = _table_entity(om, "Clinic.Patient", fields=("description",)).description.root
        assert description == ("Patients registered in the clinic" if override else "Curated in OpenMetadata")
