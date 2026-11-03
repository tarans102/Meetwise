"""Dependency-light test runner. Works without pytest; `pytest` also collects these files."""
import importlib
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

passed = failed = 0
for path in sorted((ROOT / "tests").glob("test_*.py")):
    module = importlib.import_module(f"tests.{path.stem}")
    for name, fn in vars(module).items():
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"PASS  {path.stem}::{name}")
            except Exception:
                failed += 1
                print(f"FAIL  {path.stem}::{name}")
                traceback.print_exc()
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
