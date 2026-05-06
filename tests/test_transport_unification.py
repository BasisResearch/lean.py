"""Tests for transport-layer unification (Workstream C).

Verify that ``Py.ofLeanObj`` / ``Py.toLeanObj`` and the C-level
``LeanObjHandle`` type allow Lean objects (``Expr``, ``Name``, etc.)
to pass through the ``Py`` bridge and back.
"""
from __future__ import annotations

import gc

import pytest

from lean_py.marshal import LeanObj


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def kernel(example_lib):
    """Initialize the kernel and load the Init env."""
    example_lib.leanpy_kernel_init_search("")
    example_lib.leanpy_kernel_load_env(["Init"])
    return example_lib


# ---------------------------------------------------------------------------
# Basic LeanObj round-trip
# ---------------------------------------------------------------------------


def test_lean_obj_handle_round_trip(kernel):
    """Create a GoalState (an opaque LeanObj), pass it back to Lean,
    and verify it remains valid."""
    state = kernel.leanpy_kernel_goal_create("Nat")
    assert isinstance(state, LeanObj)
    # The state should be usable after creation
    assert kernel.leanpy_kernel_goal_is_solved(state) is False


def test_lean_obj_handle_survives_gc(kernel):
    """Ensure LeanObj handles survive garbage collection cycles."""
    state = kernel.leanpy_kernel_goal_create("Nat")
    gc.collect()
    gc.collect()
    # Should still be accessible after GC
    assert kernel.leanpy_kernel_goal_n_goals(state) == 1


# ---------------------------------------------------------------------------
# Memory stress
# ---------------------------------------------------------------------------


def test_lean_obj_handle_memory_stress(kernel):
    """Create and drop 500 GoalState handles to verify no memory
    corruption under repeated allocation/deallocation."""
    for _ in range(500):
        state = kernel.leanpy_kernel_goal_create("Nat")
        assert kernel.leanpy_kernel_goal_is_solved(state) is False
        del state
    gc.collect()


def test_lean_obj_handle_concurrent_refs(kernel):
    """Hold multiple LeanObj references simultaneously and verify
    they're independent."""
    states = []
    for _ in range(50):
        states.append(kernel.leanpy_kernel_goal_create("Nat"))
    for s in states:
        assert kernel.leanpy_kernel_goal_is_solved(s) is False
    del states
    gc.collect()
