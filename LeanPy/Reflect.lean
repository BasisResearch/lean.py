/-
LeanPy.Reflect: register Lean's kernel-level inductives (`Name`, `Level`,
`Expr`, `Syntax`, …) with `derive_python`, so Python sees them as
fully-typed ADTs.

After importing this module, downstream Lean code that says

    @[python "py_my_op"]
    def myOp (e : Lean.Expr) : IO String := ...

emits a `@[python]` registration whose parameter type is `.named
Lean.Expr`. The Python side, after loading the library, gets a
`lib.Expr` namespace with constructors `app`, `lam`, `forallE`, …
matching the Lean ADT.

The set of registered types follows pantograph's serialisation surface
plus what's needed for the bidirectional introspection use case:

  - `Lean.Name`      — 3 ctors
  - `Lean.Level`     — 6 ctors
  - `Lean.BinderInfo` — 4-ctor enum
  - `Lean.Literal`   — 2 ctors
  - `Lean.MVarId`, `Lean.FVarId`, `Lean.LMVarId`
                     — single-ctor structures around `Name`
  - `Lean.Expr`      — 11 ctors
  - `Lean.Syntax`    — 4 ctors

`Lean.SourceInfo`, `Substring`, and `KVMap` (the cargo of `mdata`)
ride along as `.opaque` because they're not interesting structurally
to a Python caller. Future work could expand them.
-/
import LeanPy.Registry
import LeanPy.TypeRepr
import LeanPy.Attr
import LeanPy.Python

open Lean

namespace LeanPy.Reflect

/-! ## Kernel ADT registrations -/

derive_python Lean.Name
derive_python Lean.BinderInfo
derive_python Lean.Literal
derive_python Lean.Level
derive_python Lean.MVarId
derive_python Lean.FVarId
derive_python Lean.LevelMVarId
derive_python Lean.Expr
derive_python Lean.SourceInfo
derive_python Lean.Syntax

end LeanPy.Reflect

/-! ## Transport-layer convenience wrappers

These wrap specific kernel types as `Py` handles via `Py.ofLeanObj`.
They make it straightforward to pass Lean kernel objects to Python
callbacks through the `Py.call` bridge. -/

namespace LeanPy.Python.Py

open Lean LeanPy.Python

def ofExpr  (e : Expr)  : IO Py := ofLeanObj e
def ofName  (n : Name)  : IO Py := ofLeanObj n
def ofLevel (l : Level) : IO Py := ofLeanObj l

end LeanPy.Python.Py
