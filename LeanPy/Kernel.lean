/-
LeanPy.Kernel: a small Pantograph-like façade exposing key Lean 4 kernel
operations to Python via `@[python]`. This is intentionally a thin
wrapper so downstream users can build on it.

The model: the host Python process owns a single Lean `Environment`
loaded by name (`load_env`). Subsequent operations run in a frozen
`CoreM` over that environment. Every entry point returns a `String`
(serialised result) or an integer/Bool.
-/
import Lean
import LeanPy.Registry
import LeanPy.Attr

open Lean Meta Elab

namespace LeanPy.Kernel

/-! ### Environment management -/

/-- A reference to the active environment used by all kernel operations. -/
initialize envRef : IO.Ref (Option Environment) ← IO.mkRef none

/-- Initialize Lean's search path to allow loading Mathlib / user libs.
Must be called once per process before `loadEnv`. -/
@[python "leanpy_kernel_init_search"]
def initSearch (sp : String) : IO Unit := do
  Lean.initSearchPath (← Lean.findSysroot) (sp := System.SearchPath.parse sp)

/-- Load (import) a list of modules into a fresh environment. -/
@[python "leanpy_kernel_load_env"]
unsafe def loadEnv (modules : Array String) : IO Unit := do
  Lean.enableInitializersExecution
  let imports : Array Import := modules.map (fun n => { module := n.toName })
  let env ← Lean.importModules imports {} (loadExts := true)
  envRef.set (some env)

/-- Whether an environment is currently loaded. -/
@[python "leanpy_kernel_is_loaded"]
def isLoaded (_ : Unit) : IO Bool := do
  return (← envRef.get).isSome

/-- Clear the active environment (frees memory). -/
@[python "leanpy_kernel_clear_env"]
def clearEnv (_ : Unit) : IO Unit :=
  envRef.set none

private def withEnv (k : Environment → IO String) : IO String := do
  match (← envRef.get) with
  | some env => k env
  | none => return ""

private def runCore (act : CoreM String) : IO String := do
  match (← envRef.get) with
  | some env =>
    let ctx : Core.Context := {
      fileName := "<lean_py.kernel>"
      fileMap  := default
    }
    let state : Core.State := { env }
    try
      let (r, _) ← (act.toIO ctx state)
      return r
    catch e =>
      return s!"<error: {e.toString}>"
  | none => return "<no environment loaded>"

/-! ### Declaration introspection -/

/-- Number of declarations in the active environment. -/
@[python "leanpy_kernel_decl_count"]
def declCount (_ : Unit) : IO Int := do
  match (← envRef.get) with
  | some env =>
    let r ← IO.mkRef 0
    env.constants.forM (fun _ _ => do r.modify (· + 1))
    let n ← r.get
    return n
  | none => return 0

/-- All known declaration names (sorted), as a single newline-separated string. -/
@[python "leanpy_kernel_all_decls"]
def allDecls (_ : Unit) : IO String := do
  match (← envRef.get) with
  | some env =>
    let r ← IO.mkRef (#[] : Array String)
    env.constants.forM (fun n _ => do r.modify (·.push (toString n)))
    let acc ← r.get
    return "\n".intercalate acc.qsort.toList
  | none => return ""

/-- Look up a declaration's type as a string. Returns "" if not found. -/
@[python "leanpy_kernel_decl_type"]
def declType (name : String) : IO String := runCore do
  let n := name.toName
  match (← getEnv).find? n with
  | none => return ""
  | some info =>
    let pp ← Meta.MetaM.run' do
      Meta.ppExpr info.type
    return pp.pretty

/-- True iff the given name is defined in the environment. -/
@[python "leanpy_kernel_decl_exists"]
def declExists (name : String) : IO Bool := do
  match (← envRef.get) with
  | some env => return (env.find? name.toName).isSome
  | none => return false

/-! ### Parsing and elaboration -/

private def tryRunTerm (src : String) (k : Expr → MetaM String) : CoreM String := do
  let env ← getEnv
  match Parser.runParserCategory env `term src with
  | .error msg => return s!"<parse error: {msg}>"
  | .ok stx =>
    try
      Meta.MetaM.run' do
        let expr ← Term.TermElabM.run' (Term.elabTerm stx none)
        k (← Lean.instantiateMVars expr)
    catch e =>
      return s!"<elab error: {← e.toMessageData.toString}>"

/-- Parse + elaborate a term, then pretty-print its inferred type. -/
@[python "leanpy_kernel_infer_type"]
def inferType (src : String) : IO String := runCore do
  tryRunTerm src fun expr => do
    let ty ← Meta.inferType expr
    let pp ← Meta.ppExpr ty
    return pp.pretty

/-- Parse + elaborate a term, then pretty-print the term itself. -/
@[python "leanpy_kernel_pretty_print"]
def prettyPrint (src : String) : IO String := runCore do
  tryRunTerm src fun expr => do
    let pp ← Meta.ppExpr expr
    return pp.pretty

/-! ### Reductions -/

/-- Whnf-normalise an expression and pretty-print the result. -/
@[python "leanpy_kernel_whnf"]
def whnf (src : String) : IO String := runCore do
  tryRunTerm src fun expr => do
    let r ← Meta.whnf expr
    let pp ← Meta.ppExpr r
    return pp.pretty

end LeanPy.Kernel
