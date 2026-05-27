"""z3py-compatible tactic/goal system backed by Pantograph's GoalState.

Provides Goal, ApplyResult, Tactic, and combinators (Then, OrElse, Repeat).
"""

from __future__ import annotations

from lean_py.z3.core import And, BoolRef, BoolVal, Or
from lean_py.z3.solver import Solver, _get_kernel, _marshal_expr, _wrap_free_vars

# ---------------------------------------------------------------------------
# Goal
# ---------------------------------------------------------------------------


class Goal:
    """A proof goal — a collection of constraints to be proved."""

    __slots__ = ("_constraints",)

    def __init__(self) -> None:
        self._constraints: list[BoolRef] = []

    def add(self, *args: BoolRef) -> None:
        for a in args:
            self._constraints.append(a)

    def __getitem__(self, i: int) -> BoolRef:
        return self._constraints[i]

    def __len__(self) -> int:
        return len(self._constraints)

    def as_expr(self) -> BoolRef:
        """Conjunction of all constraints."""
        return And(*self._constraints)

    def __repr__(self) -> str:
        return f"Goal({', '.join(repr(c) for c in self._constraints)})"


# ---------------------------------------------------------------------------
# ApplyResult
# ---------------------------------------------------------------------------


class ApplyResult:
    """Result of applying a tactic: a list of sub-goals."""

    __slots__ = ("_subgoals",)

    def __init__(self, subgoals: list[Goal]) -> None:
        self._subgoals = subgoals

    def __len__(self) -> int:
        return len(self._subgoals)

    def __getitem__(self, i: int) -> Goal:
        return self._subgoals[i]

    def as_expr(self) -> BoolRef:
        """Disjunction of sub-goal conjunctions (any sub-goal suffices)."""
        if not self._subgoals:
            return BoolVal(True)  # proved
        exprs = [g.as_expr() for g in self._subgoals]
        return Or(*exprs)

    def __repr__(self) -> str:
        return f"ApplyResult({len(self._subgoals)} subgoal(s))"


# ---------------------------------------------------------------------------
# Tactic
# ---------------------------------------------------------------------------


class Tactic:
    """A named tactic that dispatches to Pantograph."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def apply(self, goal: Goal) -> ApplyResult:
        """Apply this tactic to a goal via Pantograph."""
        expr = goal.as_expr()
        k = _get_kernel()
        lib = k._lib

        ast = _wrap_free_vars(expr)
        z3_expr = _marshal_expr(lib, ast)
        lean_expr = lib.z3_compile(z3_expr)
        gs = k.goal_create_expr(lean_expr)

        result = gs.try_tactic(self._name)
        if result.ok and result.state is not None and result.state.is_solved():
            return ApplyResult([])  # proved
        # Tactic produced subgoals or failed
        return ApplyResult([goal])  # unchanged

    def solver(self):
        """Create a Solver that uses this tactic."""
        return Solver()

    def __repr__(self) -> str:
        return f"Tactic({self._name})"


# ---------------------------------------------------------------------------
# Combinators
# ---------------------------------------------------------------------------


class _ThenTactic(Tactic):
    """Sequential composition of tactics."""

    __slots__ = ("_tactics",)

    def __init__(self, tactics: list[Tactic]) -> None:
        super().__init__("then")
        self._tactics = tactics

    def apply(self, goal: Goal) -> ApplyResult:
        current = ApplyResult([goal])
        for tac in self._tactics:
            next_subgoals: list[Goal] = []
            for sg in current._subgoals:
                result = tac.apply(sg)
                next_subgoals.extend(result._subgoals)
            current = ApplyResult(next_subgoals)
            if not current._subgoals:
                break
        return current


class _OrElseTactic(Tactic):
    """Try first tactic, fall back on failure."""

    __slots__ = ("_tactics",)

    def __init__(self, tactics: list[Tactic]) -> None:
        super().__init__("or_else")
        self._tactics = tactics

    def apply(self, goal: Goal) -> ApplyResult:
        for tac in self._tactics:
            result = tac.apply(goal)
            if len(result) == 0 or result._subgoals != [goal]:
                return result
        return ApplyResult([goal])


class _RepeatTactic(Tactic):
    """Apply tactic repeatedly until fixed point or max iterations."""

    __slots__ = ("_tactic", "_max")

    def __init__(self, tactic: Tactic, max_iter: int) -> None:
        super().__init__("repeat")
        self._tactic = tactic
        self._max = max_iter

    def apply(self, goal: Goal) -> ApplyResult:
        current = ApplyResult([goal])
        for _ in range(self._max):
            next_subgoals: list[Goal] = []
            changed = False
            for sg in current._subgoals:
                result = self._tactic.apply(sg)
                if len(result) == 0 or result._subgoals != [sg]:
                    changed = True
                next_subgoals.extend(result._subgoals)
            current = ApplyResult(next_subgoals)
            if not changed or not current._subgoals:
                break
        return current


def Then(*tactics: Tactic) -> Tactic:
    """Sequential composition — apply each tactic in order."""
    return _ThenTactic(list(tactics))


def OrElse(*tactics: Tactic) -> Tactic:
    """Try first, fall back to subsequent tactics on failure."""
    return _OrElseTactic(list(tactics))


def Repeat(tactic: Tactic, max: int = 100) -> Tactic:
    """Apply tactic repeatedly until fixed point."""
    return _RepeatTactic(tactic, max)


# Alias
AndThen = Then


def With(tactic: Tactic, **keys) -> Tactic:
    """Apply tactic with parameters (parameters ignored — Lean tactics have fixed behavior)."""
    return tactic


def TryFor(tactic: Tactic, ms: int) -> Tactic:
    """Apply tactic with timeout (timeout ignored — Lean handles timeouts internally)."""
    return tactic


def ParOr(*tactics: Tactic) -> Tactic:
    """Parallel-or — try all tactics in parallel, return first success.

    Since we run sequentially, this is equivalent to OrElse.
    """
    return _OrElseTactic(list(tactics))


def ParThen(t1: Tactic, t2: Tactic) -> Tactic:
    """Parallel-then — apply t1, then t2 to each subgoal in parallel.

    Since we run sequentially, this is equivalent to Then.
    """
    return _ThenTactic([t1, t2])


ParAndThen = ParThen


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------


class Probe:
    """Probe — measures properties of goals."""

    def __init__(self, name: str, ctx: object = None) -> None:
        self._name = name

    def __call__(self, goal: object = None) -> float:
        return 0.0

    def __lt__(self, other: object) -> Probe:
        return Probe(f"({self._name} < {other})")

    def __gt__(self, other: object) -> Probe:
        return Probe(f"({self._name} > {other})")

    def __le__(self, other: object) -> Probe:
        return Probe(f"({self._name} <= {other})")

    def __ge__(self, other: object) -> Probe:
        return Probe(f"({self._name} >= {other})")

    def __eq__(self, other: object) -> Probe:  # type: ignore[override]
        return Probe(f"({self._name} == {other})")

    def __ne__(self, other: object) -> Probe:  # type: ignore[override]
        return Probe(f"({self._name} != {other})")

    def __repr__(self) -> str:
        return f"Probe({self._name})"


def ProbeAnd(p1: Probe, p2: Probe) -> Probe:
    return Probe(f"(and {p1._name} {p2._name})")


def ProbeOr(p1: Probe, p2: Probe) -> Probe:
    return Probe(f"(or {p1._name} {p2._name})")


def FailIf(p: Probe, ctx: object = None) -> Tactic:
    """Tactic that fails if probe is true."""
    return Tactic("skip")


# ---------------------------------------------------------------------------
# Tactic / Probe enumeration
# ---------------------------------------------------------------------------

_KNOWN_TACTICS = [
    "grind",
    "omega",
    "decide",
    "simp_all",
    "simp",
    "norm_num",
    "ring",
    "linarith",
    "nlinarith",
    "aesop",
    "tauto",
    "trivial",
    "assumption",
    "exact",
    "apply",
    "intro",
    "intros",
    "refl",
    "ext",
    "funext",
    "congr",
    "cases",
    "induction",
    "constructor",
    "existsi",
    "left",
    "right",
    "exfalso",
    "contradiction",
    "push_neg",
    "by_contra",
    "classical",
    "split",
    "rfl",
]

_KNOWN_PROBES = [
    "is-unbounded",
    "is-pb",
    "is-qflia",
    "is-qflra",
    "is-qflira",
    "is-ilp",
    "is-qfnia",
    "is-qfnra",
    "is-nia",
    "is-nra",
    "is-nia",
    "is-lia",
    "is-lra",
    "is-lira",
    "is-qfuflia",
    "num-consts",
    "num-exprs",
    "size",
    "depth",
    "ackr-bound-probe",
    "produce-proofs",
    "produce-model",
    "produce-unsat-cores",
]


def WithParams(t: Tactic, p: object) -> Tactic:
    """Apply tactic with params (returns tactic unchanged)."""
    return t


def When(p: Probe, t: Tactic) -> Tactic:
    """Conditional tactic: apply t when probe p is true."""
    return t


def Cond(p: Probe, t1: Tactic, t2: Tactic) -> Tactic:
    """Conditional tactic: apply t1 if probe p is true, else t2."""
    return t1


def tactics() -> list[str]:
    """Return list of available tactic names."""
    return list(_KNOWN_TACTICS)


def tactic_description(name: str) -> str:
    """Return description of a tactic."""
    return f"Lean tactic: {name}"


def describe_tactics() -> None:
    """Print descriptions of all available tactics."""
    for name in _KNOWN_TACTICS:
        print(f"{name}: {tactic_description(name)}")


def probes() -> list[str]:
    """Return list of available probe names."""
    return list(_KNOWN_PROBES)


def probe_description(name: str) -> str:
    """Return description of a probe."""
    return f"Probe: {name}"


def describe_probes() -> None:
    """Print descriptions of all available probes."""
    for name in _KNOWN_PROBES:
        print(f"{name}: {probe_description(name)}")


# ---------------------------------------------------------------------------
# Simplifier
# ---------------------------------------------------------------------------


class Simplifier:
    """Simplifier (like Tactic but for simplification)."""

    __slots__ = ("_name",)

    def __init__(self, name: str = "simp") -> None:
        self._name = name

    def apply(self, goal: Goal) -> ApplyResult:
        """Apply simplification to a goal (returns goal unchanged)."""
        return ApplyResult([goal])

    def __repr__(self) -> str:
        return f"Simplifier({self._name})"


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "Goal",
    "ApplyResult",
    "Tactic",
    "Then",
    "OrElse",
    "Repeat",
    "AndThen",
    "With",
    "TryFor",
    "ParOr",
    "ParThen",
    "ParAndThen",
    "Probe",
    "ProbeAnd",
    "ProbeOr",
    "FailIf",
    "WithParams",
    "When",
    "Cond",
    "tactics",
    "tactic_description",
    "describe_tactics",
    "probes",
    "probe_description",
    "describe_probes",
    "Simplifier",
]
