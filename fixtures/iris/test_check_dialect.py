"""Offline tests of the community-dialect guard (spec 001, FR-013, SC-006, T022)."""
import importlib.metadata
import importlib.util

import pytest

import check_dialect

COMMUNITY = "sqlalchemy_iris.base:IRISDialect"


def _entry(value):
    return importlib.metadata.EntryPoint(name="iris", value=value, group="sqlalchemy.dialects")


@pytest.fixture
def environment(monkeypatch):
    """Set the installed distributions and `iris` entry points the guard sees."""

    def configure(distributions=(), entries=(), module=False):
        def distribution(name):
            if name in distributions:
                return type("Dist", (), {"version": "0.0.1"})()
            raise importlib.metadata.PackageNotFoundError(name)

        monkeypatch.setattr(importlib.metadata, "distribution", distribution)
        monkeypatch.setattr(importlib.metadata, "entry_points", lambda group=None: [_entry(v) for v in entries])
        real_find_spec = importlib.util.find_spec
        monkeypatch.setattr(
            importlib.util,
            "find_spec",
            lambda name, *a: object() if (module and name == "sqlalchemy_iris") else real_find_spec(name, *a),
        )

    return configure


def test_community_distribution_fails(environment, capsys):
    environment(distributions={"sqlalchemy-iris"}, entries=[check_dialect.OFFICIAL])
    assert check_dialect.main() == 1
    assert "sqlalchemy-iris" in capsys.readouterr().err


def test_entry_point_to_the_community_dialect_fails(environment, capsys):
    environment(entries=[COMMUNITY])
    assert check_dialect.main() == 1
    assert COMMUNITY in capsys.readouterr().err


def test_community_module_alone_fails(environment, capsys):
    environment(entries=[check_dialect.OFFICIAL], module=True)
    assert check_dialect.main() == 1
    assert "sqlalchemy_iris" in capsys.readouterr().err


def test_official_dialect_passes(environment, capsys):
    environment(entries=[check_dialect.OFFICIAL])
    assert check_dialect.main() == 0
    assert "official dialect" in capsys.readouterr().out


def test_no_iris_dialect_passes(environment, capsys):
    environment()
    assert check_dialect.main() == 0
    assert "no iris dialect installed" in capsys.readouterr().out
