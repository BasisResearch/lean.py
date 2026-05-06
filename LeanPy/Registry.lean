/-
The persistent environment extension that tracks all `@[python]`-annotated
declarations and `derive_python`-derived types.

Stored separately for functions and types so the Python side can iterate them
independently. Both extensions are imported across modules so a Python
binding `import`ed from a downstream library will still see all bindings
defined upstream.
-/
import Lean
import LeanPy.TypeRepr

open Lean

namespace LeanPy

/-- Persistent registry of all functions exposed via `@[python]`. -/
initialize funcRegistry :
    SimplePersistentEnvExtension FuncInfo (List FuncInfo) ←
  registerSimplePersistentEnvExtension {
    name          := `LeanPy.funcRegistry
    addEntryFn    := fun arr f => f :: arr
    addImportedFn := fun arrs   => arrs.toList.flatMap (·.toList)
    toArrayFn     := fun arr    => arr.toArray
  }

/-- Persistent registry of all types exposed via `derive_python`. -/
initialize typeRegistry :
    SimplePersistentEnvExtension TypeInfo (List TypeInfo) ←
  registerSimplePersistentEnvExtension {
    name          := `LeanPy.typeRegistry
    addEntryFn    := fun arr t => t :: arr
    addImportedFn := fun arrs   => arrs.toList.flatMap (·.toList)
    toArrayFn     := fun arr    => arr.toArray
  }

namespace Registry

/-- All `@[python]`-annotated functions known in the current environment. -/
def funcs (env : Environment) : Array FuncInfo :=
  (funcRegistry.getState env).toArray.reverse

/-- All `derive_python`-derived types known in the current environment. -/
def types (env : Environment) : Array TypeInfo :=
  (typeRegistry.getState env).toArray.reverse

/-- Look up a registered function by its export name. -/
def findFunc? (env : Environment) (exportName : String) : Option FuncInfo :=
  (funcs env).find? (·.exportName == exportName)

/-- Look up a registered type by its declaration name. -/
def findType? (env : Environment) (declName : Name) : Option TypeInfo :=
  (types env).find? (·.name == declName)

/-- Add a function entry to the registry. -/
def addFunc (env : Environment) (f : FuncInfo) : Environment :=
  funcRegistry.addEntry env f

/-- Add a type entry to the registry. -/
def addType (env : Environment) (t : TypeInfo) : Environment :=
  typeRegistry.addEntry env t

end Registry

end LeanPy
