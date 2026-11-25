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
Shared fixtures for the IRIS integration tests.

The cell (release track x login) comes from the environment only:
  IRIS_HOST, IRIS_PORT (1972), IRIS_NAMESPACE (USER), IRIS_TAG (latest-em),
  IRIS_LOGIN: admin | reader | reader_dict (reader)
User names and passwords come from the fixture catalog (data/seed.py).

With IRIS_HOST set, the instance must already hold the shared fixtures (fixtures/iris/seed.py); the
session checks them and fails if they are not as expected. Without IRIS_HOST, the session starts one
IRIS Community container of IRIS_TAG, prepares it, loads the fixtures and removes it at the end.

Tests branch on `iris_cell.is_admin` / `iris_cell.has_dict_grant`, never on login names, create
objects only in `Scratch` (never `Scratch.Keep`) and skip with a reason naming `iris_cell.name`.
"""

import os
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import NamedTuple

import pytest
from sqlalchemy.engine import Engine
from tests.integration.iris.data.seed import LOGINS, FixtureError, load, self_check

from metadata.generated.schema.entity.services.connections.database.common.basicAuth import (
    BasicAuth,
)
from metadata.generated.schema.entity.services.connections.database.irisConnection import (
    IrisConnection as IrisConnectionConfig,
)
from metadata.ingestion.source.database.iris.connection import IrisConnection

IMAGE = "containers.intersystems.com/intersystems/iris-community"
DEFAULT_TAG = "latest-em"
DEFAULT_LOGIN = "reader"
UNEXPIRE = '##class(Security.Users).UnExpireUserPasswords("*")'
START_TIMEOUT_SECONDS = 180


def pytest_configure(config):
    config.addinivalue_line("markers", "iris: integration test against an IRIS instance with the shared fixtures")


@dataclass(frozen=True)
class IrisCell:
    """One matrix cell: a release track and a login, with that login's credentials and grants."""

    tag: str
    login: str
    host: str
    port: int
    namespace: str
    username: str
    password: str = field(repr=False)
    is_admin: bool
    has_dict_grant: bool

    @property
    def name(self) -> str:
        return f"iris-{self.tag}-{self.login}"


class _Endpoint(NamedTuple):
    host: str
    port: int
    tag: str
    started_here: bool


def _admin_credentials(env: Mapping[str, str]) -> tuple[str, str]:
    admin = LOGINS["admin"]
    return env.get("IRIS_ADMIN_USER", admin.user), env.get("IRIS_ADMIN_PASSWORD", admin.password)


def _cell_from_env(env: Mapping[str, str], host: str, port: int) -> IrisCell:
    login = env.get("IRIS_LOGIN", DEFAULT_LOGIN)
    if login not in LOGINS:
        raise pytest.UsageError(f"IRIS_LOGIN={login!r}: expected one of {', '.join(sorted(LOGINS))}")
    account = LOGINS[login]
    username, password = _admin_credentials(env) if account.is_admin else (account.user, account.password)
    return IrisCell(
        tag=env.get("IRIS_TAG", DEFAULT_TAG),
        login=login,
        host=host,
        port=int(port),
        namespace=env.get("IRIS_NAMESPACE", "USER"),
        username=username,
        password=password,
        is_admin=account.is_admin,
        has_dict_grant=account.has_dict_grant,
    )


def _connection_config(cell: IrisCell, username: str, password: str) -> IrisConnectionConfig:
    return IrisConnectionConfig(
        hostPort=f"{cell.host}:{cell.port}",
        username=username,
        authType=BasicAuth(password=password),
        namespace=cell.namespace,
    )


def _wait_until_running(container) -> None:
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while True:
        result = container.exec(["iris", "qlist"])
        fields = result.output.decode(errors="replace").split("^")
        if result.exit_code == 0 and len(fields) > 3 and fields[3].startswith("running"):
            return
        if time.monotonic() > deadline:
            raise RuntimeError(f"IRIS did not reach state 'running' within {START_TIMEOUT_SECONDS}s")
        time.sleep(2)


@pytest.fixture(scope="session")
def _iris_endpoint() -> Iterator[_Endpoint]:
    tag = os.environ.get("IRIS_TAG", DEFAULT_TAG)
    if os.environ.get("IRIS_HOST"):
        yield _Endpoint(os.environ["IRIS_HOST"], int(os.environ.get("IRIS_PORT", "1972")), tag, False)
        return

    from testcontainers.core.container import DockerContainer

    container = DockerContainer(f"{IMAGE}:{tag}").with_command("--check-caps false").with_exposed_ports(1972)
    container.start()
    try:
        _wait_until_running(container)
        result = container.exec(["iris", "session", "IRIS", "-U", "%SYS", UNEXPIRE])
        if result.exit_code != 0:
            raise RuntimeError(f"unexpiring the default passwords failed: {result.output!r}")
        # 127.0.0.1, not localhost: OpenMetadata rewrites localhost for workflows run in containers.
        host = container.get_container_host_ip().replace("localhost", "127.0.0.1")
        yield _Endpoint(host, int(container.get_exposed_port(1972)), tag, True)
    finally:
        container.stop()


@pytest.fixture(scope="session")
def seeded(_iris_endpoint) -> None:
    """The shared fixtures are in place: loaded here in fallback mode, verified otherwise."""
    host, port, _, started_here = _iris_endpoint
    namespace = os.environ.get("IRIS_NAMESPACE", "USER")
    admin_user, admin_password = _admin_credentials(os.environ)
    try:
        if started_here:
            load(host, port, namespace, admin_user, admin_password, wait_seconds=120)
        else:
            self_check(host, port, namespace, admin_user, admin_password)
    except FixtureError as exc:
        pytest.fail(
            f"shared IRIS fixtures not ready on {host}:{port} (run fixtures/iris/seed.py): {exc}", pytrace=False
        )


@pytest.fixture(scope="session")
def iris_cell(_iris_endpoint, seeded) -> IrisCell:
    """The cell this session runs in. Depends on `seeded`, so every IRIS test checks the fixtures."""
    return _cell_from_env(os.environ, _iris_endpoint.host, _iris_endpoint.port)


@pytest.fixture(scope="session")
def iris_service_connection(iris_cell) -> IrisConnectionConfig:
    return _connection_config(iris_cell, iris_cell.username, iris_cell.password)


@pytest.fixture(scope="session")
def iris_admin_service_connection(iris_cell) -> IrisConnectionConfig:
    """Administrator connection settings, for setup, assertions and tests that run as admin by design."""
    return _connection_config(iris_cell, *_admin_credentials(os.environ))


@pytest.fixture(scope="session")
def iris_engine(iris_service_connection, seeded) -> Iterator[Engine]:
    engine = IrisConnection(iris_service_connection).client
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def iris_admin_engine(iris_admin_service_connection, seeded) -> Iterator[Engine]:
    """Administrator engine, for test setup and assertions only, never for the behavior under test."""
    engine = IrisConnection(iris_admin_service_connection).client
    yield engine
    engine.dispose()
