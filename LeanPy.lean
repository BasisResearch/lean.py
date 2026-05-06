/-
LeanPy: effortless Python ↔ Lean bindings.

This top-level module re-exports the public surface of the library:
* `LeanPy.Registry`     — persistent registry of types/functions exposed to Python
* `LeanPy.TypeRepr`     — Lean-side description of types (passed to Python as JSON)
* `LeanPy.Attr`         — the `@[python]` attribute and `derive_python` command
* `LeanPy.Export`       — runtime export of the registry (queried by Python at startup)
* `LeanPy.Python`       — Python-in-Lean: opaque `Py` external class + monadic operations
-/
import LeanPy.Registry
import LeanPy.TypeRepr
import LeanPy.Attr
import LeanPy.Export
import LeanPy.Python
import LeanPy.Kernel
