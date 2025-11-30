-- This module serves as the root of the `Lean.Py` library.
-- Import modules here that should be built as part of the library.
import Lean.Elab
import Std.Data.HashMap

open Lean Meta Elab

syntax (name := pythonAttr) "python" str : attr
initialize pythonBindsRegistry :
  SimplePersistentEnvExtension (Name × String) (List (Name × String)) ←
  registerSimplePersistentEnvExtension {
    name := `pythonRegistryExt
    addEntryFn := (·.cons)
    addImportedFn := fun arr => arr.toList.flatMap (·.toList)
    toArrayFn := fun es => es.toArray
  }

initialize registerBuiltinAttribute {
   name := `pythonAttr
   descr := "Marks a Lean function to be exposed to Python."
   add := fun declName stx kind => do
      match stx with
      | `(attr| python $ext_name:str) =>
          let env <- getEnv
          let .some decl := env.find? declName
             | throwError s!"[python] could not find decl {declName}"
          let ext_name := ext_name.getString
          -- @[export "name"]
          modifyEnv fun env =>
            exportAttr.setParam env declName (.anonymous |>.str ext_name)
            |>.toOption.getD env
          -- register
          modifyEnv fun env =>
             pythonBindsRegistry.addEntry env (declName, ext_name)
      | _ =>
         throwErrorAt stx s!"unexpected syntax for python attribute"
}

