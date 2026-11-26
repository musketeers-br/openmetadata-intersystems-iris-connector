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
No silent path in the IRIS connector (spec 005, ADR-0008): every `except` handler in `iris/` re-raises or records a
status warning, unless it is allow-listed with a reason. `contextlib.suppress` swallows without a body that could
report, so each use needs an allow-list entry.
"""

import ast
from pathlib import Path

import pytest

from metadata.ingestion.source.database import iris

PACKAGE = Path(iris.__file__).parent

# (file, enclosing function) -> why the handler neither warns nor re-raises.
ALLOWED = {
    ("connection.py", "preset_dialect_state"): (
        "ADR-0015 preset: a refused dictionary read sets _dictionary_access for the dialect; no object is read, and "
        "the optional Test Connection step reports the missing grant"
    ),
}


def _reports(node: ast.AST) -> bool:
    """A `raise`, or a call whose attribute chain ends in `status.warning`."""
    for child in ast.walk(node):
        if isinstance(child, ast.Raise):
            return True
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "warning":
            owner = child.func.value
            if (isinstance(owner, ast.Attribute) and owner.attr == "status") or (
                isinstance(owner, ast.Name) and owner.id == "status"
            ):
                return True
    return False


def _is_suppress(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "suppress") or (
        isinstance(func, ast.Attribute) and func.attr == "suppress"
    )


def audit(sources: dict[str, str], allowed: dict[tuple[str, str], str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Return the offenders as `file:line` and the allow-list entries that matched nothing."""
    offenders: list[str] = []
    used: set[tuple[str, str]] = set()

    def visit(node: ast.AST, filename: str, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
            silent = (isinstance(child, ast.ExceptHandler) and not _reports(child)) or _is_suppress(child)
            if silent:
                if (filename, function) in allowed:
                    used.add((filename, function))
                else:
                    offenders.append(f"{filename}:{child.lineno}")
            visit(child, filename, inner)

    for filename, text in sources.items():
        visit(ast.parse(text, filename=filename), filename, "<module>")
    return offenders, sorted(set(allowed) - used)


def _package_sources() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(PACKAGE.glob("*.py"))}


def test_no_handler_in_the_iris_package_is_silent():
    offenders, stale = audit(_package_sources(), ALLOWED)
    assert offenders == [], f"handlers that neither re-raise nor call status.warning: {offenders}"
    assert stale == [], f"allow-list entries that match no handler: {stale}"


# --- self-tests of the guard ---

SILENT = """
def read(self):
    try:
        self.connection.execute(q)
    except SQLAlchemyError:
        logger.debug("no access")
"""

WARNS = """
def read(self):
    try:
        self.connection.execute(q)
    except SQLAlchemyError as exc:
        self.status.warning(key, str(exc))
"""

RERAISES = """
def read(self):
    try:
        import x
    except ImportError as exc:
        raise Missing("x") from exc
"""

SUPPRESSES = """
from contextlib import suppress

def read(self):
    with suppress(SQLAlchemyError):
        self.connection.execute(q)
"""


@pytest.mark.parametrize(
    ("text", "offenders"),
    [(SILENT, ["m.py:5"]), (WARNS, []), (RERAISES, []), (SUPPRESSES, ["m.py:5"])],
    ids=["silent", "warns", "reraises", "suppress"],
)
def test_the_guard_finds_silent_handlers(text, offenders):
    assert audit({"m.py": text}, {}) == (offenders, [])


def test_an_allow_listed_handler_passes():
    assert audit({"m.py": SILENT}, {("m.py", "read"): "reason"}) == ([], [])


def test_a_stale_allow_list_entry_fails():
    assert audit({"m.py": WARNS}, {("m.py", "read"): "reason"}) == ([], [("m.py", "read")])
