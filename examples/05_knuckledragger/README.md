# 05 — Knuckledragger / Z3 as a tactic

Same shape as `04_sympy_tactic`, but the back-end is Z3. The Lean
tactic `knuckle` hands the goal to Knuckledragger (or plain `z3` if
Knuckledragger isn't installed) and closes the goal via an oracle
axiom on accept.

```lean
import KnuckleTactic

example : ∀ x : Int, (x + 1)*(x - 1) = x*x - 1 := by knuckle
```

## Layout

- `lean/KnuckleTactic.lean` — `knuckle` tactic and `@[python]` helpers
- `python/knuckle_bridge.py` — the module Lean imports; parses goals
  and dispatches to `kdr.lemma` / `z3.Solver`
- `python/main.py` — runs the helpers on a small fixture set

## Run

```bash
cd lean && lake build && cd ..
uv run --project python python/main.py
```

If you want the real Knuckledragger experience:

```bash
uv add --project python kdrag
```

The bridge will then call `kdr.lemma(...)` instead of using Z3
directly, which gives you Knuckledragger's proof-recording machinery
on top of the SMT call.

The same notes about running the in-Lean tactic from the Lean CLI as
in `04_sympy_tactic/README.md` apply here.
