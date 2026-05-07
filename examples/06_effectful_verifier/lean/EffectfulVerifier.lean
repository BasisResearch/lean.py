import LeanPy
import LeanPy.Kernel

open Lean Meta Elab Pantograph

namespace EffectfulVerifier

private def freshCoreContext : IO Core.Context := do
  return {
    fileName       := "<effectful_verifier>"
    fileMap        := { source := "", positions := #[0] }
    currNamespace  := `_root_
    openDecls      := []
    options        := Options.empty
    initHeartbeats := ← IO.getNumHeartbeats
  }

/-- Create a goal state from a fully-elaborated `Lean.Expr`. Unlike
`goalCreate` (which takes a string and parses/elaborates it), this takes
the `Expr` directly — useful when the expression is built on the Python
side as a `LeanInductiveValue` tree. -/
@[python "effectful_goal_from_expr"]
def goalFromExpr (e : Lean.Expr) : IO GoalState := do
  match (← LeanPy.Kernel.envRef.get) with
  | none => throw (IO.userError "no environment loaded")
  | some env =>
    let ctx ← freshCoreContext
    let cs : Core.State := { env }
    let inner : CoreM (Except String GoalState) := do
      try
        let r ← Meta.MetaM.run' do
          Term.TermElabM.run' do
            Meta.check e
            GoalState.create e
        return .ok r
      catch e => return .error (← e.toMessageData.toString)
    let (r, _) ← inner.toIO ctx cs
    match r with
    | .ok gs => return gs
    | .error msg => throw (IO.userError s!"goal_from_expr: {msg}")

end EffectfulVerifier

#export_python_registry "EffectfulVerifier"
