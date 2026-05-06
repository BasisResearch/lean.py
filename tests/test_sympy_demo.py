"""Demonstrations: invoke SymPy and NumPy from Lean via LeanPy.Python."""

import importlib

import pytest


def _have(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _have("sympy"), reason="sympy not installed")
def test_sympy_factorial(example_lib):
    # sympy.factorial returns a sympy.Integer; str(.) yields the decimal form.
    assert example_lib.pythonEvalStr("__import__('sympy').factorial(20)") == \
        "2432902008176640000"


@pytest.mark.skipif(not _have("sympy"), reason="sympy not installed")
def test_sympy_simplify(example_lib):
    src = "str(__import__('sympy').simplify('(x**2 - 1)/(x - 1)'))"
    assert example_lib.pythonEvalStr(src) == "x + 1"


@pytest.mark.skipif(not _have("numpy"), reason="numpy not installed")
def test_numpy_sum(example_lib):
    src = "int(__import__('numpy').arange(100).sum())"
    assert example_lib.pythonEvalInt(src) == 4950


@pytest.mark.skipif(not _have("numpy"), reason="numpy not installed")
def test_numpy_dot(example_lib):
    src = "int(__import__('numpy').dot([1,2,3], [4,5,6]))"
    assert example_lib.pythonEvalInt(src) == 32


@pytest.mark.skipif(not _have("sympy"), reason="sympy not installed")
def test_lean_side_sympy_simplify(example_lib):
    """Use a Lean function that drives SymPy directly (not via eval)."""
    assert example_lib.sympySimplify("(x**2 - 1)/(x - 1)") == "x + 1"
    assert example_lib.sympySimplify("sin(x)**2 + cos(x)**2") == "1"


@pytest.mark.skipif(not _have("numpy"), reason="numpy not installed")
def test_lean_side_numpy_sum(example_lib):
    """Lean builds a NumPy array from a Lean array and sums it."""
    assert example_lib.numpySum([1, 2, 3, 4, 5]) == 15
    assert example_lib.numpySum(list(range(100))) == 4950
