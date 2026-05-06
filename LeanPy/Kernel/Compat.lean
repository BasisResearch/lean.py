/-
LeanPy.Kernel.Compat: Thin re-export / compatibility layer.

This file bridges `Pantograph` (the Lake dependency) into the
`LeanPy.Kernel` namespace and contains the handful of
LeanPy-specific helpers that have no upstream equivalent.
-/
import Pantograph

open Lean

namespace LeanPy.Kernel

/-! ## Re-exports from Pantograph

The core kernel types and operations are now provided by the
`Pantograph` Lake dependency. We re-export them under `LeanPy.Kernel`
so downstream code that opens the kernel namespace sees them
without a separate `open Pantograph`. -/

export Pantograph (
  GoalState TacticResult Site
  goalStatePickle goalStateUnpickle
  environmentPickle environmentUnpickle
)

/-! ## LeanPy-specific environment helpers

These utilities are not part of upstream Pantograph; they provide
name filtering and environment introspection for the Python-facing
`@[python]` wrappers in `LeanPy/Kernel.lean`. -/

@[always_inline]
def getAuxLemmaPrefix? (n : Name) : Option String :=
  match n with
  | .str _ s =>
    if "_proof_".isPrefixOf s then
      .some "_proof"
    else if "_simp_".isPrefixOf s then
      some "_simp"
    else
      none
  | _ => .none

@[always_inline]
def isAuxLemma (n : Name) : Bool :=
  getAuxLemmaPrefix? n |>.isSome

def isNameInternal (n : Name) : Bool :=
  isAuxLemma n ∨ n.hasMacroScopes

/-- Catalog all the non-internal and safe names -/
def envCatalog (env : Environment) : Array Name :=
  env.constants.fold (init := #[]) fun acc name _ =>
    match isNameInternal name with
    | false => acc.push name
    | true => acc

def module_of_name (env : Environment) (name : Name) : Option Name := do
  let moduleId ← env.getModuleIdxFor? name
  if h : moduleId.toNat < env.allImportedModuleNames.size then
    return env.allImportedModuleNames[moduleId.toNat]
  else
    .none

def toCompactSymbolName (n : Name) (info : ConstantInfo) : String :=
  let pref := match info with
  | .axiomInfo  _ => "a"
  | .defnInfo   _ => "d"
  | .thmInfo    _ => "t"
  | .opaqueInfo _ => "o"
  | .quotInfo   _ => "q"
  | .inductInfo _ => "i"
  | .ctorInfo   _ => "c"
  | .recInfo    _ => "r"
  s!"{pref}{toString n}"

def toFilteredSymbol (n : Name) (info : ConstantInfo) : Option String :=
  if isNameInternal n || info.isUnsafe
  then Option.none
  else Option.some <| toCompactSymbolName n info

abbrev ConstArray := Array (Name × ConstantInfo)
abbrev DistilledEnvironment := Array Import × ConstArray

def envDiff (src dst : Environment) : ConstArray :=
  dst.constants.map₂.foldl (init := #[]) fun acc name info =>
    if src.contains name then
      acc
    else
      acc.push (name, info)

/-- Boil an environment down to minimal components -/
def distilEnvironment (env : Environment) (background? : Option Environment := .none)
  : DistilledEnvironment :=
  let constants := match background? with
    | .some src => envDiff src env
    | .none => env.constants.map₂.toArray
  (env.header.imports, constants)

end LeanPy.Kernel
