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


# ---- Lean callable error path (Phase 3c) -----------------------------


def test_lean_callable_failure_raises_runtime_error(example_lib):
    """An IO.userError thrown inside a Lean closure surfaces as a
    Python `RuntimeError` carrying the original Lean message."""
    f = example_lib.py_make_lean_failing_callable(None)
    with pytest.raises(RuntimeError) as ei:
        f()
    assert "intentional Lean failure" in str(ei.value)


# ---- Round-trip: Python error → Lean catches → Lean re-throws -------


def test_python_attribute_error_round_trip(example_lib):
    """`AttributeError` is one of CPython's most common — make sure
    the `LeanPyCallbackError` route preserves it."""
    with pytest.raises(LeanPyCallbackError) as ei:
        example_lib.propagatePythonError("(1).nonexistent_method()")
    assert ei.value.python_type == "AttributeError"


def test_python_type_error_round_trip(example_lib):
    """TypeError preserves its type label across the bridge."""
    with pytest.raises(LeanPyCallbackError) as ei:
        example_lib.propagatePythonError("1 + 'a'")
    assert ei.value.python_type == "TypeError"


def test_python_value_error_round_trip(example_lib):
    """ValueError preserves its type label across the bridge."""
    with pytest.raises(LeanPyCallbackError) as ei:
        example_lib.propagatePythonError("int('abc')")
    assert ei.value.python_type == "ValueError"


def test_python_callback_error_python_message_attr(example_lib):
    """`LeanPyCallbackError.python_message` is just the message body
    (no `TypeName: ` prefix). This is the form to pass back to Python
    code that wants to re-raise with the original semantics."""
    with pytest.raises(LeanPyCallbackError) as ei:
        example_lib.propagatePythonError("undefined_x")
    e = ei.value
    assert "undefined_x" in e.python_message
    assert not e.python_message.startswith("NameError:"), \
        "python_message should be the unprefixed payload"


def test_lean_error_no_python_attrs(example_lib):
    """A pure-Lean error (`IO.userError`) is `LeanError` but NOT a
    `LeanPyCallbackError`, so callers can dispatch on the exception
    type alone."""
    with pytest.raises(LeanError) as ei:
        example_lib.py_lean_panic("just lean")
    assert not isinstance(ei.value, LeanPyCallbackError)


# ---- Smoke: nested call paths preserve error info -------------------


def test_lean_callable_raised_message_preserved(example_lib):
    """When Python invokes a Lean callable that throws, the resulting
    RuntimeError carries the *Lean* error message in its body."""
    f = example_lib.py_make_lean_failing_callable(None)
    try:
        f()
    except RuntimeError as e:
        msg = str(e)
        # The closure throws "intentional Lean failure from closure".
        assert "intentional Lean failure" in msg
    else:
        pytest.fail("expected RuntimeError")
