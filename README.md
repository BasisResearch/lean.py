# lean-py

Effortless interop between **Lean 4** and **Python**, in both directions.

* **Lean -> Python.** Annotate any Lean definition with `@[python "name"]`
  and call it from Python with automatic type marshalling.
  `derive_python` exposes inductives and structures as Python constructors.
* **Python -> Lean.** `LeanPy.Python` gives Lean code a `Py` type with
  `import_`, `eval`, `exec`, `getAttr`, `call`, etc. CPython is loaded
  lazily via `dlopen`.
* **Kernel facade.** `LeanPy.Kernel` wraps the
  [Pantograph](https://github.com/leanprover/Pantograph) library so a
  Python process can drive Lean's type-checker, elaborator, and tactic
  engine without spawning a subprocess.

## Install

### Python side

```bash
uv pip install "lean_py @ git+https://github.com/kiranandcode/lean.py"
```

or in `pyproject.toml`:

```toml
[project]
dependencies = ["lean_py @ git+https://github.com/kiranandcode/lean.py"]
```

The Python package discovers `lean.h` and `libleanshared` from the active
Lean toolchain at import time. You need a working
[elan](https://github.com/leanprover/elan) install (`lean` on PATH).

### Lean side

Add to your `lakefile.toml`:

```toml
[[require]]
name = "LeanPy"
git  = "https://github.com/kiranandcode/lean.py"

[[lean_lib]]
name = "MyLib"
# These three lines are required:
moreLinkObjs = [
  "LeanPy/LeanPy:static",
  "LeanPy/leanPyNative:static",
  "Pantograph/Pantograph:static",
]
precompileModules = true
defaultFacets = ["shared"]
# macOS only — allows install_name_tool to rewrite @rpath references:
moreLinkArgs = ["-Wl,-headerpad_max_install_names"]
```

> **Why three static libs?** `LeanPy:static` is the Lean module,
> `leanPyNative:static` is the C bridge (`python_bridge.c`), and
> `Pantograph:static` is the proof-assistant kernel that `LeanPy.Kernel`
> depends on. All three must be linked into the shared library that
> Python loads.

Then build:

```bash
lake build           # fetches LeanPy + Pantograph, compiles everything
```

## Using additional Lake dependencies

If your project depends on other Lean libraries (Batteries, Mathlib,
your own packages, etc.), add them as normal `[[require]]` entries in
your `lakefile.toml`. Any library whose symbols are called at runtime
through the Python-loaded `.so`/`.dylib` must also appear in
`moreLinkObjs`:

```toml
[[require]]
name = "LeanPy"
git  = "https://github.com/kiranandcode/lean.py"

[[require]]
name = "batteries"
git  = "https://github.com/leanprover-community/batteries"
rev  = "main"

[[lean_lib]]
name = "MyLib"
moreLinkObjs = [
  "LeanPy/LeanPy:static",
  "LeanPy/leanPyNative:static",
  "Pantograph/Pantograph:static",
  # Add any additional deps whose symbols you call at runtime:
  "batteries/Batteries:static",
]
precompileModules = true
defaultFacets = ["shared"]
moreLinkArgs = ["-Wl,-headerpad_max_install_names"]
```

**Rule of thumb:** if `lake build` succeeds but Python fails with
`symbol not found`, add the missing package to `moreLinkObjs` as
`"<package>/<LibName>:static"`. The pattern is always
`"<lake-package-name>/<lean_lib-name>:static"`.

If you only `import` a library at compile time (e.g. for notation or
macros) but don't call its functions at runtime, you don't need it in
`moreLinkObjs`.

## Quick start

### 1. Write Lean code

```lean
-- MyLib.lean
import LeanPy
open LeanPy

@[python "add"]
def add (a b : Int) : Int := a + b

structure Point where
  x : Int
  y : Int

derive_python Point

@[python "origin"]
def origin (_ : Unit) : Point := { x := 0, y := 0 }

#export_python_registry "MyLib"   -- makes the registry visible to Python
```

### 2. Call from Python

```python
from lean_py import LeanLibrary

lib = LeanLibrary.from_lake("path/to/lake/project", "MyLib", build=True)

lib.add(3, 4)          # 7
lib.origin(None)       # Point.mk(0, 0)
lib.Point(10, 20)      # Point.mk(10, 20) — constructed in Python
```

`from_lake` finds the `.lake/build/lib/lib<Name>.{dylib,so}` produced by
`lake build`. Pass `build=True` to run `lake build` automatically.

## Calling Python from Lean

```lean
open LeanPy.Python in
@[python "numpy_dot"]
def numpyDot (xs ys : Array Int) : IO Int := do
  init ()                         -- dlopens libpython once
  let np ← import_ "numpy"
  let dot ← np.getAttr "dot"
  let a ← Py.ofList (xs.toList.map Py.ofInt)
  let b ← Py.ofList (ys.toList.map Py.ofInt)
  (← dot.call #[← a, ← b]).toInt
```

```python
lib.numpy_dot([1, 2, 3], [4, 5, 6])   # 32
```

## Kernel facade (Pantograph)

Drive Lean's type-checker and tactic engine from Python:

```python
from lean_py import LeanLibrary
from lean_py.kernel import Kernel

lib = LeanLibrary.from_lake("path/to/project", "MyLib", build=True)
k = Kernel(lib)
k.load(["Init"])

# Create a goal and run tactics
state = k.goal_create("∀ n : Nat, n + 0 = n")
print(state.pretty())             # ⊢ ∀ (n : Nat), n + 0 = n

result = state.try_tactic("intro n")
print(result.state.pretty())      # n : Nat\n⊢ n + 0 = n

result2 = result.state.try_tactic("simp")
print(result2.state.is_solved())  # True
```

The kernel API also exposes environment introspection (`catalog`,
`decl_type`, `module_of`, ...), expression elaboration (`infer_type`,
`pretty_print`, `whnf`), frontend processing, and goal-state pickling.
See `lean_py/kernel.py` for the full surface.

## Bidirectional introspection

Lean's kernel ADTs (`Lean.Expr`, `Lean.Name`, `Lean.Level`,
`Lean.Syntax`, ...) are exposed as Python values via `derive_python`
(registered in `LeanPy/Reflect.lean`):

```python
Name = lib.Name
Expr = lib.Expr

# Build a Lean.Expr tree in Python
nat  = Name.str(Name.anonymous, "Nat")
succ = Expr.const(Name.str(nat, "succ"), [])
zero = Expr.const(Name.str(nat, "zero"), [])
e    = Expr.app(succ, zero)       # Nat.succ Nat.zero

# Pass it to any @[python] function expecting Lean.Expr
lib.describe_expr(e)
```

Going the other way, `Py` values returned from Lean land as live Python
objects:

```python
lib.makeList123(None)   # [1, 2, 3]  (not an opaque handle)
```

## Exceptions

Errors carry type information across the boundary:

```python
from lean_py import LeanError, LeanPyCallbackError

try:
    lib.some_io_function()
except LeanPyCallbackError as e:    # Python error inside a Lean callback
    print(e.python_type, e.python_message)
except LeanError as e:              # Lean IO error
    print(e.kind, e.message)
```

## Examples

```
examples/
  01_basic/             tiny end-to-end demo
  02_pantograph_kernel/ Pantograph-style kernel facade
  03_numpy_typed/       numpy with Lean-checked dependent shapes
  04_sympy_tactic/      `by sympy` — Lean tactic backed by SymPy via Expr trees
  05_knuckledragger/    `by knuckle` — Lean tactic backed by Z3 via Expr trees
```

Each is a self-contained Lake + uv project.

## Tests

```bash
uv sync --dev
lake build
cd tests/lean && lake build TestLib:shared && cd ../..
uv run pytest tests -v
```

125 tests covering: FFI primitives, all marshalled types, typed
exceptions, bidirectional introspection, kernel facade (goal state,
tactics, environment, elaboration, frontend, serialisation), Python-in-Lean
demos, and refcount stress tests.

## How it works

1. `@[python "name"]` sets `@[export]` and registers metadata (parameter
   types, return type) in a persistent env extension.
2. `derive_python TypeName` walks an inductive's constructors and adds
   them to the same registry.
3. `#export_python_registry "Prefix"` serialises the registry to JSON and
   emits two `@[export]`'d C functions returning that JSON.
4. On the Python side, `LeanLibrary` dlopens the `.dylib`/`.so`, calls
   `Prefix_funcs_json()` / `Prefix_types_json()`, builds `TypeWrapper`s,
   and exposes one Python callable per registered function.
5. The C bridge (`LeanPy/native/python_bridge.c`) implements the
   Python-in-Lean direction: a `lean_external_class` over `PyObject*`
   plus `lean_py_*` externs.

## Repository layout

```
LeanPy.lean              root import
LeanPy/
  Attr.lean              @[python] attribute, derive_python
  Export.lean            #export_python_registry
  Python.lean            Py type + @[extern] bridge
  Reflect.lean           derive_python for Lean.Expr/Name/Level/...
  Kernel.lean            Pantograph kernel API
  Kernel/                Frontend, Compat, ...
  native/python_bridge.c C bridge (dlopen, no Python.h)

lean_py/
  __init__.py            public API
  library.py             LeanLibrary loader
  marshal.py             Lean <-> Python marshalling
  kernel.py              Kernel / GoalState / TacticResult
  registry.py            TypeRepr / FuncInfo mirrors
  _runtime.py            dynamic ctypes FFI from lean.h
  _parse.py              lean.h parser (pycparser)
  utils.py               toolchain helpers

examples/                self-contained demos
tests/                   125-test suite
```

## License

Apache 2.0. See [LICENSE](LICENSE).
