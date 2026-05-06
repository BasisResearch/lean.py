# 02 — Pantograph-style kernel access

A small façade over Lean's `Meta`/`Elab` machinery, exposed to Python in
the spirit of [Pantograph](https://github.com/lenianiva/Pantograph). The
Lean side bundles:

- `demo_init_search`, `demo_load_env` — bring up an environment from Python
- `demo_infer_type`, `demo_whnf`, `demo_pretty` — elaborate / reduce a term
- `demo_decl_type`, `demo_decl_axioms` — inspect named declarations
- `demo_search_decls` — substring search over the constants map
- `demo_decide` — decide a closed `Prop` through `Decidable` synthesis

This is intentionally a thin layer; Pantograph itself exposes a much
larger surface (full goal-state machinery, tactic execution, frontend
parsing). Use this as the seed for your own.

## Run

```bash
cd lean && lake build && cd ..
uv run --project python python/main.py
```
