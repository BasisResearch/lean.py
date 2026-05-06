# Exceptions in lean-py

Errors can be raised on either side of the bridge, and we want them to surface
on the *other* side without losing information about where they came from. This
document describes the typed exception model exposed in both directions.

## Two directions

| Origin   | Wrapped as                              | Caught as (other side)                          |
|----------|-----------------------------------------|-------------------------------------------------|
| Lean     | `IO.Error` ctor (e.g. `userError msg`)  | `lean_py.LeanError` (Python)                    |
| Python   | `IO.userError "TypeName: msg"`          | `lean_py.LeanPyCallbackError` (Python) **or** `LeanPy.Python.PyException` (Lean) |

## Lean → Python

Any `@[python]` function whose Lean signature is `IO α` either returns the
unwrapped value (Ok branch) or raises a Python exception (Error branch). The
wrapper at `lean_py/marshal.py` decodes the Lean `IO.Error` constructor and
raises `LeanError` carrying:

- `kind`: short tag (`"userError"`, `"fileNotFound"`, ...).
- `message`: human-readable description.
- `context`: optional dict of extra fields.

```python
from lean_py import LeanError

try:
    lib.some_io_function()
except LeanError as e:
    print(e.kind)       # e.g. "userError"
    print(e.message)    # the Lean-side message
```

`LeanError` subclasses `RuntimeError`, so existing `except RuntimeError:` and
`except Exception:` clauses still catch it.

## Python → Lean → Python (callback failures)

When Lean code calls back into Python via `LeanPy.Python.eval`, `Py.call`,
`Py.getAttr`, etc., and the underlying CPython call raises, the C bridge
formats the exception as `"<TypeName>: <message>"` and produces an
`IO.userError`. On the way back to Python the wrapper recognises this shape
and re-raises as `LeanPyCallbackError`:

```python
from lean_py import LeanPyCallbackError

try:
    lib.run_python_eval("x = {}; x['missing']")  # @[python] fn calling eval
except LeanPyCallbackError as e:
    print(e.python_type)     # "KeyError"
    print(e.python_message)  # "'missing'"
```

`LeanPyCallbackError` inherits from `LeanError` (with `kind == "python"`), so a
single `except LeanError:` covers both flavours.

## Python → Lean (recovering inside Lean)

Sometimes the Lean side wants to *recover* from a Python failure rather than
let it propagate to Python. Use `LeanPy.Python.tryCatchPy`:

```lean
import LeanPy.Python
open LeanPy.Python

@[python "try_eval_or_default"]
def tryEvalOrDefault (src : String) (default : String) : IO String := do
  init ()
  tryCatchPy
    (do let r ← eval src; r.str)
    (fun (exc : PyException) => do
      IO.eprintln s!"caught Python {exc.typeName}: {exc.message}"
      return default)
```

`PyException` carries:

- `typeName : String` — name of the original Python exception class.
- `message : String` — `str(exc)` from the Python side.

Errors of non-Python origin also flow through `tryCatchPy`, with `typeName`
set to `"PythonError"` and the raw Lean message in `message`.

## Raising from Lean

A `@[python]` function can raise a typed error to Python with any of the
standard `IO` panics:

```lean
@[python "validate_input"]
def validateInput (n : Int) : IO Unit := do
  if n < 0 then
    throw (IO.userError s!"expected non-negative, got {n}")
```

On the Python side this surfaces as `LeanError(kind="userError", message="…")`.

## Raising from Python (caught in Lean)

Inside a callback, raising a Python exception works as usual. The bridge
unconditionally captures it; if Lean has wrapped the call in `tryCatchPy` it
catches there, otherwise the exception propagates back to the original Python
caller as `LeanPyCallbackError`.

## Reference table

| Class                                    | Python | Lean equivalent              | When raised                                  |
|------------------------------------------|--------|------------------------------|----------------------------------------------|
| `LeanError`                              | ✅     | any `IO.Error` ctor          | Lean function fails                          |
| `LeanPyCallbackError(LeanError)`         | ✅     | `IO.userError "T: msg"`      | CPython exception inside a Lean→Python call  |
| `LeanPy.Python.PyException` (struct)     | —      | parsed `tryCatchPy` arg      | matches the bridge's userError format        |

## Tests

`tests/test_exceptions.py` exercises every cell of the table above.
