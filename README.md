# lean-py

Effortless interop between **Lean 4** and **Python**, in both directions.

This branch targets Lean 4.35.0. Before each Lake project's first build, run
`python3 scripts/prepare_lean435.py /path/to/project` from this checkout.
It applies a checked proof-only workaround to the pinned Regex dependency;
plain `lake build` currently fails without it. See the
[kernel bridge example](examples/kernel/README.md) for importing an existing
Mathlib project's compiled proofs from Python.

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
uv pip install "lean_py @ git+https://github.com/BasisResearch/lean.py"
```

or in `pyproject.toml`:

```toml
[project]
dependencies = ["lean_py @ git+https://github.com/BasisResearch/lean.py"]
```

The Python package discovers `lean.h` and `libleanshared` from the active
Lean toolchain at import time. You need a working
[elan](https://github.com/leanprover/elan) install (`lean` on PATH).

### Lean side

Add to your `lakefile.toml`:

```toml
[[require]]
name = "LeanPy"
git  = "https://github.com/BasisResearch/lean.py"

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
git  = "https://github.com/BasisResearch/lean.py"

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

## z3py-compatible prover

Lean's `grind` tactic is a powerful automated reasoning engine — congruence
closure, arithmetic, and more — but calling it means setting up a Lake
project, marshalling goal strings, and threading tactic results. `lean_py.z3`
wraps all of that behind a z3py-compatible API so you can write propositions
in Python and prove them with one call.

```python
from lean_py.z3 import *

x, y = Ints('x y')
prove(Implies(And(x > 0, y > 0), x + y > 0))   # prints "proved"
```

Expressions build up Lean syntax under the hood. Operator overloading on
`ArithRef` (`+`, `-`, `*`, `<`, `<=`, ...) and `BoolRef` (`&`, `|`, `~`)
works exactly like z3py. Free variables are tracked automatically and bound
as `∀` quantifiers at proof time.

```python
# Solver interface — same as z3py
s = Solver()
s.add(x > 0, x < 0)
s.check()              # unsat (negation proved via grind)

# Quantifiers, uninterpreted sorts, functions
Entity = DeclareSort('Entity')
Man = Function('Man', Entity, BoolSort())
Mortal = Function('Mortal', Entity, BoolSort())
socrates = Const('socrates', Entity)
e = Const('e', Entity)

prove(Implies(
    And(ForAll([e], Implies(Man(e), Mortal(e))),
        Man(socrates)),
    Mortal(socrates),
))                     # proved
```

The solver tries tactics in order: `grind`, `omega`, `decide`, `simp_all`.
Because Lean is a proof checker and not an SMT solver, `check()` returns
`unsat` (negation proved) or `unknown` — never `sat`. Model extraction is
not supported.

### Setup

The z3 layer needs a `Kernel` to talk to Lean. Two options:

**Manual** — point at an existing Lake project (the kernel facade you
already know):

```python
from lean_py import LeanLibrary
from lean_py.kernel import Kernel
from lean_py.z3 import *

lib = LeanLibrary.from_lake("path/to/project", "MyLib", build=True)
k = Kernel(lib)
k.init_search("")
k.load(["Init"])
set_kernel(k)

prove(Int('x') + 0 == Int('x'))
```

**Zero-config** — `ManagedProject` creates and caches a Lake project
under `~/.lean_py/managed/` so you never touch a lakefile:

```python
from lean_py.project import ManagedProject
from lean_py.z3 import *

mp = ManagedProject.get(deps=("batteries",))  # fetches + builds once
set_kernel(mp.kernel())

x = Int('x')
prove(Implies(x > 0, x + 1 > 0))
```

`ManagedProject` pins dependencies to your active Lean toolchain version
(e.g. `batteries@v4.29.1` for `leanprover/lean4:v4.29.1`). Supported
well-known packages: `batteries`, `mathlib`, `aesop`, `proofwidgets`.
Pass any other name and it will be added as a bare `[[require]]` entry —
you'll need to specify the git source yourself. For example, to use a
custom package `MyMathUtils`:

```python
mp = ManagedProject.get(deps=("batteries", "MyMathUtils"))
```

This generates a `lakefile.toml` with:

```toml
[[require]]
name = "batteries"
git  = "https://github.com/leanprover-community/batteries"
rev  = "v4.29.1"

[[require]]
name = "MyMathUtils"
```

You'd then edit `~/.lean_py/managed/<hash>/lakefile.toml` to add the
git source for `MyMathUtils` before the first build:

```toml
[[require]]
name = "MyMathUtils"
git  = "https://github.com/yourorg/my-math-utils"
rev  = "main"
```

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

## Type stubs

A `LeanLibrary` exposes its functions and types dynamically, so editors and
type-checkers see only `Any`. Generate a `.pyi` stub from the same registry
that drives marshalling — one source of truth for runtime conversion *and*
static types:

```bash
python -m lean_py.stubgen path/to/project MyLib -o MyLib.pyi
```

or at runtime:

```python
lib = LeanLibrary.from_lake("path/to/project", "MyLib", build=True)
lib.write_stub("MyLib.pyi")
```

The stub declares a `MyLibLibrary(LeanLibrary)` subclass with typed methods
(`def add(self, a0: int, a1: int, /) -> int: ...`) and one class per derived
type, including per-constructor classes for pattern matching. Annotate the
`from_lake` result to opt in:

```python
from MyLib import MyLibLibrary  # the generated stub
lib: MyLibLibrary = LeanLibrary.from_lake("path/to/project", "MyLib")  # type: ignore[assignment]
lib.add(3, 4)          # checked: (int, int) -> int
```

Parameter *names* are not in the registry yet, so parameters are positional
(`a0, a1, ...`), matching the runtime wrappers, which reject keyword arguments.

The stub annotations come from the same `TypeRepr` that drives marshalling, so
they can't drift from runtime behaviour. That representation also backs an
optional runtime check — one description, static hints and value validation
alike:

```python
from lean_py import set_argument_typechecking

set_argument_typechecking(True)
lib.add(3, "four")     # TypeError: add arg 1: expected `Int` (int), got str 'four'
```

It is off by default (the marshaller is deliberately lenient); enable it while
developing for clearer errors before values cross the FFI boundary.

## Distribution: self-contained wheels

By default a `LeanLibrary` discovers the Lean runtime from the active toolchain
(`lean --print-prefix`), so every user needs elan installed. To ship a library
that installs with **no toolchain**, bundle the dylib together with its Lean
runtime dependency closure into a wheel:

```bash
python -m lean_py.packaging build path/to/project MyLib --version 0.1.0 -o dist/
```

The bundler vendors the dylib, the Lean runtime shared libraries, and `lean.h`
into the wheel, and rewrites their install names / RPATHs so they resolve each
other via `@loader_path` (macOS) or `$ORIGIN` (Linux). The wheel ships a loader:

```python
from mylib import load          # the bundled package
lib = load()                    # a ready LeanLibrary, no elan required
lib.myFunction(42)
```

Because lean.py binds through **ctypes** rather than a CPython C-extension, the
wheel is ABI-independent and tagged `py3-none-<platform>` — the only
platform-specific content is the vendored dylibs. (This is the analogue of
nerodia's `abi3` wheels; lean.py needs no Python-ABI tag at all.) Bundling
requires `install_name_tool`/`codesign` on macOS or `patchelf` on Linux.

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
  06_effectful_verifier/ side-effectful programs with verified pre/post specs
  07_z3py_drop_in/      z3py vocabulary backed by Lean's grind (no Z3 needed)
```

Each is a self-contained Lake + uv project.

## Tests

```bash
uv sync --dev
python3 scripts/prepare_lean435.py
lake build
python3 scripts/prepare_lean435.py tests/lean
cd tests/lean && lake build TestLib:shared && cd ../..
uv run pytest tests -v
```

1300+ tests across 17 files covering: FFI primitives, all marshalled
types, typed exceptions, bidirectional introspection, kernel facade (goal
state, tactics, environment, elaboration, frontend, serialisation),
Python-in-Lean demos, the z3py-compatible layer, and refcount stress tests.

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
  project.py             ManagedProject (zero-config Lake projects)
  z3/                    z3py-compatible prover (core AST + solver)

examples/                self-contained demos
tests/                   125-test suite
```

## License

Apache 2.0. See [LICENSE](LICENSE).
