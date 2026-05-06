"""Shared pytest fixtures.

Most tests rely on the `examples/lean/PyleanExample.dylib` being built and
loaded as a `LeanLibrary`. The fixture is session-scoped so library
load (which initialises the Lean runtime) only happens once.
"""

import pytest

from tests.utils import find_examples_dylib
from lean_py import LeanLibrary


@pytest.fixture(scope="session")
def example_lib() -> LeanLibrary:
    dylib = find_examples_dylib()
    return LeanLibrary(dylib, "PyleanExample")
