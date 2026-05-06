"""End-to-end tests for the typed exception path.

Two directions:
  1. Lean error → Python: `@[python]` raises an `IO.Error`; the wrapper
     decodes the ctor and raises `LeanError`.
  2. Python error → Lean → Python: a `LeanPy.Python.eval` call inside
     a `@[python]` function fails with a `KeyError` (etc); the bridge
     packages it as `IO.userError "KeyError: ..."` and we want the
     Python wrapper to reraise as `LeanPyCallbackError(python_type=...)`.
  3. Lean recovery: `tryCatchPy` should catch the Python exception
     inside Lean and return a parsed sentinel string.
"""

from __future__ import annotations

import pytest

from lean_py import LeanError, LeanPyCallbackError


def test_lean_panic_raises_typed_lean_error(example_lib):
    """A bare `IO.userError` from Lean should surface as `LeanError`
    with `kind == "userError"`."""
    with pytest.raises(LeanError) as excinfo:
        example_lib.py_lean_panic("boom")
    e = excinfo.value
    assert e.kind == "userError"
    assert e.message == "boom"


def test_python_callback_error_carries_type(example_lib):
    """A Python `NameError` inside the bridge should round-trip with
    its original Python class name visible."""
    with pytest.raises(LeanPyCallbackError) as excinfo:
        example_lib.propagatePythonError("definitely_undefined_name + 1")
    e = excinfo.value
    assert e.python_type == "NameError"
    assert "definitely_undefined_name" in e.python_message
    # Subclassing: every callback error is also a LeanError.
    assert isinstance(e, LeanError)
    assert e.kind == "python"


def test_python_callback_error_zero_division(example_lib):
    """A `ZeroDivisionError` should likewise round-trip its type."""
    with pytest.raises(LeanPyCallbackError) as excinfo:
        example_lib.propagatePythonError("1 / 0")
    assert excinfo.value.python_type == "ZeroDivisionError"


def test_python_callback_error_key_error(example_lib):
    """`KeyError` carries the missing-key as the message body."""
    with pytest.raises(LeanPyCallbackError) as excinfo:
        example_lib.propagatePythonError("{}['missing']")
    assert excinfo.value.python_type == "KeyError"


def test_lean_side_recovery(example_lib):
    """`LeanPy.Python.tryCatchPy` should catch the Python exception
    *inside* Lean. The fixture returns a sentinel string carrying the
    exception's parsed type name and message — no Python-side raise."""
    s = example_lib.evalOrDescribeError("undefined_x + 1")
    assert s.startswith("caught:NameError:")
    assert "undefined_x" in s


def test_lean_side_recovery_zero_division(example_lib):
    s = example_lib.evalOrDescribeError("1 / 0")
    assert s.startswith("caught:ZeroDivisionError:")


def test_lean_side_no_error_passes_through(example_lib):
    """When the action succeeds, `tryCatchPy` returns the value
    unchanged."""
    s = example_lib.evalOrDescribeError("'hello'")
    assert s == "hello"


def test_lean_error_is_runtime_error(example_lib):
    """Base class is RuntimeError so existing `except Exception:` and
    `except RuntimeError:` blocks still catch us."""
    with pytest.raises(RuntimeError):
        example_lib.py_lean_panic("still raises")
    with pytest.raises(Exception):
        example_lib.py_lean_panic("still raises")


def test_lean_error_str_contains_kind(example_lib):
    """`str(LeanError)` should be human-readable and include the kind
    so users diagnosing tracebacks see what flavor of error it was."""
    try:
        example_lib.py_lean_panic("xyzzy")
    except LeanError as e:
        s = str(e)
        assert "userError" in s
        assert "xyzzy" in s
    else:
        pytest.fail("expected LeanError")
