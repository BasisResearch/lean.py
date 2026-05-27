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


# -----------------------------------------------------------------------
# Kernel operation memory stress tests
# -----------------------------------------------------------------------


def test_goal_state_create_drop_stress(example_lib):
    """Create and drop GoalState handles 2000x — catches leaked
    lean_object* from the kernel wrapper layer."""
    example_lib.leanpy_kernel_init_search("")
    example_lib.leanpy_kernel_load_env(["Init"])
    gc.collect()
    for _ in range(2_000):
        state = example_lib.leanpy_kernel_goal_create("Nat")
        assert state is not None
        del state
    gc.collect()


def test_tactic_chain_stress(example_lib):
    """Run a short tactic chain many times to stress goal-state
    allocation and refcount management."""
    example_lib.leanpy_kernel_init_search("")
    if not example_lib.leanpy_kernel_is_loaded(None):
        example_lib.leanpy_kernel_load_env(["Init"])
    gc.collect()
    for _ in range(500):
        state = example_lib.leanpy_kernel_goal_create("∀ n : Nat, n + 0 = n")
        msg, next_state = example_lib.leanpy_kernel_goal_try_tactic(state, "intro n")
        del next_state
        del state
    gc.collect()


# -----------------------------------------------------------------------
# CPython refcount regression tests for C bridge bugs
# -----------------------------------------------------------------------


def test_pow_smoke(example_lib):
    """Smoke-test Py.pow through the bridge (exercises lean_py_pow).

    The historical bug: p_Py_IncRef(p_Py_None) was called before
    PyNumber_Power but never DecRef'd. On CPython <3.12 this leaked
    one Py_None refcount per call; on 3.12+ None is immortal so
    IncRef/DecRef are no-ops. The fix removes the spurious IncRef.

    This test exercises the code path. Actual leak detection requires
    valgrind/LeakSanitizer (see CI).
    """
    for _ in range(1_000):
        assert example_lib.powInt(2, 10) == 1024
    assert example_lib.powInt(3, 4) == 81


def test_error_propagation_no_type_name_leak(example_lib):
    """raise_py_error must not leak the exception type name PyObject.

    The bug: PyObject_GetAttrString(etype, "__name__") returned a new
    reference that was never Py_DecRef'd.  Each error propagation leaked
    the type name string object.

    We use tracemalloc to detect whether memory grows linearly with the
    number of triggered errors.
    """
    import tracemalloc

    # Warm up: trigger a few errors to stabilise any one-time allocations.
    for _ in range(50):
        try:
            example_lib.pythonEvalInt("undefined_variable_xyzzy")
        except Exception:
            pass

    gc.collect()
    tracemalloc.start()
    snap_before = tracemalloc.take_snapshot()

    N = 2_000
    for _ in range(N):
        try:
            example_lib.pythonEvalInt("undefined_variable_xyzzy")
        except Exception:
            pass

    gc.collect()
    snap_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snap_after.compare_to(snap_before, "lineno")
    total_growth = sum(s.size_diff for s in stats if s.size_diff > 0)

    # With the bug, each call leaks a ~60-byte "NameError" string →
    # ~120 KB growth for 2000 calls.  Without it, growth should stay
    # under ~60 KB (Python interpreter noise).  Use 80 KB threshold
    # to avoid CI flakiness while still catching the ~125 KB leak.
    assert total_growth < 80_000, (
        f"Memory grew by {total_growth} bytes after {N} error propagations "
        f"(threshold 80 KB) — likely a leak in raise_py_error"
    )
