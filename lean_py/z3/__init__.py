"""z3py-compatible interface backed by Lean's ``grind`` tactic.

Usage::

    from lean_py.z3 import *

    x, y = Ints('x y')
    prove(Implies(And(x > 0, y > 0), x + y > 0))

    s = Solver()
    s.add(x > 0, x < 0)
    assert s.check() == unsat
"""

from lean_py.z3.core import *  # noqa: F401,F403
from lean_py.z3.solver import *  # noqa: F401,F403
from lean_py.z3.tactic import *  # noqa: F401,F403
