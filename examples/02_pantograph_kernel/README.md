# 02 — Pantograph-style kernel access

End-to-end Python driver for `LeanPy.Kernel` — the pantograph-equivalent
surface that ships with `lean_py`. The Lean side is intentionally a
two-line shim:

```lean
import LeanPy
import LeanPy.Kernel
#export_python_registry "PantographDemo"
```

Everything the demo uses (`leanpy_kernel_goal_create`,
`leanpy_kernel_goal_try_have`, `leanpy_kernel_frontend_process`,
`leanpy_kernel_delab_unfold_aux_lemmas`, …) comes from `LeanPy.Kernel`
upstream — your own project doesn't need to re-export anything to use
the kernel from Python. The Python driver in `python/main.py` walks
env loading, decl introspection, elaboration, goal state, prograde
tactics, frontend processing, and delab utilities.

Other features of `lean_py` aren't shown here — they have full test
coverage instead:

- **Lean closures as Python callables** (`Py.fromLeanCallable`):
  see `tests/test_callable.py`.
- **Bidirectional `Lean.Expr` introspection**: see
  `tests/test_introspection.py`. Phase 3d (Expr-typed parameters
  driving SymPy) is in `examples/04_sympy_tactic`.
- **Typed exceptions** (`LeanError`, `LeanPyCallbackError`,
  `tryCatchPy`): see `tests/test_exceptions.py` and
  `docs/EXCEPTIONS.md`.
- **Pickling and frontend ops**: see `tests/test_kernel_extra.py`.

## Run

```bash
cd lean && lake build && cd ..
uv run --project python python/main.py
```

## Notes

- `goal_pretty` / `goal_root_expr` / tactic ops on the *same*
  `GoalState` a second time can corrupt state (see
  `docs/ARCHITECTURE.md` "GoalState lifecycle"). The demo creates a
  fresh state per heavy operation.
- All operations come from `lean_py.kernel.Kernel` — there are no
  example-specific Lean wrappers.
