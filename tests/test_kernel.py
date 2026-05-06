"""End-to-end tests for the Pantograph-equivalent `LeanPy.Kernel` API.

These exercise loading a Lean environment from Python, looking up
declarations, parsing/elaborating terms, and inferring types — the core
operations Pantograph exposes for tactic-state inspection.

The kernel API is exposed via the same `TestLib` fixture as every
other test in the suite, so all tests share one Python process / one
Lean runtime."""

import pytest


@pytest.fixture(scope="session")
def kernel(example_lib):
    """Initialise Lean's search path and load a baseline `Init` env."""
    example_lib.leanpy_kernel_init_search("")
    example_lib.leanpy_kernel_load_env(["Init"])
    return example_lib


def test_kernel_loaded(kernel):
    assert kernel.leanpy_kernel_is_loaded(None) is True
    n = kernel.leanpy_kernel_decl_count(None)
    assert n > 100  # Init has many decls


def test_decl_exists(kernel):
    assert kernel.leanpy_kernel_decl_exists("Nat") is True
    assert kernel.leanpy_kernel_decl_exists("Bool") is True
    assert kernel.leanpy_kernel_decl_exists("Nat.add") is True
    assert kernel.leanpy_kernel_decl_exists("DefinitelyNotARealDecl") is False


def test_decl_type(kernel):
    # Nat is a Type
    t = kernel.leanpy_kernel_decl_type("Nat")
    assert "Type" in t

    # Nat.succ : Nat → Nat
    t = kernel.leanpy_kernel_decl_type("Nat.succ")
    assert "Nat" in t and "→" in t


def test_pretty_print(kernel):
    pp = kernel.leanpy_kernel_pretty_print("Nat.zero")
    assert "Nat" in pp


def test_infer_type(kernel):
    t = kernel.leanpy_kernel_infer_type("Nat.succ Nat.zero")
    assert "Nat" in t

    t = kernel.leanpy_kernel_infer_type("true")
    assert "Bool" in t

    t = kernel.leanpy_kernel_infer_type("\"hello\"")
    assert "String" in t


def test_whnf(kernel):
    r = kernel.leanpy_kernel_whnf("Nat.succ Nat.zero")
    assert r != ""
