"""z3py-compatible solver backed by Lean's ``grind`` tactic.

The solver constructs Lean goal strings from z3-style expressions and
dispatches them through :class:`lean_py.kernel.Kernel`.  Because Lean is
a proof checker (not an SMT solver), the focus is on proving theorems:

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

from typing import TYPE_CHECKING

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
# Goal string construction
# ---------------------------------------------------------------------------


def _goal_string(expr: BoolRef) -> str:
    """Build a Lean goal string from a z3 expression.

    Collects free variables, sorts them (Type vars first, then functions,
    then values), and wraps in ``forall`` binders.
    """
    free = sorted(expr._vars, key=_var_sort_key)
    if not free:
        return expr._lean
    binders = " ".join(f"({name} : {sort})" for name, sort in free)
    return f"\u2200 {binders}, {expr._lean}"


def _var_sort_key(var: tuple[str, str]) -> tuple[int, str, str]:
    """Sort ordering: Type vars (0), function sigs (1), values (2)."""
    name, sort = var
    if sort == "Type":
        return (0, name, sort)
    if "\u2192" in sort:
        return (1, name, sort)
    return (2, name, sort)


# ---------------------------------------------------------------------------
# Tactic dispatch
# ---------------------------------------------------------------------------

_TACTICS = ["grind", "omega", "decide", "simp_all"]


def _try_prove(goal_str: str) -> bool:
    """Create a goal and try tactics in order. Returns True if proved."""
    k = _get_kernel()
    gs = k.goal_create(goal_str)
    for tac in _TACTICS:
        result = gs.try_tactic(tac)
        if result.ok and result.state is not None and result.state.is_solved():
            return True
    return False


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
        # Try to prove negation of the conjunction
        negated = Not(conj)
        goal = _goal_string(negated)
        if _try_prove(goal):
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
        return f"[{', '.join(a._lean for a in self._assertions)}]"


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def prove(claim: BoolRef) -> bool:
    """Prove a claim directly (no double-negation).

    Returns ``True`` if proved, ``False`` otherwise.
    Prints "proved" or "failed to prove" to match knuckledragger style.
    """
    goal = _goal_string(claim)
    result = _try_prove(goal)
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
    goal = _goal_string(expr) if expr._vars else expr._lean
    return k.whnf(goal)


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "CheckSatResult", "sat", "unsat", "unknown",
    "Solver",
    "set_kernel",
    "prove", "solve", "simplify",
]
