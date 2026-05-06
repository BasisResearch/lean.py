/-
Runtime export of the registry.

A user library should put

    #export_python_registry "<prefix>"

at the end of one Lean module. This emits two `@[export]`'d functions:

    <prefix>_funcs_json : Unit → String
    <prefix>_types_json : Unit → String

returning the (compile-time) JSON serialization of the persistent
registry of functions and types known at the point of the command.

The Python loader calls these symbols, parses the JSON, and uses the
result to generate Python wrappers for the registered Lean declarations.

By convention `<prefix>` is the same as the library name passed to
`LeanPy.Library(path, name)` on the Python side.
-/
import Lean
import LeanPy.Registry

open Lean Elab Command

namespace LeanPy

syntax (name := exportPyRegistry) "#export_python_registry" str : command

/-- Set the `@[export]` attribute on a declaration to a chosen C symbol name. -/
private def setExport (declName : Name) (cSymbol : String) : CommandElabM Unit := do
  let cName : Name := .anonymous |>.str cSymbol
  modifyEnv fun env =>
    exportAttr.setParam env declName cName |>.toOption.getD env

@[command_elab exportPyRegistry]
def elabExportPyRegistry : CommandElab := fun stx => do
  match stx with
  | `(#export_python_registry $pfxStx:str) => do
    let env ← getEnv
    let funcsJson := (Json.arr ((Registry.funcs env).map (·.toJson))).compress
    let typesJson := (Json.arr ((Registry.types env).map (·.toJson))).compress
    let pfx := pfxStx.getString
    let funcsName  := Name.mkSimple s!"_leanpy_{pfx}_funcs_json"
    let typesName  := Name.mkSimple s!"_leanpy_{pfx}_types_json"
    let funcsId    := mkIdent funcsName
    let typesId    := mkIdent typesName
    let funcsLit   := Syntax.mkStrLit funcsJson
    let typesLit   := Syntax.mkStrLit typesJson
    elabCommand (← `(def $funcsId:ident (_ : Unit) : String := $funcsLit:str))
    elabCommand (← `(def $typesId:ident (_ : Unit) : String := $typesLit:str))
    -- The names get scoped to the current namespace (`LeanPy.<id>` here).
    -- Resolve via the just-elaborated env.
    let env' ← getEnv
    let resolveOne (sn : Name) : CommandElabM Name := do
      match env'.find? sn with
      | some _ => return sn
      | none =>
        let ns ← getCurrNamespace
        return ns ++ sn
    let funcsResolved ← resolveOne funcsName
    let typesResolved ← resolveOne typesName
    setExport funcsResolved s!"{pfx}_funcs_json"
    setExport typesResolved s!"{pfx}_types_json"
  | _ => throwUnsupportedSyntax

end LeanPy
