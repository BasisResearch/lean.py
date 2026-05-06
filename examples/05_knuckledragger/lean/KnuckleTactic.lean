/-
Knuckledragger as a tactic.

Knuckledragger (https://github.com/philzook58/knuckledragger) is a
Python proof assistant built on Z3 / SMT. We use it the same way we
used SymPy in `04_sympy_tactic`: hand the Lean goal to a Python
function, return whether Knuckledragger / Z3 accepts, and close the
Lean goal via an oracle axiom on accept.

The pattern is identical to the SymPy demo. The two oracles can be
mixed in the same Lean file because Lean does not care which Python
library is on the other side of the bridge.
-/
import Lean
import LeanPy
import LeanPy.Python

open Lean Meta Elab Tactic
open LeanPy LeanPy.Python

namespace KnuckleTactic

/-- Oracle: any proposition Knuckledragger / Z3 accepts is true. -/
axiom knuckle_oracle (p : Prop) : p

/-! ### Python-callable surface -/

/-- True iff Knuckledragger (via Z3) discharges the proposition. -/
@[python "knuckle_accept"]
def knuckleAccept (prop : String) : IO Bool := do
  init ()
  let mod ← import_ "knuckle_bridge"
  let f ← getAttr mod "accept"
  toBool (← call f #[← ofString prop])

/-- True iff `lhs == rhs` is discharged. -/
@[python "knuckle_eq_accept"]
def knuckleEqAccept (lhs rhs : String) : IO Bool := do
  init ()
  let mod ← import_ "knuckle_bridge"
  let f ← getAttr mod "eq_accept"
  toBool (← call f #[← ofString lhs, ← ofString rhs])

/-! ### The `knuckle` tactic -/

private def goalToZ3 (e : Expr) : MetaM String := do
  let pp ← Meta.ppExpr e
  return pp.pretty

syntax (name := knuckleTac) "knuckle" : tactic

@[tactic knuckleTac]
def evalKnuckle : Tactic := fun stx =>
  match stx with
  | `(tactic| knuckle) => do
    let goal ← getMainGoal
    let goalType ← goal.getType
    let rendered ← goalToZ3 goalType
    let accepted ← knuckleAccept rendered
    if !accepted then
      throwError "knuckle: Z3/Knuckledragger rejected `{rendered}`"
    let proof ← Meta.mkAppOptM ``knuckle_oracle #[goalType]
    goal.assign proof
  | _ => throwUnsupportedSyntax

end KnuckleTactic

#export_python_registry "KnuckleTactic"
