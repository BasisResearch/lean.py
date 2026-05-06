/-
LeanPy.Kernel: a Pantograph-equivalent kernel facade.

The implementation files (`LeanPy/Kernel/*.lean`) are lifted, with
attribution, from Pantograph (https://github.com/lenianiva/Pantograph,
licensed under GPL-3.0+; the upstream copy of the code lives in this
repo at `_examples/Pantograph/`). Where pantograph wires things to a
JSON REPL we instead expose them through `@[python]` for direct C ABI
use, but the goal-state semantics, tactic execution, frontend
processing, environment serialisation, and delab logic are all
identical.

This top-level module:
  1. Re-exports every operations module so users can write
     `import LeanPy.Kernel` and get the full surface.
  2. Provides global `envRef`/`initSearch`/`loadEnv`/`isLoaded`/
     `clearEnv` plus monad runners `runCore` / `runMeta` / `runTermElabM`
     that bind to the active env.
  3. Adds `@[python]`-tagged wrappers around every operation pantograph
     `@[export]`s, so Python callers see them as ordinary FFI symbols.

Pantograph attributions live in the per-module file headers.
-/
import Lean
import LeanPy.Registry
import LeanPy.Attr
import LeanPy.Kernel.Goal
import LeanPy.Kernel.Frontend
import LeanPy.Kernel.Serial
import LeanPy.Kernel.Delab

open Lean Meta Elab

namespace LeanPy.Kernel

/-! ## Environment lifecycle -/

/-- Active environment used by all kernel ops. Set via `loadEnv`. -/
initialize envRef : IO.Ref (Option Environment) ← IO.mkRef none

@[python "leanpy_kernel_init_search"]
def initSearch (sp : String) : IO Unit := do
  Lean.initSearchPath (← Lean.findSysroot) (sp := System.SearchPath.parse sp)

@[python "leanpy_kernel_load_env"]
unsafe def loadEnv (modules : Array String) : IO Unit := do
  Lean.enableInitializersExecution
  let imports : Array Import := modules.map (fun n => { module := n.toName })
  let env ← Lean.importModules imports {} (loadExts := true)
  envRef.set (some env)

@[python "leanpy_kernel_is_loaded"]
def isLoaded (_ : Unit) : IO Bool := do
  return (← envRef.get).isSome

@[python "leanpy_kernel_clear_env"]
def clearEnv (_ : Unit) : IO Unit :=
  envRef.set none

/-- Build a `Core.Context` matching pantograph's defaults plus a fresh
`initHeartbeats` for timeout accounting. -/
private def freshCoreContext : IO Core.Context := do
  return {
    fileName       := "<lean_py.kernel>"
    fileMap        := { source := "", positions := #[0] }
    currNamespace  := `_root_
    openDecls      := []
    options        := Options.empty
    initHeartbeats := ← IO.getNumHeartbeats
  }

/-- Run a `CoreM` action against the active env, returning the inner
String (already pretty-printed). On error, returns a `<error: ...>`
sentinel rather than throwing. -/
def runCore (act : CoreM String) : IO String := do
  match (← envRef.get) with
  | some env =>
    let ctx ← freshCoreContext
    let state : Core.State := { env }
    try
      let (r, _) ← (act.toIO ctx state)
      return r
    catch e =>
      return s!"<error: {e.toString}>"
  | none => return "<no environment loaded>"

private def ppExprStr (e : Expr) : MetaM String := do
  let pp ← Meta.ppExpr e
  return pp.pretty

/-! ## Declaration introspection (formerly `LeanPy/Kernel.lean` ops) -/

@[python "leanpy_kernel_decl_count"]
def declCount (_ : Unit) : IO Int := do
  match (← envRef.get) with
  | some env =>
    let r ← IO.mkRef 0
    env.constants.forM (fun _ _ => do r.modify (· + 1))
    return (← r.get)
  | none => return 0

@[python "leanpy_kernel_all_decls"]
def allDecls (_ : Unit) : IO String := do
  match (← envRef.get) with
  | some env =>
    let r ← IO.mkRef (#[] : Array String)
    env.constants.forM (fun n _ => do r.modify (·.push (toString n)))
    let acc ← r.get
    return "\n".intercalate acc.qsort.toList
  | none => return ""

@[python "leanpy_kernel_catalog"]
def catalogPy (_ : Unit) : IO String := do
  match (← envRef.get) with
  | some env =>
    let names := envCatalog env
    let strs := names.map toString
    return "\n".intercalate strs.qsort.toList
  | none => return ""

@[python "leanpy_kernel_search"]
def search (needle : String) : IO String := do
  match (← envRef.get) with
  | some env =>
    let r ← IO.mkRef (#[] : Array String)
    env.constants.forM fun n _ => do
      let s := toString n
      if needle.isEmpty || ((s.splitOn needle).length > 1) then
        r.modify (·.push s)
    let acc ← r.get
    return "\n".intercalate acc.qsort.toList
  | none => return ""

@[python "leanpy_kernel_decl_exists"]
def declExists (name : String) : IO Bool := do
  match (← envRef.get) with
  | some env => return (env.find? name.toName).isSome
  | none => return false

@[python "leanpy_kernel_decl_type"]
def declType (name : String) : IO String := runCore do
  let n := name.toName
  match (← getEnv).find? n with
  | none => return ""
  | some info =>
    Meta.MetaM.run' do ppExprStr info.type

@[python "leanpy_kernel_decl_value"]
def declValue (name : String) : IO String := runCore do
  let n := name.toName
  match (← getEnv).find? n with
  | none => return ""
  | some info =>
    match info.value? with
    | none   => return ""
    | some v => Meta.MetaM.run' do ppExprStr v

@[python "leanpy_kernel_module_of_name_str"]
def moduleOfNameStr (name : String) : IO String := do
  match (← envRef.get) with
  | some env =>
    match module_of_name env name.toName with
    | some n => return toString n
    | none   => return ""
  | none => return ""

@[python "leanpy_kernel_is_internal_name_str"]
def isInternalNameStr (name : String) : IO Bool :=
  return isNameInternal name.toName

@[python "leanpy_kernel_decl_axioms"]
def declAxioms (name : String) : IO String := runCore do
  let env ← getEnv
  let n := name.toName
  if env.find? n |>.isNone then
    return ""
  let (_, st) := ((CollectAxioms.collect n).run env).run {}
  let names := st.axioms.toList.map toString |>.toArray.qsort
  return "\n".intercalate names.toList

/-! ## Elaboration -/

private def withTerm (src : String) (k : Expr → MetaM String) : CoreM String := do
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

@[python "leanpy_kernel_infer_type"]
def inferType (src : String) : IO String := runCore do
  withTerm src fun expr => do
    let ty ← Meta.inferType expr
    ppExprStr ty

@[python "leanpy_kernel_pretty_print"]
def prettyPrint (src : String) : IO String := runCore do
  withTerm src fun expr => ppExprStr expr

@[python "leanpy_kernel_whnf"]
def whnf (src : String) : IO String := runCore do
  withTerm src fun expr => do
    let r ← Meta.whnf expr
    ppExprStr r

@[python "leanpy_kernel_expr_echo"]
def exprEchoStr (src : String) : IO String := runCore do
  withTerm src fun expr => do
    let ty ← Meta.inferType expr
    let exprStr ← ppExprStr expr
    let tyStr   ← ppExprStr ty
    return s!"{exprStr}\n---\n{tyStr}"

@[python "leanpy_kernel_parse_type"]
def parseTypeStr (src : String) : IO String := runCore do
  let env ← getEnv
  match Parser.runParserCategory env `term src with
  | .error msg => return s!"<parse error: {msg}>"
  | .ok stx =>
    try
      Meta.MetaM.run' do
        Term.TermElabM.run' do
          let expr ← Term.elabType stx
          let expr ← Lean.instantiateMVars expr
          ppExprStr expr
    catch e =>
      return s!"<elab error: {← e.toMessageData.toString}>"

@[python "leanpy_kernel_decide"]
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

/-! ## Goal state — Python-facing wrappers

The full goal-state surface is in `LeanPy/Kernel/Goal.lean` (lifted
from pantograph). These Python entry points wrap the major operations
in a way that's easy to invoke through `@[python]`. -/

/-- Create a fresh goal state for a type-as-a-string. Throws an
`IO.userError` on parse/elaboration failure (which surfaces as
`LeanError` on the Python side). -/
@[python "leanpy_kernel_goal_create"]
def goalCreate (typeStr : String) : IO GoalState := do
  match (← envRef.get) with
  | none => throw (IO.userError "no environment loaded")
  | some env =>
    let ctx ← freshCoreContext
    let cs : Core.State := { env }
    match Parser.runParserCategory env `term typeStr with
    | .error msg => throw (IO.userError s!"parse error: {msg}")
    | .ok stx =>
      let inner : CoreM (Except String GoalState) := do
        try
          let r ← Meta.MetaM.run' do
            Term.TermElabM.run' do
              let target ← Elab.Term.elabType stx
              GoalState.create target
          return .ok r
        catch e => return .error (← e.toMessageData.toString)
      let (r, _) ← inner.toIO ctx cs
      match r with
      | .ok gs => return gs
      | .error msg => throw (IO.userError s!"elab error: {msg}")

@[python "leanpy_kernel_goal_is_solved"]
def goalIsSolved (state : GoalState) : IO Bool := return state.isSolved

@[python "leanpy_kernel_goal_n_goals"]
def goalNGoals (state : GoalState) : IO Int := return state.goals.length

@[python "leanpy_kernel_goal_main_goal_name"]
def goalMainGoalName (state : GoalState) : IO String :=
  return match state.mainGoal? with
  | some m => toString m.name
  | none   => ""

@[python "leanpy_kernel_goal_root_expr"]
def goalRootExprPy (state : GoalState) : IO String := do
  match (← envRef.get) with
  | none => return ""
  | some env =>
    let ctx ← freshCoreContext
    let cs : Core.State := { env }
    try
      let act : MetaM String := do
        state.restoreMetaM
        match state.rootExpr? with
        | none   => return ""
        | some e => ppExprStr e
      let (s, _) ← act.run'.toIO ctx cs
      return s
    catch _ => return ""

@[python "leanpy_kernel_goal_pretty"]
def goalPretty (state : GoalState) : IO String := do
  match (← envRef.get) with
  | none => return "<no env>"
  | some env =>
    let ctx ← freshCoreContext
    let cs : Core.State := { env }
    try
      let (s, _) ← (Meta.MetaM.run' (s := state.metaState) do
        let goals := state.goals
        let strs ← goals.mapM fun mvarId => do
          let some decl := (← getMCtx).findDecl? mvarId | return s!"<missing {mvarId.name}>"
          Meta.withLCtx decl.lctx decl.localInstances do
            let mut hyps : Array String := #[]
            for fvar in decl.lctx do
              if fvar.isAuxDecl || fvar.isImplementationDetail then continue
              let ty ← ppExprStr fvar.type
              hyps := hyps.push s!"{fvar.userName} : {ty}"
            let target ← ppExprStr decl.type
            let body := if hyps.isEmpty then "" else "\n".intercalate hyps.toList ++ "\n"
            return s!"{body}⊢ {target}"
        return "\n\n".intercalate strs).toIO ctx cs
      return s
    catch e => return s!"<error: {e.toString}>"

private def messageDataToString (m : MessageData) : IO String :=
  -- MessageData needs a context to render. Use the empty default for our
  -- purposes; the user can call `goalPretty` for formatted output.
  m.format >>= fun f => return f.pretty

private def msgToString (m : Lean.Message) : IO String := messageDataToString m.data

private def encodeTacticResult : TacticResult → IO String
  | .success _ msgs       => do
    let strs ← msgs.toList.mapM msgToString
    return "success\n" ++ "\n".intercalate strs
  | .failure msgs         => do
    let strs ← msgs.toList.mapM msgToString
    return "failure\n" ++ "\n".intercalate strs
  | .parseError msg       => return s!"parseError\n{msg}"
  | .invalidAction msg    => return s!"invalidAction\n{msg}"

private def runGoalTactic (state : GoalState) (act : Elab.TermElabM TacticResult) :
    IO (String × Option GoalState) := do
  match (← envRef.get) with
  | none => return ("invalidAction\nno environment loaded", none)
  | some env =>
    let ctx ← freshCoreContext
    let cs : Core.State := { env }
    try
      let (r, _) ← (Meta.MetaM.run' (Term.TermElabM.run' act)).toIO ctx cs
      let msg ← encodeTacticResult r
      let next? := match r with
        | .success s _ => some s
        | _            => none
      return (msg, next?)
    catch e =>
      return (s!"failure\n{e.toString}", none)

/-- Run a single string tactic on the main goal (focus). -/
@[python "leanpy_kernel_goal_try_tactic"]
def goalTryTactic (state : GoalState) (tactic : String) :
    IO (String × Option GoalState) := do
  match state.mainGoal? with
  | none => return ("invalidAction\nno goals", none)
  | some g => runGoalTactic state (state.tryTactic (.focus g) tactic)

/-- Direct expression assignment to the main goal. -/
@[python "leanpy_kernel_goal_try_assign"]
def goalTryAssign (state : GoalState) (expr : String) :
    IO (String × Option GoalState) := do
  match state.mainGoal? with
  | none => return ("invalidAction\nno goals", none)
  | some g => runGoalTactic state (state.tryAssign (.focus g) expr)

/-- Enter `conv` mode on the main goal. -/
@[python "leanpy_kernel_goal_conv_enter"]
def goalConvEnter (state : GoalState) : IO (String × Option GoalState) := do
  match state.mainGoal? with
  | none => return ("invalidAction\nno goals", none)
  | some g => runGoalTactic state (state.convEnter (.focus g))

/-- Enter `calc` mode on the main goal. -/
@[python "leanpy_kernel_goal_calc_enter"]
def goalCalcEnter (state : GoalState) : IO (String × Option GoalState) := do
  match state.mainGoal? with
  | none => return ("invalidAction\nno goals", none)
  | some g => runGoalTactic state (state.calcEnter (.focus g))

/-- Exit any active `conv`/`calc` fragment. -/
@[python "leanpy_kernel_goal_fragment_exit"]
def goalFragmentExit (state : GoalState) : IO (String × Option GoalState) := do
  match state.mainGoal? with
  | none => return ("invalidAction\nno goals", none)
  | some g => runGoalTactic state (state.fragmentExit (.focus g))

/-- Resume a list of named goals. -/
@[python "leanpy_kernel_goal_resume"]
def goalResume (state : GoalState) (goalNames : Array String) :
    IO (Option GoalState × String) := do
  let mvars := goalNames.toList.map fun s => MVarId.mk s.toName
  match state.resume mvars with
  | .ok s => return (some s, "")
  | .error e => return (none, e)

/-- Continue from `branch` over the goals of `target`. -/
@[python "leanpy_kernel_goal_continue"]
def goalContinue (target branch : GoalState) :
    IO (Option GoalState × String) := do
  match target.continue branch with
  | .ok s => return (some s, "")
  | .error e => return (none, e)

end LeanPy.Kernel
