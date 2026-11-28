"""Fixtures for the fixture tests in fixtures/iris (plain venv: intersystems-irispython and pytest).

Tests that need a live IRIS use `iris_env` or `admin_conn`; without IRIS_HOST those fixtures raise a
usage error instead of skipping, so a run without IRIS cannot pass by skipping.
"""
import importlib.util
import os

import pytest

from seed import CANDIDATES  # fixtures/iris/seed.py, on sys.path through pytest's rootdir insertion


@pytest.fixture(scope="session")
def seed_module():
    """The canonical loader module, loaded by path (the .om/ copy when it exists)."""
    path = next(p for p in CANDIDATES if p.is_file())
    spec = importlib.util.spec_from_file_location("iris_fixture_seed", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def iris_env():
    if not os.environ.get("IRIS_HOST"):
        raise pytest.UsageError(
            "fixture tests need IRIS: run fixtures/iris/start-iris.sh TAG PORT NAME, "
            "then set IRIS_HOST (and IRIS_PORT)"
        )
    return {
        "host": os.environ["IRIS_HOST"],
        "port": int(os.environ.get("IRIS_PORT", "1972")),
        "namespace": os.environ.get("IRIS_NAMESPACE", "USER"),
        "admin_user": os.environ.get("IRIS_ADMIN_USER", "_SYSTEM"),
        "admin_password": os.environ.get("IRIS_ADMIN_PASSWORD", "SYS"),
    }


@pytest.fixture(scope="session")
def connect(iris_env):
    """connect(user, password) -> a driver connection to the configured instance."""
    import iris  # pylint: disable=import-outside-toplevel

    def _connect(user, password):
        return iris.connect(iris_env["host"], iris_env["port"], iris_env["namespace"], user, password)

    return _connect


@pytest.fixture(scope="session")
def loaded(seed_module, iris_env):
    """Load the fixtures once per session; tests that change state reload them."""
    seed_module.load(**iris_env)
    return iris_env


@pytest.fixture
def admin_conn(loaded, connect):
    conn = connect(loaded["admin_user"], loaded["admin_password"])
    yield conn
    conn.close()
