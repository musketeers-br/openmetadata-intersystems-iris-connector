#!/usr/bin/env python3
"""Fail when the community IRIS dialect could be used instead of the official one (spec 001, R6).

The community package `sqlalchemy-iris` (module `sqlalchemy_iris`) registers the same `iris`
entry point in `sqlalchemy.dialects` as the official `sqlalchemy-intersystems-iris`, so it can
shadow it silently. Exit 1 when the community distribution or module is present, or when the `iris`
entry point resolves to anything but the official dialect; exit 0 otherwise. Standard library only,
so it runs in the plain fixture venv and in `.om/env`.
"""
import importlib.util
import sys
from importlib import metadata

OFFICIAL = "sqlalchemy_intersystems_iris.iris:IRISDialect_iris"
COMMUNITY_DISTRIBUTION = "sqlalchemy-iris"
COMMUNITY_MODULE = "sqlalchemy_iris"


def problems():
    """Every reason the environment could pick up the community dialect."""
    found = []
    try:
        version = metadata.distribution(COMMUNITY_DISTRIBUTION).version
    except metadata.PackageNotFoundError:
        pass
    else:
        found.append(f"distribution {COMMUNITY_DISTRIBUTION} {version} is installed")
    if importlib.util.find_spec(COMMUNITY_MODULE) is not None:
        found.append(f"module {COMMUNITY_MODULE} is importable")
    for entry in metadata.entry_points(group="sqlalchemy.dialects"):
        if entry.name == "iris" and entry.value != OFFICIAL:
            found.append(f"entry point sqlalchemy.dialects:iris -> {entry.value} (expected {OFFICIAL})")
    return found


def main():
    found = problems()
    if found:
        for problem in found:
            sys.stderr.write(f"check_dialect: FAIL: {problem}\n")
        sys.stderr.write("check_dialect: remove sqlalchemy-iris; the connector uses sqlalchemy-intersystems-iris\n")
        return 1
    official = any(
        entry.name == "iris" and entry.value == OFFICIAL
        for entry in metadata.entry_points(group="sqlalchemy.dialects")
    )
    sys.stdout.write(f"check_dialect: ok ({'official dialect' if official else 'no iris dialect installed'})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
