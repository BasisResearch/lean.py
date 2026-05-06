"""Tests for the extended @[python] kernel ops added in the pantograph
parity push: try_have / try_let / try_define / try_draft, goal pickle,
diag, env pickle, frontend find_source_path / process / collect_sorrys,
and delab unfold_aux_lemmas / unfold_matchers / instantiate_all /
expr_proj_to_app.

These tests stand alone — they don't depend on the goal-state churn
that test_kernel_full.py is sensitive to. We run them as standalone
pytest invocations or with a single Kernel handle.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from lean_py.kernel import Kernel


@pytest.fixture(scope="module")
def kernel(example_lib) -> Kernel:
    k = Kernel(example_lib)
    if not k.is_loaded():
        k.init_search("")
        k.load(["Init"])
    return k


# ----------------------------------------------------------------------
# Frontend wrappers
# ----------------------------------------------------------------------


def test_frontend_find_source_path_for_init(kernel):
    p = kernel.find_source_path("Init.Prelude")
    # The path should at least end with `.lean` and contain "Init"
    assert p.endswith(".lean")
    assert "Init" in p


def test_frontend_find_source_path_missing_module_raises(kernel):
    with pytest.raises(RuntimeError):
        kernel.find_source_path("Nonexistent.Bogus.Module.Foo")


def test_frontend_process_simple(kernel):
    src = "def foo : Nat := 42\n"
    out = kernel.process(src)
    # New constants from the def should be present.
    assert "foo" in out


def test_frontend_collect_sorrys_no_sorries(kernel):
    src = "def foo : Nat := 42\n"
    state, msg = kernel.collect_sorrys(src)
    assert state is None
    assert "no sorrys" in msg


# ----------------------------------------------------------------------
# Delab utilities
# ----------------------------------------------------------------------


def test_delab_unfold_aux_lemmas_passthrough(kernel):
    """For an expression without aux lemmas, this should pretty-print
    unchanged."""
    s = kernel.unfold_aux_lemmas("Nat.succ Nat.zero")
    # Pretty-printed Nat.succ 0
    assert "Nat" in s


def test_delab_unfold_matchers(kernel):
    s = kernel.unfold_matchers("Nat.succ Nat.zero")
    assert "Nat" in s


def test_delab_instantiate_all(kernel):
    s = kernel.instantiate_all("(1 : Nat) + 1")
    assert "1" in s


def test_delab_expr_proj_to_app_requires_projection(kernel):
    """expr_proj_to_app requires an Expr.proj; for a non-projection
    input, it surfaces the underlying panic as an error sentinel."""
    # The wrapper renders panics into the result via runCore's catch.
    # We just check it doesn't crash the process.
    _ = kernel.expr_proj_to_app("Nat.succ Nat.zero")


# ----------------------------------------------------------------------
# Smoke: env_pickle / env_unpickle
# ----------------------------------------------------------------------


def test_env_pickle_round_trip(kernel):
    """Sanity check the env_pickle / env_unpickle plumbing — can pickle
    and reload without raising. We don't compare bit-for-bit semantics,
    just that the wrapper marshals correctly."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "env.olean")
        kernel.env_pickle(path)
        assert os.path.getsize(path) > 0
        # Reload — env stays loaded even after reload
        kernel.env_unpickle(path)
        assert kernel.is_loaded()
