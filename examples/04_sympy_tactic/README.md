# 04 — SymPy as a tactic

A Lean tactic, `sympy`, that sends the current goal's `Lean.Expr` tree
to Python via `Py.ofLeanObj`, where `lean_to_sympy.py` walks the ADT and
converts it to a SymPy expression. If SymPy reports the proposition is
identically true, the goal is closed with an oracle axiom.

```lean
import SymPyTactic

example : (1 : Int) + 1 = 2 := by sympy
example : (3 : Int) * 4 = 12 := by sympy
```

The tactic works by:

1. `Tactic.getMainGoal` to read the current goal's `Lean.Expr`
2. `Py.ofLeanObj` to marshal it to Python as a `LeanInductiveValue` tree
3. `lean_to_sympy.decode_and_check_prop` walks the Expr ADT and builds
   a SymPy expression, then checks if it simplifies to `True`
4. `goal.assign (sympy_oracle goalType)` on accept

No string serialisation — the Lean expression tree crosses the FFI
boundary directly.

## Layout

- `lean/SymPyTactic.lean` — the `sympy` tactic and `@[python]` helpers
- `lean/Demo.lean` — example proofs
- `python/lean_to_sympy.py` — Lean.Expr → SymPy converter (the Python
  backend that the tactic calls)

## Build

```bash
cd lean && lake build
```
