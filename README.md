# lean-py

Effortless interop between **Lean 4** and **Python**, in both directions.

* **Lean → Python.** Annotate any Lean definition with `@[python "name"]`
  and it becomes callable from Python with the right marshalled types.
  `derive_python` exposes inductives / structures as Python wrapper
  classes whose constructors round-trip through the C ABI.
* **Python → Lean.** A built-in `LeanPy.Python` namespace gives Lean
  code an opaque `Py` external object plus the usual operations
  (`import_`, `eval`, `exec`, `getAttr`, `call`, …). CPython is loaded
  lazily via `dlopen`.
* **Pantograph-style kernel facade.** `LeanPy.Kernel` exposes
  `loadEnv`, `inferType`, `prettyPrint`, `whnf`, etc. so a host Python
  process can drive Lean's elaborator without spawning a subprocess.

## Quick example

```lean
-- examples/lean/PyleanExample.lean
import LeanPy
open LeanPy

@[python "py_bar"]
def bar (x : Int) : Int := x + 1

structure Point where
  x : Int
  y : Int

derive_python Point

@[python "py_origin"]
def origin (_ : Unit) : Point := ⟨0, 0⟩

#export_python_registry "PyleanExample"
```

```python
# Python side
from lean_py import LeanLibrary

lib = LeanLibrary("examples/lean/.lake/build/lib/libPyleanExample.dylib",
                  "PyleanExample")
print(lib.bar(7))                       # → 8
print(lib.Point(3, 4))                  # → Point.mk(3, 4)
print(lib.origin(None))                 # → Point.mk(0, 0)
```

## Python in Lean (sympy / numpy demo)

```lean
open LeanPy.Python in
@[python "py_sympy_simplify"]
def sympySimplify (expr : String) : IO String := do
  init ()                       -- lazy: dlopens libpython once
  let sympy ← import_ "sympy"
  let f     ← getAttr sympy "simplify"
  let e     ← ofString expr
  str (← call f #[e])
```

```python
print(lib.sympySimplify("(x**2 - 1)/(x - 1)"))   # "x + 1"
```

## How it works

1. The `@[python "name"]` attribute (`LeanPy/Attr.lean`) sets `@[export]`
   and registers metadata (declaration name, parameter `TypeRepr`s, return
   type) in a `SimplePersistentEnvExtension`.
2. `derive_python TypeName` walks an inductive's constructors and adds
   them to the same registry — no new Lean declarations are emitted.
3. `#export_python_registry "<prefix>"` (`LeanPy/Export.lean`) reads the
   compile-time registry, JSON-serialises it, and emits two
   `@[export]`'d functions returning that JSON to Python.
4. On the Python side, `LeanLibrary("foo.dylib", "Foo")` dlopens the
   library, calls `Foo_funcs_json()` / `Foo_types_json()`, builds
   `TypeWrapper`s for each registered type, and exposes one Python
   callable per registered Lean function.
5. The C bridge (`LeanPy/native/python_bridge.c`) implements the
   Python-in-Lean direction: a `lean_external_class` over `PyObject*`
   plus `lean_py_*` externs that the Lean side calls.

## Tests

```bash
uv sync --dev
lake build
(cd examples/lean && lake build)
uv run pytest tests -v
```

There are 37 tests covering FFI primitives, all marshalled types, the
kernel facade, sympy / numpy demos through Lean, and refcount stress.
For a heavier memory check (`leaks` on macOS, `valgrind` on Linux):

```bash
tests/leaks_check.sh
```

## CI

`.github/workflows/ci.yml` runs the suite on `ubuntu-latest` and
`macos-latest` against three Lean toolchains (the pinned default plus a
prior stable and `nightly`), and runs separate `leaks` (macOS) and
`valgrind` (Linux) jobs.

## Repository layout

```
LeanPy.lean              # entry point importing all modules
LeanPy/
  Registry.lean          # persistent env extensions (funcs + types)
  TypeRepr.lean          # JSON-serializable structural type model
  Attr.lean              # @[python] attribute, derive_python command
  Export.lean            # #export_python_registry command
  Python.lean            # @[extern] declarations for the Py bridge
  Kernel.lean            # Pantograph-equivalent kernel API
  native/python_bridge.c # C side of the Python bridge

lean_py/
  __init__.py            # public Python API
  _parse.py              # parses lean.h with pycparser
  _runtime.py            # dynamic ctypes FFI built from lean.h
  marshal.py             # Lean ↔ Python value marshalling
  registry.py            # Python mirror of TypeRepr / FuncInfo
  library.py             # LeanLibrary loader + wrapper generation
  utils.py               # toolchain / lib path helpers

examples/lean/           # PyleanExample: tiny demo Lean library
tests/                   # 37-test suite (FFI / marshal / kernel / Python-in-Lean / sympy / numpy / memory)
```
