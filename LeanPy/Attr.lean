/-
The `@[python "<name>"]` attribute and the `derive_python` command.

`@[python "py_foo"]` does three things:
  1. Sets `@[export "py_foo"]` so the C symbol is emitted.
  2. Reads the declaration's type, walks parameters, and converts each
     parameter and result type into a `TypeRepr` value.
  3. Adds a `FuncInfo` entry to the persistent registry.

`derive_python TypeName` walks an inductive declaration and adds a
`TypeInfo` entry to the persistent registry. No accessor functions
are generated — the Python side decodes the constructor tag and
field offsets directly via the C ABI.
-/
import Lean
import LeanPy.Registry
import LeanPy.TypeRepr

open Lean Meta Elab Command

namespace LeanPy

/-- Convert a Lean type expression into a `TypeRepr`.

Recognises a fixed set of well-known types and falls through to
`.named` (for registered user types) or `.opaque` (for anything else).
The walk is purely structural and does not unfold definitions. -/
partial def typeToRepr (env : Environment) (e : Expr) : TypeRepr :=
  let e := e.headBeta.cleanupAnnotations
  match e with
  | .const n _ =>
    match n with
    | ``Nat       => .nat
    | ``Int       => .int
    | ``Bool      => .bool
    | ``String    => .string
    | ``Float     => .float
    | ``Float32   => .float32
    | ``Char      => .char
    | ``Unit      => .unit
    | ``PUnit     => .unit
    | ``UInt8     => .uint 8
    | ``UInt16    => .uint 16
    | ``UInt32    => .uint 32
    | ``UInt64    => .uint 64
    | ``USize     => .uint 64
    | ``Int8      => .sint 8
    | ``Int16     => .sint 16
    | ``Int32     => .sint 32
    | ``Int64     => .sint 64
    | `LeanPy.Python.Py => .pyobject
    | _ =>
      if (Registry.findType? env n).isSome then .named n
      else .opaque n
  | .app .. =>
    let fn   := e.getAppFn
    let args := e.getAppArgs
    match fn with
    | .const n _ =>
      match n with
      | ``Array  => if h : args.size > 0 then .array  (typeToRepr env args[0]) else .opaque n
      | ``List   => if h : args.size > 0 then .list   (typeToRepr env args[0]) else .opaque n
      | ``Option => if h : args.size > 0 then .option (typeToRepr env args[0]) else .opaque n
      | ``Prod   => if h : args.size > 1 then .prod   (typeToRepr env args[0]) (typeToRepr env args[1]) else .opaque n
      | ``Sum    => if h : args.size > 1 then .sum    (typeToRepr env args[0]) (typeToRepr env args[1]) else .opaque n
      | ``IO     => if h : args.size > 0 then .io     (typeToRepr env args[0]) else .opaque n
      | ``EIO    => if h : args.size > 1 then .except (typeToRepr env args[0]) (typeToRepr env args[1]) else .opaque n
      | ``Except => if h : args.size > 1 then .except (typeToRepr env args[0]) (typeToRepr env args[1]) else .opaque n
      | _ =>
        if (Registry.findType? env n).isSome then .named n
        else .opaque n
    | _ => .opaque .anonymous
  | _ => .opaque .anonymous

/-- Walk a function type, yielding `(paramTypes, returnType)`. Drops type-class
parameters and instance arguments (these are not transmitted to Python). -/
partial def collectFunSig (env : Environment) (type : Expr) : Array TypeRepr × TypeRepr :=
  let rec go (params : Array TypeRepr) : Expr → Array TypeRepr × TypeRepr
    | .forallE _ d b _ =>
      -- Skip instance / type-class style binders heuristically: arrow into
      -- something that returns a type, treat as opaque param to keep arity.
      let dRepr := typeToRepr env d
      go (params.push dRepr) b
    | t => (params, typeToRepr env t)
  go #[] type

/-- The underlying registration logic, shared by the attribute and the
`derive_python` command. Marked `setExportName := false` to skip rewiring
the `export` attribute when only adding metadata. -/
def doRegisterPython
    (declName : Name) (extName : String) (setExportName : Bool := true) :
    AttrM Unit := do
  let env ← getEnv
  let some info := env.find? declName
    | throwError s!"[python] could not find decl {declName}"
  let (params, ret) := collectFunSig env info.type
  let funcInfo : FuncInfo := {
    declName, exportName := extName, params, returnType := ret
  }
  if setExportName then
    modifyEnv fun env =>
      exportAttr.setParam env declName (.anonymous |>.str extName)
        |>.toOption.getD env
  modifyEnv (Registry.addFunc · funcInfo)

/-- The `@[python "name"]` attribute. Equivalent to `@[export "name"]`
plus an entry in the persistent function registry. -/
syntax (name := pythonAttr) "python" str : attr

initialize registerBuiltinAttribute {
  name        := `pythonAttr
  descr       := "Marks a Lean function to be exposed to Python."
  applicationTime := AttributeApplicationTime.afterCompilation
  add         := fun declName stx _kind => do
    match stx with
    | `(attr| python $extName:str) =>
        doRegisterPython declName extName.getString
    | _ =>
        throwErrorAt stx "unexpected syntax for @[python]"
}

/-! ### `derive_python` command

`derive_python TypeName` reads the declaration of `TypeName` from the
environment, builds a `TypeInfo`, and stores it in the type registry. No
new declarations are generated — the Python side uses the type info
directly to read constructors / fields out of the runtime object.
-/

/-- Build a `TypeInfo` for a Lean inductive type. -/
def buildTypeInfo (env : Environment) (n : Name) : MetaM TypeInfo := do
  let some (.inductInfo iinfo) := env.find? n
    | throwError s!"derive_python: {n} is not an inductive type"
  let isStructure := isStructure env n
  let mut ctors  : Array CtorInfo := #[]
  let mut isEnum := true
  for (cname, idx) in iinfo.ctors.zipIdx do
    let some (.ctorInfo ci) := env.find? cname
      | throwError s!"derive_python: cannot find constructor {cname}"
    -- Walk the constructor type, dropping the inductive's parameters
    -- and treating remaining `forallE` binders as fields.
    let ctorType := ci.type
    -- Skip the leading parameters of the inductive.
    let rec skipParams : Nat → Expr → Expr
      | 0,   e                  => e
      | n+1, .forallE _ _ b _   => skipParams n b
      | _+1, e                  => e
    let body := skipParams iinfo.numParams ctorType
    let mut fields : Array TypeRepr := #[]
    let mut t := body
    while t.isForall do
      let .forallE _ dom rest _ := t | break
      fields := fields.push (typeToRepr env dom)
      t := rest
    if !fields.isEmpty then isEnum := false
    let cname' := cname.componentsRev.head?.map toString |>.getD (toString cname)
    ctors := ctors.push { name := cname', tag := idx, fields }
  return { name := n, isStructure, isEnum, ctors }

/-- Add a type to the registry. To allow recursive `derive_python` (where
a type references itself in one of its constructors), we first register
a *placeholder* `TypeInfo` containing only the name; this lets the
`typeToRepr` lookup classify recursive uses as `.named` rather than
`.opaque`. We then run `buildTypeInfo` against the now-extended
environment and overwrite the placeholder with the full info. -/
def doRegisterType (n : Name) : CommandElabM Unit := do
  let env ← getEnv
  if let some existing := Registry.findType? env n then
    -- An entry already exists. If it's a placeholder (no ctors), we
    -- still need to compute the real one and add it; otherwise return.
    if !existing.ctors.isEmpty then return ()
  else
    -- 1. Register a name-only placeholder so recursive lookups succeed.
    let placeholder : TypeInfo := { name := n }
    modifyEnv (Registry.addType · placeholder)
  -- 2. Now compute the real `TypeInfo` against the extended env.
  let info ← liftTermElabM <| Lean.Meta.MetaM.run' (buildTypeInfo (← getEnv) n)
  -- 3. Overwrite the placeholder with the real info.
  modifyEnv (Registry.addType · info)

/-- The `derive_python` command. -/
syntax (name := derivePython) "derive_python" ident,+ : command

@[command_elab derivePython]
def elabDerivePython : Command.CommandElab := fun stx =>
  match stx with
  | `(derive_python $names,*) => do
      for n in names.getElems do
        let resolved ← liftCoreM <| Lean.realizeGlobalConstNoOverloadCore n.getId
        doRegisterType resolved
  | _ => throwUnsupportedSyntax

/-- Convenience: register a type (used internally and by user code). -/
def deriveType (n : Name) : CommandElabM Unit := doRegisterType n

end LeanPy
