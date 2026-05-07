"""
Refinement-type verification using effectful's algebraic effects + lean-py.

effectful's ``defdata.dispatch(int)`` provides symbolic arithmetic (``+``, ``-``,
``*``, ``>``, ``>=``, etc.) that builds ``Term[int]`` / ``Term[bool]`` trees.

Two handlers interpret these trees:
  - **Lean.Expr handler**: builds ``LeanInductiveValue`` expression trees that
    are passed to Lean's ``goalFromExpr`` for formal verification via ``omega``.
  - **String handler**: produces human-readable Lean syntax strings for display.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Annotated, get_type_hints

from effectful.ops.semantics import evaluate, handler
from effectful.ops.syntax import defdata, defop
from effectful.ops.types import Operation

from expr_builder import ExprBuilder
from lean_py.kernel import GoalState


# ---------------------------------------------------------------------------
#  Refinement annotations
# ---------------------------------------------------------------------------

class Gt:
    """Refinement: value > n."""
    def __init__(self, n: int):
        self.n = n
    def __repr__(self):
        return f"Gt({self.n})"


class Ge:
    """Refinement: value >= n."""
    def __init__(self, n: int):
        self.n = n
    def __repr__(self):
        return f"Ge({self.n})"


# ---------------------------------------------------------------------------
#  assert_refined — effectful operation (intercepted by handler)
# ---------------------------------------------------------------------------

@defop
def assert_refined(value: int, refinement) -> None:
    """Declare that *value* satisfies *refinement*.

    During symbolic execution, the handler intercepts this and collects the
    verification condition as a ``Term[bool]``.
    """
    pass  # no-op in concrete mode


# ---------------------------------------------------------------------------
#  Verification result
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    description: str
    verified: bool

    def __iter__(self):
        return iter((self.description, self.verified))


# ---------------------------------------------------------------------------
#  Term → human-readable Lean syntax string (for display)
# ---------------------------------------------------------------------------

def _build_lean_str(vc_term, var_names, var_ops, precond_terms) -> str:
    """Convert an effectful Term to a Lean proposition string."""
    int_ops = defdata.dispatch(int)

    def _wrap(x):
        s = str(x) if isinstance(x, int) else x
        if isinstance(x, int) and x < 0:
            return f"({s})"
        return s

    str_handler = {}
    for name in var_names:
        str_handler[var_ops[name]] = (lambda n: lambda: n)(name)

    str_handler[int_ops.__add__] = lambda a, b: f"({_wrap(a)} + {_wrap(b)})"
    str_handler[int_ops.__sub__] = lambda a, b: f"({_wrap(a)} - {_wrap(b)})"
    str_handler[int_ops.__mul__] = lambda a, b: f"({_wrap(a)} * {_wrap(b)})"
    str_handler[int_ops.__gt__]  = lambda a, b: f"({_wrap(a)} > {_wrap(b)})"
    str_handler[int_ops.__ge__]  = lambda a, b: f"({_wrap(a)} >= {_wrap(b)})"
    str_handler[int_ops.__lt__]  = lambda a, b: f"({_wrap(a)} < {_wrap(b)})"
    str_handler[int_ops.__le__]  = lambda a, b: f"({_wrap(a)} <= {_wrap(b)})"

    with handler(str_handler):
        body_str = evaluate(vc_term)
        prec_strs = [evaluate(p) for p in precond_terms]

    quant = " ".join(f"({n} : Int)" for n in var_names)
    if prec_strs:
        precs = " → ".join(prec_strs)
        return f"∀ {quant}, {precs} → {body_str}"
    return f"∀ {quant}, {body_str}"


# ---------------------------------------------------------------------------
#  Term → Lean.Expr (for formal verification)
# ---------------------------------------------------------------------------

def _make_expr_handler(eb: ExprBuilder, var_names, var_ops, depth):
    """Build an effectful handler that maps Term ops → Lean.Expr builders.

    *depth* is the number of forallE binders above the expression scope.
    Variable ``var_names[i]`` maps to ``bvar(depth - 1 - i)``.
    """
    int_ops = defdata.dispatch(int)
    h = {}

    for i, name in enumerate(var_names):
        bv = eb.mk_bvar(depth - 1 - i)
        h[var_ops[name]] = (lambda bv=bv: lambda: bv)(bv)

    def coerce(x):
        return eb.mk_int(x) if isinstance(x, int) else x

    h[int_ops.__add__] = lambda a, b: eb.mk_int_add(coerce(a), coerce(b))
    h[int_ops.__sub__] = lambda a, b: eb.mk_int_sub(coerce(a), coerce(b))
    h[int_ops.__mul__] = lambda a, b: eb.mk_int_mul(coerce(a), coerce(b))
    h[int_ops.__gt__]  = lambda a, b: eb.mk_int_gt(coerce(a), coerce(b))
    h[int_ops.__ge__]  = lambda a, b: eb.mk_int_ge(coerce(a), coerce(b))
    h[int_ops.__lt__]  = lambda a, b: eb.mk_int_lt(coerce(a), coerce(b))
    h[int_ops.__le__]  = lambda a, b: eb.mk_int_le(coerce(a), coerce(b))
    return h


def _build_vc_expr(eb: ExprBuilder, vc_term, var_names, var_ops, precond_terms):
    """Convert an effectful VC Term to a ``Lean.Expr`` proposition.

    Builds ``∀ (x : Int) ..., preconds → body`` with correct de Bruijn
    indices at each binder depth.
    """
    n_vars = len(var_names)
    n_preconds = len(precond_terms)
    total = n_vars + n_preconds

    # Evaluate the body at the innermost depth (all binders above).
    with handler(_make_expr_handler(eb, var_names, var_ops, total)):
        body_expr = evaluate(vc_term)

    # Wrap preconditions from innermost outward.
    result = body_expr
    for j in reversed(range(n_preconds)):
        depth = n_vars + j
        with handler(_make_expr_handler(eb, var_names, var_ops, depth)):
            prec_expr = evaluate(precond_terms[j])
        result = eb.mk_forall("_", prec_expr, result)

    # Wrap ∀ variable binders.
    for i in reversed(range(n_vars)):
        result = eb.mk_forall(var_names[i], eb.INT, result)

    return result


# ---------------------------------------------------------------------------
#  Core: verify_function
# ---------------------------------------------------------------------------

def verify_function(fn, lib, kernel) -> list[VerificationResult]:
    """Verify all ``assert_refined`` calls in *fn* hold given its refinements.

    1. Inspect *fn*'s type annotations → create ``defop(int)`` per param +
       preconditions from ``Gt`` / ``Ge`` metadata.
    2. Execute *fn* symbolically → collect VC ``Term``s from ``assert_refined``.
    3. Convert each VC to a ``Lean.Expr`` tree and a display string.
    4. Send Expr to Lean (``goalFromExpr`` + ``intros; omega``).
    """
    hints = get_type_hints(fn, include_extras=True)
    params = inspect.signature(fn).parameters

    # Create symbolic vars and extract preconditions.
    var_ops: dict[str, Operation] = {}
    var_names: list[str] = []
    precond_terms = []

    for name in params:
        var_op = defop(int, name=name)
        var_ops[name] = var_op
        var_names.append(name)

        annotation = hints.get(name)
        if hasattr(annotation, "__metadata__"):
            for meta in annotation.__metadata__:
                if isinstance(meta, Gt):
                    precond_terms.append(var_op() > meta.n)
                elif isinstance(meta, Ge):
                    precond_terms.append(var_op() >= meta.n)

    # Execute symbolically and collect VCs.
    vc_terms: list = []

    def _handle_assert(value, refinement):
        if isinstance(refinement, Gt):
            vc_terms.append(value > refinement.n)
        elif isinstance(refinement, Ge):
            vc_terms.append(value >= refinement.n)

    with handler({assert_refined: _handle_assert}):
        fn(**{name: var_ops[name]() for name in params})

    # Convert each VC to Lean.Expr + description string, then verify.
    eb = ExprBuilder(lib)
    results: list[VerificationResult] = []
    for vc_term in vc_terms:
        desc = _build_lean_str(vc_term, var_names, var_ops, precond_terms)
        lean_expr = _build_vc_expr(eb, vc_term, var_names, var_ops, precond_terms)
        ok = _verify_expr(lib, kernel, lean_expr)
        results.append(VerificationResult(desc, ok))

    return results


# ---------------------------------------------------------------------------
#  Lean verification via goalFromExpr
# ---------------------------------------------------------------------------

def _verify_expr(lib, kernel, lean_expr) -> bool:
    """Create a goal from a ``Lean.Expr`` and close it.

    Uses ``simp [Int.ofNat]`` to normalise the fully-elaborated Int
    literals before ``omega`` decides the linear arithmetic.
    """
    try:
        gs_handle = lib.effectful_goal_from_expr(lean_expr)
        gs = GoalState(kernel, gs_handle)
        result = gs.try_tactic("intros; simp [Int.ofNat] at *; omega")
        return result.ok and result.state is not None and result.state.is_solved()
    except Exception as exc:
        print(f"    [verify error: {exc}]")
        return False
