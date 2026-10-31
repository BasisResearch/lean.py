# Inspect an existing Lean project

This bridge loads compiled `.olean` modules through `Kernel`. It does not link
the inspected project's native libraries or `Mathlib:static`. Build the project
first, using Lean 4.35.0. Declaration lookup and proof tactics then operate on
its imported environment. Native evaluation can require additional libraries.

From the lean.py repository:

```sh
python3 scripts/prepare_lean435.py
lake build
python3 scripts/prepare_lean435.py examples/kernel/lean
(cd examples/kernel/lean && lake build KernelBridge:shared)
uv sync --dev
uv run python examples/kernel/inspect_project.py /path/to/project \
  --module MyProject.Proofs \
  --declaration MyProject.my_theorem
```

The helper resolves each Lake search-path entry against the inspected project.
The bridge imports `LeanPy.Kernel` and `LeanPy.Export`. It does not import the
`LeanPy` umbrella or request a Regex archive, although building the existing
LeanPy static library still builds its Regex dependency.

## Elaborating source against the project

`Kernel.elaborate(source, inherit_env=False)` processes Lean commands against
the loaded environment and returns a `ProcessResult`: per command the
constants it added (names unescaped) and Lean's messages (`severity`, `line`,
`column`, `end_line`, `end_column`, `text`), plus `ok`, `errors` and `error`.
A header (`module`, `import …`) is skipped when its imports are loaded, and is
an `error` naming the missing modules otherwise. With `inherit_env=True` the
declarations persist: later `elaborate`, `decl_type`, `decl_axioms` and goal
calls see them, so a translator can elaborate and check one fragment at a time.

```python
r = kernel.elaborate("def x : Nat := 1", inherit_env=True)
assert r.ok, "\n".join(map(str, r.errors))
print(kernel.decl_type("x"))
```

The runtime is the toolchain of the project `LeanLibrary.from_lake` loads,
whatever the current directory; `LEANPY_TOOLCHAIN`, `LEANPY_LEAN_PREFIX` or
`lean_py.utils.set_toolchain` override it.

## Temporary dependency workaround

Regex `v4.34.0-rc1` triggers a Lean 4.35 `grind` panic in
`Regex.Data.SparseSet.Bijection.surj_of_inj`. Upstream has no Lean 4.35 tag.
`prepare_lean435.py` runs `lake update`, verifies the exact source SHA-256,
and replaces one tactic with `apply Fin.ext; grind -hom [Fin.ext_iff]`.
The theorem statement is unchanged. Lean checks the resulting proof.

Run the helper for each Lake project before building it. It is idempotent and
refuses unexpected source. A plain first `lake build` without this preparation
still fails in Regex. Remove this workaround when a compatible upstream
revision is available.
