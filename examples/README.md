# lean-py examples

Each subdirectory is a self-contained `lake` project + `uv` project
that path-depends on the lean-py repository root. Build with `lake
build` in `lean/` and run with `uv run --project python python/main.py`.

| Directory | Demonstrates |
| --- | --- |
| [01_basic](./01_basic) | The smallest end-to-end demo: a few `@[python]` functions, an inductive, a structure |
| [02_pantograph_kernel](./02_pantograph_kernel) | Pantograph-style kernel access (load env, infer type, decl axioms, decide propositions) |
| [03_numpy_typed](./03_numpy_typed) | Phantom-typed numpy wrappers in Lean — a pure Lean exe; Python is just numpy's runtime |
| [04_sympy_tactic](./04_sympy_tactic) | A real Lean tactic that closes goals SymPy accepts |
| [05_knuckledragger](./05_knuckledragger) | Same pattern as 04, with Knuckledragger / Z3 as the oracle |
