# 05 — Knuckledragger / Z3 as a tactic

Same shape as `04_sympy_tactic`, but the back-end is Z3. The Lean tactic
`knuckle` sends the goal's `Lean.Expr` tree to Python via `Py.ofLeanObj`,
where `lean_to_z3.py` walks the ADT and converts it to a Z3 expression.
If Z3 (or Knuckledragger) discharges the proposition, the goal is closed
via an oracle axiom.

```lean
import KnuckleTactic

example : (1 : Int) + 1 = 2 := by knuckle
example : (3 : Int) * 4 = 12 := by knuckle
```

## Layout

- `lean/KnuckleTactic.lean` — the `knuckle` tactic and `@[python]` helpers
- `lean/Demo.lean` — example proofs
- `python/lean_to_z3.py` — Lean.Expr → Z3 converter (the Python backend
  that the tactic calls)

## Build

```bash
cd lean && lake build
```

If you want the real Knuckledragger experience:

```bash
uv add --project python kdrag
```

The bridge will then call `kdr.lemma(...)` instead of using Z3 directly,
which gives you Knuckledragger's proof-recording machinery on top of the
SMT call.
