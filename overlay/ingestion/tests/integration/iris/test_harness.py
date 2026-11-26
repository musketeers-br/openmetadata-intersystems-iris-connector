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
Placeholder connector test that runs in every matrix cell, and tests of the cell mapping itself.

The marked tests use the connector's own engine for the cell's login: a basic query succeeds, and the
class dictionary is readable exactly when the cell's login has the dictionary grant.
"""

import pytest
from sqlalchemy import text
from tests.integration.iris.conftest import _cell_from_env
from tests.integration.iris.data.seed import LOGINS


def _scalar(engine, statement: str):
    with engine.connect() as connection:
        return connection.execute(text(statement)).scalar()


@pytest.mark.iris
def test_select_one(iris_engine):
    assert _scalar(iris_engine, "SELECT 1") == 1


@pytest.mark.iris
def test_dictionary_toggle(iris_engine, iris_cell):
    try:
        _scalar(iris_engine, "SELECT TOP 1 Name FROM %Dictionary.PropertyDefinition")
        error = None
    except Exception as exc:
        error = str(exc)
    if iris_cell.has_dict_grant:
        assert error is None, f"{iris_cell.name}: dictionary not readable: {error}"
    else:
        assert error is not None, f"{iris_cell.name}: dictionary readable without the grant"
        assert "-99" in error, f"{iris_cell.name}: {error}"


@pytest.mark.iris
def test_cell_identity(iris_engine, iris_cell, record_property):
    version = _scalar(iris_engine, "SELECT $ZVERSION")
    record_property("cell", iris_cell.name)
    record_property("zversion", version)
    assert "IRIS" in version


def test_unknown_login_is_a_usage_error():
    with pytest.raises(pytest.UsageError, match="IRIS_LOGIN"):
        _cell_from_env({"IRIS_LOGIN": "root"}, "127.0.0.1", 1972)


@pytest.mark.parametrize("login", sorted(LOGINS))
def test_each_login_maps_to_the_catalog(login):
    cell = _cell_from_env({"IRIS_LOGIN": login, "IRIS_TAG": "latest-cd"}, "127.0.0.1", 1972)
    account = LOGINS[login]
    assert (cell.username, cell.is_admin, cell.has_dict_grant) == (
        account.user,
        account.is_admin,
        account.has_dict_grant,
    )
    assert cell.name == f"iris-latest-cd-{login}"
    assert "password=" not in repr(cell)
