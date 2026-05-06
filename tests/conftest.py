"""Shared pytest fixtures.

Tests load `tests/lean` as a `LeanLibrary` via the `from_lake` smart
constructor — it handles the `lake build` invocation and locates the
shared library under `.lake/build/lib`. The fixture is session-scoped
so library load (which initialises the Lean runtime) only happens once.

We run kernel tests after everything else: the kernel tests trigger a
cumulative refcount issue (see docs/ARCHITECTURE.md "GoalState
lifecycle") that destabilises subsequent tests. Putting them last
keeps the rest of the suite robust without losing the kernel coverage.
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


def pytest_collection_modifyitems(config, items):
    """Reorder so kernel-state tests run last.

    The kernel tests exercise long-lived Lean state objects whose
    finalisation interacts poorly with later tests. Reordering keeps
    the rest of the suite green.
    """
    def is_kernel_full(item):
        return "test_kernel_full" in item.nodeid

    items.sort(key=is_kernel_full)
