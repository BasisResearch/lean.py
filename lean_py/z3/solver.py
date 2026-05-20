"""z3py-compatible solver backed by Lean's ``grind`` tactic.

The solver constructs Lean Z3Expr AST values from z3-style expressions
and dispatches them through :class:`lean_py.kernel.Kernel`. The Lean
side compiles the AST to fully elaborated ``Lean.Expr`` via MetaM.

- **unsat** means the negation of the conjunction was proved (the
  constraints are contradictory).
- **sat** is never returned -- Lean cannot produce models.
- **unknown** means grind could not discharge the goal.

Typical usage::

    from lean_py.z3 import *
    x, y = Ints('x y')
    prove(Implies(And(x > 0, y > 0), x + y > 0))
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lean_py.z3._ast import (
    ASTNode,
    ASTSort,
    AppNode,
    ArrowASTSort,
    BitvecASTSort,
    BinOp,
    BinOpNode,
    BoolLit,
    BvLit,
    ConstArrayNode,
    DistinctNode,
    ExistsNode,
    ForAllNode,
    IntASTSort,
    IntLit,
    IteNode,
    NatASTSort,
    NatLit,
    PropSort,
    RealASTSort,
    SelectNode,
    StoreNode,
    UnOp,
    UnOpNode,
    TypeASTSort,
    UninterpASTSort,
    Var,
)
from lean_py.z3.core import (
    And,
    BoolRef,
    BoolVal,
    ExprRef,
    Not,
)

if TYPE_CHECKING:
    from lean_py.kernel import Kernel

# ---------------------------------------------------------------------------
# CheckSatResult
# ---------------------------------------------------------------------------


class CheckSatResult:
    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return self._name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CheckSatResult) and self._name == other._name

    def __hash__(self) -> int:
        return hash(self._name)

    def __bool__(self) -> bool:
        raise TypeError(
            "CheckSatResult cannot be used as bool; compare to sat/unsat/unknown"
        )


sat = CheckSatResult("sat")
unsat = CheckSatResult("unsat")
unknown = CheckSatResult("unknown")


# ---------------------------------------------------------------------------
# Kernel management
# ---------------------------------------------------------------------------

_kernel: Kernel | None = None


def set_kernel(k: Kernel) -> None:
    """Set the global kernel used by solvers and ``prove()``."""
    global _kernel
    _kernel = k


def _get_kernel() -> Kernel:
    global _kernel
    if _kernel is not None:
        return _kernel
    # Lazy init via ManagedProject
    from lean_py.project import ManagedProject

    mp = ManagedProject.get()
    _kernel = mp.kernel()
    return _kernel


# ---------------------------------------------------------------------------
# AST marshalling (Python AST → Lean Z3Sort/Z3BinOp/Z3UnOp/Z3Expr)
# ---------------------------------------------------------------------------


def _marshal_sort(lib: Any, sort: ASTSort) -> Any:
    """Convert a Python ASTSort to a Lean Z3Sort value."""
    Z3Sort = lib.Z3Sort
    if isinstance(sort, PropSort):
        return Z3Sort.prop
    if isinstance(sort, IntASTSort):
        return Z3Sort.int
    if isinstance(sort, NatASTSort):
        return Z3Sort.nat
    if isinstance(sort, RealASTSort):
        return Z3Sort.real
    if isinstance(sort, TypeASTSort):
        return Z3Sort.type
    if isinstance(sort, BitvecASTSort):
        return Z3Sort.bitvec(sort.width)
    if isinstance(sort, UninterpASTSort):
        return Z3Sort.uninterp(sort.name)
    if isinstance(sort, ArrowASTSort):
        dom = _marshal_sort(lib, sort.dom)
        cod = _marshal_sort(lib, sort.cod)
        return Z3Sort.arrow(dom, cod)
    raise TypeError(f"Unknown ASTSort: {type(sort)}")


def _marshal_binop(lib: Any, op: str) -> Any:
    """Convert a BinOp string to a Lean Z3BinOp value."""
    Z3BinOp = lib.Z3BinOp
    return getattr(Z3BinOp, op)


def _marshal_unop(lib: Any, op: str) -> Any:
    """Convert a UnOp string to a Lean Z3UnOp value."""
    Z3UnOp = lib.Z3UnOp
    return getattr(Z3UnOp, op)


def _marshal_expr(lib: Any, node: ASTNode) -> Any:
    """Convert a Python ASTNode to a Lean Z3Expr value."""
    Z3Expr = lib.Z3Expr
    if isinstance(node, Var):
        return Z3Expr.var(node.name)
    if isinstance(node, IntLit):
        return Z3Expr.intLit(node.val)
    if isinstance(node, NatLit):
        return Z3Expr.natLit(node.val)
    if isinstance(node, BoolLit):
        return Z3Expr.boolLit(node.val)
    if isinstance(node, BvLit):
        return Z3Expr.bvLit(node.val, node.width)
    if isinstance(node, BinOpNode):
        op = _marshal_binop(lib, node.op)
        lhs = _marshal_expr(lib, node.lhs)
        rhs = _marshal_expr(lib, node.rhs)
        return Z3Expr.binop(op, lhs, rhs)
    if isinstance(node, UnOpNode):
        op = _marshal_unop(lib, node.op)
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.unop(op, arg)
    if isinstance(node, IteNode):
        cond = _marshal_expr(lib, node.cond)
        then_ = _marshal_expr(lib, node.then_)
        else_ = _marshal_expr(lib, node.else_)
        return Z3Expr.ite(cond, then_, else_)
    if isinstance(node, ForAllNode):
        sort = _marshal_sort(lib, node.sort)
        body = _marshal_expr(lib, node.body)
        return Z3Expr.forall_(node.name, sort, body)
    if isinstance(node, ExistsNode):
        sort = _marshal_sort(lib, node.sort)
        body = _marshal_expr(lib, node.body)
        return Z3Expr.exists_(node.name, sort, body)
    if isinstance(node, AppNode):
        func = _marshal_expr(lib, node.func)
        args = [_marshal_expr(lib, a) for a in node.args]
        return Z3Expr.app(func, args)
    if isinstance(node, DistinctNode):
        args = [_marshal_expr(lib, a) for a in node.args]
        return Z3Expr.distinct(args)
    if isinstance(node, SelectNode):
        arr = _marshal_expr(lib, node.arr)
        idx = _marshal_expr(lib, node.idx)
        return Z3Expr.select(arr, idx)
    if isinstance(node, StoreNode):
        arr = _marshal_expr(lib, node.arr)
        idx = _marshal_expr(lib, node.idx)
        val = _marshal_expr(lib, node.val)
        return Z3Expr.store(arr, idx, val)
    if isinstance(node, ConstArrayNode):
        dom_sort = _marshal_sort(lib, node.dom_sort)
        val = _marshal_expr(lib, node.val)
        return Z3Expr.constArray(dom_sort, val)
    raise TypeError(f"Unknown ASTNode: {type(node)}")


# ---------------------------------------------------------------------------
# Variable sort key (for ordering free variables)
# ---------------------------------------------------------------------------


def _var_sort_key(var: tuple[str, ASTSort]) -> tuple[int, str]:
    """Sort ordering: Type vars (0), function sigs (1), values (2)."""
    name, sort = var
    if isinstance(sort, TypeASTSort):
        return (0, name)
    if isinstance(sort, ArrowASTSort):
        return (1, name)
    return (2, name)


# ---------------------------------------------------------------------------
# Core prove function
# ---------------------------------------------------------------------------


def _wrap_free_vars(expr: BoolRef) -> ASTNode:
    """Wrap the expression AST in ForAll nodes for its free variables.

    Sorts free vars: Type vars first, arrows (functions) second, values last.
    """
    free = sorted(expr._vars, key=_var_sort_key)
    ast: ASTNode = expr._ast
    for name, sort in reversed(free):
        ast = ForAllNode(name=name, sort=sort, body=ast)
    return ast


def _try_prove(expr: BoolRef) -> bool:
    """Compile AST to Lean.Expr, create goal, try tactics. Returns True if proved."""
    k = _get_kernel()
    lib = k._lib

    # Wrap free vars in ForAll
    ast = _wrap_free_vars(expr)

    # Marshal to Lean Z3Expr
    z3_expr = _marshal_expr(lib, ast)

    # Compile to Lean.Expr
    lean_expr = lib.z3_compile(z3_expr)

    # Create goal state from the Lean.Expr
    gs = k.goal_create_expr(lean_expr)

    # Try tactics
    for tac in _TACTICS:
        result = gs.try_tactic(tac)
        if result.ok and result.state is not None and result.state.is_solved():
            return True
    return False


# ---------------------------------------------------------------------------
# Tactic dispatch
# ---------------------------------------------------------------------------

_TACTICS = ["grind", "omega", "decide", "simp_all"]


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------


class Solver:
    """z3py-compatible solver interface.

    ``check()`` builds the conjunction of all assertions, negates it,
    and tries to prove the negation via grind.  If proved, returns
    ``unsat`` (the constraints are contradictory).  Otherwise ``unknown``.
    """

    def __init__(self) -> None:
        self._assertions: list[BoolRef] = []
        self._stack: list[int] = []

    def add(self, *args: BoolRef) -> None:
        for a in args:
            self._assertions.append(a)

    def push(self) -> None:
        self._stack.append(len(self._assertions))

    def pop(self, n: int = 1) -> None:
        for _ in range(n):
            if not self._stack:
                raise IndexError("pop from empty solver stack")
            self._assertions = self._assertions[: self._stack.pop()]

    def check(self) -> CheckSatResult:
        if not self._assertions:
            return unknown
        conj = And(*self._assertions)
        negated = Not(conj)
        if _try_prove(negated):
            return unsat
        return unknown

    def assertions(self) -> list[BoolRef]:
        return list(self._assertions)

    def reset(self) -> None:
        self._assertions.clear()
        self._stack.clear()

    def __enter__(self) -> Solver:
        self.push()
        return self

    def __exit__(self, *exc) -> None:
        self.pop()

    def __repr__(self) -> str:
        return f"[{', '.join(repr(a) for a in self._assertions)}]"


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def prove(claim: BoolRef) -> bool:
    """Prove a claim directly (no double-negation).

    Returns ``True`` if proved, ``False`` otherwise.
    Prints "proved" or "failed to prove" to match knuckledragger style.
    """
    result = _try_prove(claim)
    if result:
        print("proved")
    else:
        print("failed to prove")
    return result


def solve(*args: BoolRef) -> CheckSatResult:
    """Shorthand: create solver, add args, check."""
    s = Solver()
    s.add(*args)
    return s.check()


def simplify(expr: ExprRef) -> str:
    """Reduce an expression via Lean's ``whnf``."""
    k = _get_kernel()
    # For simplify, fall back to string-based approach since it's just whnf
    return k.whnf(repr(expr))


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "CheckSatResult", "sat", "unsat", "unknown",
    "Solver",
    "set_kernel",
    "prove", "solve", "simplify",
]
