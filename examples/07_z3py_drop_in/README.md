# 07 — z3py drop-in backed by Lean's `grind`

[Knuckledragger](https://github.com/philzook58/knuckledragger) is an
LCF-style proof assistant whose term language *is* z3py — `kdrag.smt` is
literally `import z3`. That means any tool that speaks the z3py vocabulary
can slot into the same workflow.

`lean_py.z3` provides that vocabulary. Same `Int`, `Bools`, `ForAll`,
`Solver`, `prove` — but the backend is Lean's `grind` tactic instead of
Z3's SMT solver. No Z3 binary, no SAT solver, just the Lean kernel you
already have installed.

```python
# knuckledragger                      # lean_py.z3
import kdrag as kd                     from lean_py.z3 import *
import kdrag.smt as smt

p, q = smt.Bools("p q")               p, q = Bools("p q")
kd.prove(smt.Implies(p,               prove(Implies(p,
    smt.Or(p, q)))                         Or(p, q)))
```

## What you get

Propositional logic, integer/nat/real arithmetic, bit-vectors, arrays,
algebraic datatypes, quantifiers, uninterpreted sorts and functions,
`Solver` with push/pop. See `prove_with_lean.py` for worked examples:
Socrates syllogism, transitivity chains, pigeonhole-style UNSAT, solver
backtracking.

Lean is a proof checker, not an SMT solver. `Solver.check()` returns
`unsat` or `unknown`, never `sat`. Model extraction is not supported.

## Run

```bash
# Against the test fixture (no extra build needed):
cd ../..
DYLD_LIBRARY_PATH=$(lean --print-prefix)/lib/lean \
  python examples/07_z3py_drop_in/prove_with_lean.py

# Or zero-config (builds a managed Lake project on first run):
DYLD_LIBRARY_PATH=$(lean --print-prefix)/lib/lean \
  python examples/07_z3py_drop_in/prove_with_lean.py --managed
```

## Philip's lakefile

Philip Zucker (knuckledragger author) keeps a
[single lakefile](https://github.com/philzook58/philzook58.github.io/blob/master/lakefile.toml)
in his blog repo to make Lean scratch files work with Mathlib. The
`ManagedProject` API does the same thing programmatically:

```python
from lean_py.project import ManagedProject
from lean_py.z3 import *

mp = ManagedProject.get(deps=("mathlib",))
set_kernel(mp.kernel())

x = Int("x")
prove(Implies(x > 0, x * x > 0))
```

No lakefile to maintain. `ManagedProject` creates one under
`~/.lean_py/managed/`, pins deps to your toolchain version, and caches
the build.
