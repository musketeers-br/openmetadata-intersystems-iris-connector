"""Repository rules that keep tests safe on the shared fixtures (spec 001, FR-018, SC-008). Offline.

Connector tests never create users or grants, and create, fill or drop tables only in `Scratch`,
never `Scratch.Keep` (the loader owns it). Only SQL passed to `execute`, `exec_driver_sql` or `text`
is inspected, so assertion messages that quote SQL are not flagged. The fixture loader itself is
exempt. A last rule keeps the repository's documents self-contained: no tracked file names the
private planning repository.
"""
import ast
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "overlay" / "ingestion" / "tests"
LOADER = TESTS / "integration" / "iris" / "data" / "seed.py"
SQL_CALLS = {"execute", "exec_driver_sql", "text"}
FORBIDDEN = re.compile(r"\bCREATE\s+USER\b|\bGRANT\b|\bSecurity\.Users\b", re.IGNORECASE)
WRITES = re.compile(
    r"\b(CREATE\s+TABLE|CREATE\s+VIEW|INSERT\s+INTO|DROP\s+TABLE|DROP\s+VIEW)\s+"
    r"(?:IF\s+(?:NOT\s+)?EXISTS\s+)?([^\s(;]+)",
    re.IGNORECASE,
)
IN_SCRATCH = re.compile(r'^"?Scratch"?\.', re.IGNORECASE)
SENTINEL = re.compile(r'^"?Scratch"?\."?Keep"?$', re.IGNORECASE)
PLANNING_REPO = "is-" + "omd"  # split so this file does not name it


def _string_value(node):
    """The text of a string constant or f-string (placeholders become `{}`), else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(part.value if isinstance(part, ast.Constant) else "{}" for part in node.values)
    return None


def _sql_arguments(tree):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in SQL_CALLS:
            sql = _string_value(node.args[0])
            if sql is not None:
                yield node.lineno, sql


def violations(path):
    """Every rule broken by the SQL in one Python file, as 'file:line: reason'."""
    found = []
    for line, sql in _sql_arguments(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        where = f"{path}:{line}"
        if FORBIDDEN.search(sql):
            found.append(f"{where}: tests never create users or grants: {sql!r}")
        for verb, target in WRITES.findall(sql):
            verb = " ".join(verb.upper().split())
            if not IN_SCRATCH.match(target):
                found.append(f"{where}: {verb} outside Scratch: {target}")
            elif SENTINEL.match(target) and verb in {"CREATE TABLE", "DROP TABLE"}:
                found.append(f"{where}: {verb} on Scratch.Keep, which the loader owns")
    return found


def test_connector_tests_follow_the_fixture_rules():
    files = [p for p in sorted(TESTS.rglob("*.py")) if p != LOADER]
    assert files, f"no test files under {TESTS}"
    found = [problem for path in files for problem in violations(path)]
    assert not found, "\n".join(found)


def test_no_tracked_file_names_the_planning_repository():
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    found = []
    for name in listed.stdout.decode().split("\0"):
        path = ROOT / name
        if not name or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found += [f"{name}:{n}" for n, line in enumerate(text.splitlines(), 1) if PLANNING_REPO in line.lower()]
    assert not found, "documents must state decisions themselves, not point to the planning repository:\n" + "\n".join(
        found
    )


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ('conn.execute(text("CREATE TABLE Clinic.X (Id INT)"))', "CREATE TABLE outside Scratch"),
        ('conn.execute(text("DROP TABLE Scratch.Keep"))', "DROP TABLE on Scratch.Keep"),
        ('cur.execute("CREATE TABLE IF NOT EXISTS Scratch.Keep (Id INT)")', "CREATE TABLE on Scratch.Keep"),
        ('cur.execute("INSERT INTO Billing.Patient VALUES (?, ?)", row)', "INSERT INTO outside Scratch"),
        ('engine.exec_driver_sql(f"GRANT SELECT ON {t} TO someone")', "users or grants"),
        ('cur.execute("CREATE USER x IDENTIFIED BY y")', "users or grants"),
        ('cur.execute(f"DROP VIEW {schema}.V")', "DROP VIEW outside Scratch"),
    ],
    ids=["create-outside", "drop-sentinel", "create-sentinel", "insert-outside", "grant", "user", "fstring"],
)
def test_the_rule_can_fail(tmp_path, source, reason):
    path = tmp_path / "test_bad.py"
    path.write_text(source + "\n", encoding="utf-8")
    found = violations(path)
    assert any(reason in problem for problem in found), found


@pytest.mark.parametrize(
    "source",
    [
        'assert "GRANT SELECT ON X" in msg',
        'conn.execute(text("CREATE TABLE Scratch.Gone (Id INT)"))',
        'conn.execute(text(f"DROP TABLE Scratch.{name}"))',
        'conn.execute(text("SELECT COUNT(*) FROM Scratch.Keep"))',
        'pytest.fail("run CREATE USER by hand")',
    ],
    ids=["assert-text", "scratch-create", "scratch-fstring", "sentinel-read", "message"],
)
def test_allowed_sql_passes(tmp_path, source):
    path = tmp_path / "test_ok.py"
    path.write_text(source + "\n", encoding="utf-8")
    assert violations(path) == []
