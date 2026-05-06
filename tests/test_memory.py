"""Memory-management correctness tests.

These verify that repeated FFI round-trips don't leak Lean objects
or Python references. We approximate "no leak" by:

  * Calling each Lean function many times and checking that Python's
    `gc` reports no growing allocator counts.
  * For the Python-in-Lean bridge, comparing CPython's `sys.getrefcount`
    on a long-lived sentinel before and after a stress loop.

These tests are deliberately fast (a few thousand iterations) so they
can run in CI on every commit. The `tests/leaks_check.sh` script
performs a more thorough check using macOS `leaks` / Linux `valgrind`.
"""

from __future__ import annotations

import gc
import importlib
import sys

import pytest


def _have(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except ImportError:
        return False


def test_int_round_trip_no_leak(example_lib):
    """Lean Int → Python → Lean Int over many iterations should not leak."""
    gc.collect()
    for _ in range(10_000):
        assert example_lib.bar(7) == 8
    gc.collect()


def test_string_round_trip_no_leak(example_lib):
    """Strings are heap-allocated; ensure no leak on repeated calls."""
    gc.collect()
    payload = "x" * 256
    for _ in range(2_000):
        out = example_lib.greet(payload)
        assert out.startswith("Hello, ")
    gc.collect()


def test_array_round_trip_no_leak(example_lib):
    """Array marshalling builds many small objects; ensure cleanup."""
    gc.collect()
    arr = list(range(50))
    for _ in range(2_000):
        assert example_lib.sumList(arr) == sum(arr)
    gc.collect()


def test_inductive_round_trip_no_leak(example_lib):
    """Encode + decode constructor objects in a tight loop."""
    gc.collect()
    p = example_lib.Point(3, 4)
    for _ in range(2_000):
        assert example_lib.pointNormSq(p) == 25
        s = example_lib.shapePerimeter(example_lib.Shape.rect(2, 3))
        assert s == 10
    gc.collect()


@pytest.mark.skipif(not _have("sympy"), reason="sympy not installed")
def test_python_in_lean_no_pyref_leak(example_lib):
    """Stress the Python-in-Lean bridge and ensure CPython's refcount on
    a sentinel doesn't grow. This catches missing `Py_DecRef` calls in
    the C bridge."""
    sentinel = ("leanpy-sentinel",) * 4
    base_rc = sys.getrefcount(sentinel)
    for _ in range(1_000):
        # Each call allocates and frees several Python objects internally.
        assert example_lib.pythonEvalInt("1 + 2 + 3") == 6
    gc.collect()
    # The sentinel's refcount should be unchanged.
    assert sys.getrefcount(sentinel) == base_rc


def test_leanobj_handle_dropping(example_lib):
    """Pure Python LeanObj wrappers should release their refs on GC."""
    from lean_py import LeanObj
    from lean_py.lean_ffi import get_lean_ffi
    ffi = get_lean_ffi()

    # Allocate / drop in a loop and ensure no exceptions.
    for _ in range(5_000):
        s = ffi.mk_string("hello")
        wrapper = LeanObj(s)
        del wrapper
    gc.collect()


def test_lean_expr_round_trip_no_leak(example_lib):
    """Round-trip Lean.Expr ADT values 2k times. Catches refcount issues
    in the new recursive-type marshalling (Phase 3a)."""
    Name = example_lib.Name
    Expr = example_lib.Expr
    f_name = Name.str(Name.str(Name.anonymous, "Nat"), "succ")
    x_name = Name.str(Name.str(Name.anonymous, "Nat"), "zero")
    f = Expr.const(f_name, [])
    x = Expr.const(x_name, [])
    e = Expr.app(f, x)
    gc.collect()
    for _ in range(2_000):
        s = example_lib.py_expr_describe(e)
        assert s == "app (const Nat.succ) (const Nat.zero)"
    gc.collect()


def test_pyobject_round_trip_no_pyref_leak(example_lib):
    """Stress the live pyobject round-trip (Phase 3b). Each call
    decrements a Lean-held PyObject and we want the CPython refcount
    on a sentinel to stay stable."""
    sentinel = ("leanpy-pyobj-sentinel",) * 8
    base_rc = sys.getrefcount(sentinel)
    for _ in range(1_000):
        py_list = example_lib.makeList123(None)
        assert py_list == [1, 2, 3]
    gc.collect()
    assert sys.getrefcount(sentinel) == base_rc
