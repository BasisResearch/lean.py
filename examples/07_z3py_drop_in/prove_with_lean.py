"""
Drop-in replacement for z3py, backed by Lean's grind tactic.

Knuckledragger (https://github.com/philzook58/knuckledragger) uses z3py
as its core expression language — `kdrag.smt` is literally `import z3`.
This script shows the same propositions proved through Lean instead of Z3.

Usage:
    # With an existing Lake project (e.g. tests/lean):
    DYLD_LIBRARY_PATH=$(lean --print-prefix)/lib/lean python prove_with_lean.py

    # Or zero-config via ManagedProject (builds on first run):
    DYLD_LIBRARY_PATH=$(lean --print-prefix)/lib/lean python prove_with_lean.py --managed
"""

from __future__ import annotations

import sys
from pathlib import Path

# -- kernel setup -----------------------------------------------------------

def setup_kernel(managed: bool = False):
    from lean_py.z3 import set_kernel

    if managed:
        from lean_py.project import ManagedProject
        from lean_py.utils import add_lean_lib_to_dyld_path
        add_lean_lib_to_dyld_path()
        mp = ManagedProject.get()
        k = mp.kernel()
        k.load(["Init"])
        set_kernel(k)
        return

    from lean_py import LeanLibrary
    from lean_py.kernel import Kernel
    from lean_py.utils import add_lean_lib_to_dyld_path
    add_lean_lib_to_dyld_path()

    # Point at tests/lean as a convenient pre-built fixture
    project = Path(__file__).resolve().parent.parent.parent / "tests" / "lean"
    lib = LeanLibrary.from_lake(project, "TestLib", build=True)
    k = Kernel(lib)
    k.init_search("")
    k.load(["Init"])
    set_kernel(k)


# -- proofs ------------------------------------------------------------------
# Each function below mirrors a knuckledragger-style proof.
# Where kdrag would write:
#     import kdrag.smt as smt
#     p, q = smt.Bools("p q")
#     kd.prove(smt.Implies(p, smt.Or(p, q)))
#
# We write:
#     from lean_py.z3 import *
#     p, q = Bools("p q")
#     prove(Implies(p, Or(p, q)))
#
# Same vocabulary, different backend.

from lean_py.z3 import *


def propositional_logic():
    """Simple tautologies — the bread and butter of knuckledragger."""
    print("=== Propositional Logic ===")

    p, q = Bools("p q")

    # kdrag: kd.prove(smt.Implies(p, smt.Or(p, q)))
    prove(Implies(p, Or(p, q)))

    # Modus ponens
    prove(Implies(And(p, Implies(p, q)), q))

    # Excluded middle (classical)
    prove(Or(p, Not(p)))

    print()


def integer_arithmetic():
    """Linear arithmetic — where omega shines."""
    print("=== Integer Arithmetic ===")

    x, y, z = Ints("x y z")

    # Basic
    prove(Implies(x > 0, x + 1 > 0))

    # Transitivity chain
    prove(Implies(And(x > y, y > z), x > z))

    # Knuckledragger's favourite: linear combos
    prove(Implies(And(x > 0, y > 0), x + y > 0))

    print()


def nat_arithmetic():
    """Nat-specific reasoning."""
    print("=== Nat Arithmetic ===")

    n, m = Nat("n"), Nat("m")

    prove(ForAll([n], n + 0 == n))
    prove(ForAll([n, m], Implies(n > 0, n + m > 0)))

    print()


def quantifiers_and_uninterpreted():
    """Uninterpreted sorts + functions — the group theory / syllogism pattern.

    This is a core knuckledragger idiom:
        G = smt.DeclareSort("G")
        mul = smt.Function("mul", G, G, G)
        e = smt.Const("e", G)
        ...
    """
    print("=== Quantifiers & Uninterpreted Sorts ===")

    # Socrates syllogism
    Entity = DeclareSort("Entity")
    Man = Function("Man", Entity, BoolSort())
    Mortal = Function("Mortal", Entity, BoolSort())
    socrates = Const("socrates", Entity)
    x = Const("x", Entity)

    prove(Implies(
        And(ForAll([x], Implies(Man(x), Mortal(x))),
            Man(socrates)),
        Mortal(socrates),
    ))

    # Function congruence: f(x) = f(y) if x = y
    S = DeclareSort("S")
    f = Function("f", S, S)
    a, b = Const("a", S), Const("b", S)
    prove(Implies(a == b, f(a) == f(b)))

    print()


def solver_unsat():
    """Using the Solver to detect contradictions (unsat).

    In knuckledragger, you'd use z3.Solver() directly. Here the
    solver drives grind under the hood — same interface, same result.
    """
    print("=== Solver (UNSAT detection) ===")

    x = Int("x")

    s = Solver()
    s.add(x > 0, x < 0)
    result = s.check()
    print(f"  x > 0 ∧ x < 0: {result}")
    assert result == unsat

    # Pigeonhole-flavoured: 3 values in 2 slots
    a, b, c = Ints("a b c")
    s = Solver()
    s.add(Distinct(a, b, c))
    s.add(a >= IntVal(1), a <= IntVal(2))
    s.add(b >= IntVal(1), b <= IntVal(2))
    s.add(c >= IntVal(1), c <= IntVal(2))
    result = s.check()
    print(f"  3 distinct values in {{1,2}}: {result}")
    assert result == unsat

    print()


def push_pop():
    """Solver backtracking — incremental reasoning."""
    print("=== Push/Pop ===")

    x = Int("x")
    s = Solver()
    s.add(x > 0)

    s.push()
    s.add(x < 0)
    assert s.check() == unsat
    print("  After push + contradiction: unsat")
    s.pop()

    # Back to just x > 0 — satisfiable, so we get unknown
    # (Lean proves things, doesn't find models)
    assert s.check() == unknown
    print("  After pop (x > 0 only): unknown (can't prove negation)")

    print()


# -- main --------------------------------------------------------------------

if __name__ == "__main__":
    managed = "--managed" in sys.argv
    setup_kernel(managed=managed)

    propositional_logic()
    integer_arithmetic()
    nat_arithmetic()
    quantifiers_and_uninterpreted()
    solver_unsat()
    push_pop()

    print("All proofs discharged.")
