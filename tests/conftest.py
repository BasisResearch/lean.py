"""Shared pytest fixtures.

Tests load `tests/lean` as a `LeanLibrary` via the `from_lake` smart
constructor — it handles the `lake build` invocation and locates the
shared library under `.lake/build/lib`. The fixture is session-scoped
so library load (which initialises the Lean runtime) only happens once.
"""

from pathlib import Path

import pytest

from lean_py import LeanLibrary
from lean_py.utils import add_lean_lib_to_dyld_path


@pytest.fixture(scope="session")
def example_lib() -> LeanLibrary:
    add_lean_lib_to_dyld_path()
    return LeanLibrary.from_lake(
        Path(__file__).parent / "lean", "TestLib", build=True,
    )
