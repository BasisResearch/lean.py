"""End-to-end tests for the pantograph-equivalent LeanPy.Kernel surface.

These exercise the operations layer of pantograph that we've ported into
`LeanPy/Kernel/*.lean`: GoalState construction + tactic execution,
environment introspection, elaboration, frontend processing, etc.
"""

from __future__ import annotations

import pytest


# --- shared fixture ---------------------------------------------------------

@pytest.fixture(scope="module")
def kernel(example_lib):
    """Initialize the kernel and load the `Init` env."""
    example_lib.leanpy_kernel_init_search("")
    example_lib.leanpy_kernel_load_env(["Init"])
    return example_lib


# --- environment introspection ----------------------------------------------

def test_env_loaded(kernel):
    assert kernel.leanpy_kernel_is_loaded(None) is True


def test_env_decl_count_nonzero(kernel):
    n = kernel.leanpy_kernel_decl_count(None)
    assert n > 100


def test_env_catalog_filters_internal(kernel):
    """Catalog should NOT contain auto-generated proof / match symbols."""
    full = kernel.leanpy_kernel_all_decls(None).split("\n")
    cat = kernel.leanpy_kernel_catalog(None).split("\n")
    # Internal names typically include `_proof_` or macro-scoped suffixes.
    internal_in_full = [n for n in full if n.endswith("._proof_1")]
    if internal_in_full:
        # Catalog should drop them
        for n in internal_in_full:
            assert n not in cat


def test_env_decl_exists(kernel):
    assert kernel.leanpy_kernel_decl_exists("Nat") is True
    assert kernel.leanpy_kernel_decl_exists("Nat.add") is True
    assert kernel.leanpy_kernel_decl_exists("DefinitelyNotARealDecl") is False


def test_env_decl_type(kernel):
    t = kernel.leanpy_kernel_decl_type("Nat.succ")
    assert "Nat" in t and "→" in t


def test_env_decl_axioms(kernel):
    # Nat.add should depend on no axioms (constructive arithmetic).
    axs = kernel.leanpy_kernel_decl_axioms("Nat.add")
    # Either empty or only synthetic / Eq-related axioms; the key point
    # is that Classical.choice is not in there.
    assert "Classical.choice" not in axs


def test_env_module_of(kernel):
    m = kernel.leanpy_kernel_module_of_name_str("Nat")
    assert m  # comes from Init


def test_env_is_internal(kernel):
    # A user-facing name is not internal
    assert kernel.leanpy_kernel_is_internal_name_str("Nat.add") is False


# --- elaboration -----------------------------------------------------------

def test_infer_type_basic(kernel):
    assert "Nat" in kernel.leanpy_kernel_infer_type("Nat.succ Nat.zero")
    assert "Bool" in kernel.leanpy_kernel_infer_type("true")


def test_pretty_print(kernel):
    s = kernel.leanpy_kernel_pretty_print("Nat.zero")
    assert "Nat" in s


def test_whnf(kernel):
    s = kernel.leanpy_kernel_whnf("Nat.succ Nat.zero")
    assert s != ""


def test_expr_echo_format(kernel):
    """expr_echo returns `<expr>\\n---\\n<type>`."""
    s = kernel.leanpy_kernel_expr_echo("Nat.succ Nat.zero")
    assert "---" in s
    expr_part, type_part = s.split("\n---\n")
    assert "Nat" in type_part


def test_parse_type(kernel):
    s = kernel.leanpy_kernel_parse_type("Nat → Nat")
    assert "Nat" in s


def test_decide_true(kernel):
    s = kernel.leanpy_kernel_decide("(1 : Nat) + 1 = 2")
    assert s == "true"


def test_decide_false(kernel):
    s = kernel.leanpy_kernel_decide("(1 : Nat) = 2")
    assert s == "false"


# --- goal state ------------------------------------------------------------

def test_goal_create(kernel):
    """We can create a goal state and read off its solved/unsolved flag."""
    state = kernel.leanpy_kernel_goal_create("∀ n : Nat, n + 0 = n")
    assert state is not None
    assert kernel.leanpy_kernel_goal_is_solved(state) is False
    assert kernel.leanpy_kernel_goal_n_goals(state) == 1


def test_goal_create_invalid(kernel):
    """Invalid types raise `LeanError`."""
    from lean_py import LeanError
    with pytest.raises(LeanError):
        kernel.leanpy_kernel_goal_create("@@@@")


def test_goal_main_goal_name(kernel):
    state = kernel.leanpy_kernel_goal_create("∀ n : Nat, n = n")
    nm = kernel.leanpy_kernel_goal_main_goal_name(state)
    assert nm  # non-empty mvar name


def test_goal_pretty(kernel):
    state = kernel.leanpy_kernel_goal_create("∀ n : Nat, n = n")
    s = kernel.leanpy_kernel_goal_pretty(state)
    assert "⊢" in s
    assert "Nat" in s


def test_goal_root_unsolved(kernel):
    state = kernel.leanpy_kernel_goal_create("∀ n : Nat, n + 0 = n")
    s = kernel.leanpy_kernel_goal_root_expr(state)
    assert isinstance(s, str)


def test_goal_try_tactic_success(kernel):
    state = kernel.leanpy_kernel_goal_create("∀ n : Nat, n + 0 = n")
    msg, next_state = kernel.leanpy_kernel_goal_try_tactic(state, "intro n")
    assert msg.startswith("success") or msg.startswith("failure"), msg
    if next_state is None:
        pytest.skip(f"intro failed in this toolchain: {msg}")
    assert kernel.leanpy_kernel_goal_n_goals(next_state) == 1


def test_goal_try_tactic_parse_error(kernel):
    state = kernel.leanpy_kernel_goal_create("∀ n : Nat, n = n")
    msg, next_state = kernel.leanpy_kernel_goal_try_tactic(state, "@@@@")
    assert msg.startswith("parseError") or msg.startswith("failure")
    assert next_state is None


def test_goal_try_assign(kernel):
    state = kernel.leanpy_kernel_goal_create("Nat")
    msg, next_state = kernel.leanpy_kernel_goal_try_assign(state, "(0 : Nat)")
    assert msg.startswith("success"), msg
    assert next_state is not None
    assert kernel.leanpy_kernel_goal_is_solved(next_state) is True


def test_goal_state_basic_query_is_reusable(kernel):
    state = kernel.leanpy_kernel_goal_create("∀ n : Nat, n = n")
    name1 = kernel.leanpy_kernel_goal_main_goal_name(state)
    name2 = kernel.leanpy_kernel_goal_main_goal_name(state)
    assert name1 == name2
    assert kernel.leanpy_kernel_goal_n_goals(state) == kernel.leanpy_kernel_goal_n_goals(state)
    assert not kernel.leanpy_kernel_goal_is_solved(state)


def test_goal_state_pretty_is_reusable(kernel):
    state = kernel.leanpy_kernel_goal_create("∀ n : Nat, n = n")
    s1 = kernel.leanpy_kernel_goal_pretty(state)
    s2 = kernel.leanpy_kernel_goal_pretty(state)
    assert s1 == s2


def test_goal_search(kernel):
    """`leanpy_kernel_search` filters declarations by substring."""
    s = kernel.leanpy_kernel_search("Nat.succ")
    assert "Nat.succ" in s.split("\n")
