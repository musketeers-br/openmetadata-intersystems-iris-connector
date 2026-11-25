"""Load and verify the shared IRIS fixtures (spec 001): the one documented command.

Runs the canonical loader, ingestion/tests/integration/iris/data/seed.py. When .om/ exists it runs
the copy there, because developers edit inside .om/ (ADR-0014); otherwise the overlay/ copy. The
configuration (IRIS_HOST, IRIS_PORT, ...) and exit codes are the loader's; see its docstring.
"""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELATIVE = Path("ingestion/tests/integration/iris/data/seed.py")
CANDIDATES = (ROOT / ".om" / RELATIVE, ROOT / "overlay" / RELATIVE)


def canonical_loader() -> Path:
    for path in CANDIDATES:
        if path.is_file():
            return path
    raise SystemExit(f"fixture loader not found: {CANDIDATES[1]}")


if __name__ == "__main__":
    loader = canonical_loader()
    print(f"loader: {loader.relative_to(ROOT)}", flush=True)
    try:
        runpy.run_path(str(loader), run_name="__main__")
    except SystemExit as done:
        sys.exit(done.code)
