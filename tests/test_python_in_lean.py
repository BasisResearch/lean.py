"""End-to-end tests for the Python-in-Lean bridge.

These exercise `LeanPy.Python.*` from Lean by calling Lean functions that
invoke CPython internally. The Lean side dlopens libpython at runtime
(via `LeanPy.Python.init`), so we exercise the whole loader path.
"""

import math
import sys

import pytest


def test_python_eval_int_simple(example_lib):
    assert example_lib.pythonEvalInt("1 + 2") == 3
    assert example_lib.pythonEvalInt("2 ** 10") == 1024
    assert example_lib.pythonEvalInt("len([1, 2, 3, 4, 5])") == 5


def test_python_eval_str(example_lib):
    assert example_lib.pythonEvalStr("'hello, ' + 'world'") == "hello, world"
    assert example_lib.pythonEvalStr("str(2 ** 8)") == "256"


def test_python_module_import_and_call(example_lib):
    # math.factorial(5) == 120
    assert example_lib.pythonCall1Int("math", "factorial", 5) == 120
    # operator.neg(7) == -7
    assert example_lib.pythonCall1Int("operator", "neg", 7) == -7


def test_python_eval_error_propagates(example_lib):
    with pytest.raises(RuntimeError):
        example_lib.pythonEvalInt("undefined_name + 1")
