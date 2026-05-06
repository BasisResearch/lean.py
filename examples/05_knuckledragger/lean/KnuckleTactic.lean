/-
Knuckledragger / Z3 as a tactic.

`knuckle` is a Lean tactic that sends the current goal's `Lean.Expr` tree
to Python via `Py.ofLeanObj`, where `lean_to_z3.py` walks the ADT and
converts it to a Z3 expression. If Z3 (or Knuckledragger) discharges the
proposition, the goal is closed with an *oracle* axiom.

The Python-callable surface:

- `knuckle_expr_eq_accept`  : Lean.Expr → Lean.Expr → IO Bool
- `knuckle_expr_check_prop` : Lean.Expr → IO Bool

The Lean tactic `knuckle` is the user-facing surface for proofs.
-/
import Lean
import LeanPy
import LeanPy.Python

open Lean Meta Elab Tactic
open LeanPy LeanPy.Python

namespace KnuckleTactic

/-- Oracle: any proposition Knuckledragger / Z3 accepts is true. -/
axiom knuckle_oracle (p : Prop) : p

/-! ### Expr-based interface

Pass `Lean.Expr` trees across the FFI instead of pretty-printed strings.
The Python side gets a fully-typed `LeanInductiveValue` mirror of the
Expr and converts to Z3 directly via `lean_to_z3.py`. -/

/-- Expr-based equality check via Z3. -/
@[python "knuckle_expr_eq_accept"]
def knuckleExprEqAccept (lhs rhs : Lean.Expr) : IO Bool := do
  init ()
  let mod ← import_ "lean_to_z3"
  let checkFn ← mod.getAttr "z3_eq_check"
  let convFn ← mod.getAttr "expr_to_z3"
  let lhsZ3 ← convFn.call #[← Py.ofLeanObj lhs]
  let rhsZ3 ← convFn.call #[← Py.ofLeanObj rhs]
  (← checkFn.call #[lhsZ3, rhsZ3]).toBool

/-- Check a proposition Expr via Z3 / Knuckledragger. -/
@[python "knuckle_expr_check_prop"]
def knuckleExprCheckProp (e : Lean.Expr) : IO Bool := do
  init ()
  let handle ← Py.ofLeanObj e
  let mod ← import_ "lean_to_z3"
  let checkFn ← mod.getAttr "decode_and_check_prop"
  (← checkFn.call #[handle]).toBool

/-! ### The `knuckle` tactic -/

syntax (name := knuckleTac) "knuckle" : tactic

@[tactic knuckleTac]
def evalKnuckle : Tactic := fun stx =>
  match stx with
  | `(tactic| knuckle) => do
    let goal ← getMainGoal
    let goalType ← goal.getType
    let accepted ← knuckleExprCheckProp goalType
    if !accepted then
      throwError "knuckle: Z3/Knuckledragger rejected the goal"
    let proof ← Meta.mkAppOptM ``knuckle_oracle #[goalType]
    goal.assign proof
  | _ => throwUnsupportedSyntax

end KnuckleTactic

#export_python_registry "KnuckleTactic"

/-!
## Using the `knuckle` tactic

Example proofs (paste into a REPL with z3-solver on the host's PYTHONPATH):

```lean
example : (1 : Int) + 1 = 2 := by knuckle
example : ∀ x : Int, x + 0 = x := by knuckle
```
-/
