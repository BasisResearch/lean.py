/-
A small Pantograph-style façade exposing key Lean kernel operations to
Python: load an environment, infer types, list declarations, look up
the axioms a declaration depends on, and prove decidable propositions
through Lean's kernel `decide`.

This is intentionally a thin layer; real Pantograph is much larger.
The goal here is to show how to wire the Lean elaborator and decision
procedures through `@[python]` so a Python-driven prover can ride on top.
-/
import Lean
import LeanPy
import LeanPy.Kernel

open Lean Meta Elab

namespace PantographDemo

/-- Re-exports `LeanPy.Kernel.initSearch` under a stable Python name. -/
@[python "demo_init_search"]
def initSearch (sp : String) : IO Unit :=
  LeanPy.Kernel.initSearch sp

/-- Re-exports `LeanPy.Kernel.loadEnv`. -/
@[python "demo_load_env"]
unsafe def loadEnv (modules : Array String) : IO Unit :=
  LeanPy.Kernel.loadEnv modules

private def runCore (act : CoreM String) : IO String := do
  match (← LeanPy.Kernel.envRef.get) with
  | none => return "<no environment>"
  | some env =>
    let ctx : Core.Context := { fileName := "<demo>", fileMap := default }
    let st  : Core.State := { env }
    try
      let (r, _) ← act.toIO ctx st
      return r
    catch e =>
      return s!"<error: {e.toString}>"

/-- Names of all declarations in the environment whose name contains `needle`. -/
@[python "demo_search_decls"]
def searchDecls (needle : String) : IO String := do
  match (← LeanPy.Kernel.envRef.get) with
  | none => return ""
  | some env =>
    let r ← IO.mkRef (#[] : Array String)
    env.constants.forM fun n _ => do
      let s := toString n
      if needle.isEmpty || ((s.splitOn needle).length > 1) then
        r.modify (·.push s)
    let acc ← r.get
    return "\n".intercalate acc.qsort.toList

/-- Pretty-print the type of an existing declaration `name` (or "" if missing). -/
@[python "demo_decl_type"]
def declType (name : String) : IO String := runCore do
  let n := name.toName
  match (← getEnv).find? n with
  | none => return ""
  | some info =>
    let pp ← Meta.MetaM.run' do Meta.ppExpr info.type
    return pp.pretty

/-- Compute and return a sorted list of all axioms `decl` transitively depends on.
Useful for surfacing `Classical.choice`, `propext`, `sorry`, etc. -/
@[python "demo_decl_axioms"]
def declAxioms (decl : String) : IO String := runCore do
  let env ← getEnv
  let n := decl.toName
  if env.find? n |>.isNone then
    return ""
  let (_, st) := ((CollectAxioms.collect n).run env).run {}
  let names := st.axioms.toList.map toString |>.toArray.qsort
  return "\n".intercalate names.toList

/-- Decide a closed `Prop` through the kernel: parse, elaborate against
the `Prop` universe, synthesise `Decidable` and reduce.
Returns "true", "false", or an error string. -/
@[python "demo_decide"]
def decideProp (src : String) : IO String := runCore do
  let env ← getEnv
  match Parser.runParserCategory env `term src with
  | .error msg => return s!"<parse: {msg}>"
  | .ok stx =>
    try
      Meta.MetaM.run' do
        let expr ← Term.TermElabM.run'
          (Term.elabTermAndSynthesize stx (some (.sort .zero)))
        let expr ← Lean.instantiateMVars expr
        let dty ← Meta.mkAppM ``Decidable #[expr]
        let dec ← Meta.synthInstance dty
        let r ← Meta.whnf dec
        if r.isAppOf ``Decidable.isTrue then return "true"
        else if r.isAppOf ``Decidable.isFalse then return "false"
        else return "<undecided>"
    catch e =>
      return s!"<elab: {← e.toMessageData.toString}>"

/-- Re-expose `inferType`/`prettyPrint`/`whnf` from `LeanPy.Kernel`. -/
@[python "demo_infer_type"]
def inferType (src : String) : IO String := LeanPy.Kernel.inferType src
@[python "demo_pretty"]
def pretty (src : String) : IO String := LeanPy.Kernel.prettyPrint src
@[python "demo_whnf"]
def whnf (src : String) : IO String := LeanPy.Kernel.whnf src

end PantographDemo

#export_python_registry "PantographDemo"
