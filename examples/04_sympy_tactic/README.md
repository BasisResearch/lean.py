# 04 — SymPy as a tactic

A real Lean tactic, `sympy`, that hands the current goal to SymPy via
the lean-py Python bridge and closes the goal via an oracle axiom if
SymPy reports the proposition is identically true.

```lean
import SymPyTactic

example : (1 : Int) + 1 = 2 := by sympy
example : (3 : Int) * 4 = 12 := by sympy
```

The tactic is a thin wrapper:

1. `Tactic.getMainGoal` to read the current `Expr`
2. `Meta.ppExpr` for a SymPy-friendly rendering (replacing `=` with
   `Eq(...,...)`)
3. `sympy_accept` — the IO-marked Python bridge call
4. `goal.assign (sympy_oracle goalType)` on accept

Treat it as a textbook "computer-algebra oracle": the proof is
"trust SymPy on this fragment", in the same spirit as papers that use
Mathematica or Z3 as a black-box decider.

## Layout

- `lean/SymPyTactic.lean` — the tactic and its Python-callable helpers
- `lean/Demo.lean` — example proofs that drive the tactic
- `python/main.py` — exercises the Python-callable surface only
  (`sympy_simplify`, `sympy_accept`, `sympy_eq_accept`)

## Run

```bash
cd lean && lake build && cd ..
uv run --project python python/main.py
```

To run the Lean tactic *inside Lean* (rather than the helper functions
from Python), use a host process that already has `libpython` and
`sympy` available:

```bash
cd lean
PYTHONPATH=$(python -c 'import sys; print(":".join(sys.path))') \
  LEANPY_LIBPYTHON=$(python -c 'import sys, ctypes.util; print(ctypes.util.find_library(f"python{sys.version_info.major}.{sys.version_info.minor}"))') \
  lake env lean Demo.lean
```

The interpreter needs the native bridge linked in; running through the
lean CLI may report "could not find native implementation" — in
practice the tactic is most useful from a hosted environment (the
LeanLibrary loaded by Python, or a binary with `supportInterpreter`).
