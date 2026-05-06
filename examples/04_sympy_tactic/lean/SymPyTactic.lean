/-
SymPy as a tactic.

`sympy` is a Lean tactic that sends the current goal's `Lean.Expr` tree
to Python via `Py.ofLeanObj`, where `lean_to_sympy.py` walks the ADT and
converts it to a SymPy expression. If SymPy reports the proposition is
identically true, the goal is closed with an *oracle* axiom.

The Python-callable surface:

- `sympy_expr_eq_accept`  : Lean.Expr → Lean.Expr → IO Bool
- `sympy_expr_check_prop` : Lean.Expr → IO Bool

The Lean tactic `sympy` is the user-facing surface for proofs.
-/
import Lean
import LeanPy
import LeanPy.Python

open Lean Meta Elab Tactic
open LeanPy LeanPy.Python

namespace SymPyTactic

/-- The oracle: any proposition SymPy accepts is true. This is
intentionally an axiom; it stands for "we trust the SymPy decision
procedure on this fragment". -/
axiom sympy_oracle (p : Prop) : p

/-! ### Expr-based interface

Pass `Lean.Expr` trees across the FFI instead of pretty-printed strings.
The Python side gets a fully-typed `LeanInductiveValue` mirror of the
Expr and converts to SymPy directly via `lean_to_sympy.py`. -/

/-- Expr-based equality check. Receives `Lean.Expr` trees (via the
`derive_python` Reflect registration) and delegates conversion entirely
to Python's `lean_to_sympy` module. -/
@[python "sympy_expr_eq_accept"]
def sympyExprEqAccept (lhs rhs : Lean.Expr) : IO Bool := do
  init ()
  let mod ← import_ "lean_to_sympy"
  let checkFn ← mod.getAttr "sympy_eq_check"
  let convFn ← mod.getAttr "expr_to_sympy"
  let lhsSy ← convFn.call #[← Py.ofLeanObj lhs]
  let rhsSy ← convFn.call #[← Py.ofLeanObj rhs]
  (← checkFn.call #[lhsSy, rhsSy]).toBool

/-- Check a proposition Expr via `Py.ofLeanObj` + Python-side decode. -/
@[python "sympy_expr_check_prop"]
def sympyExprCheckProp (e : Lean.Expr) : IO Bool := do
  init ()
  let handle ← Py.ofLeanObj e
  let mod ← import_ "lean_to_sympy"
  let checkFn ← mod.getAttr "decode_and_check_prop"
  (← checkFn.call #[handle]).toBool

/-! ### The `sympy` tactic -/

syntax (name := sympyTac) "sympy" : tactic

@[tactic sympyTac]
def evalSympy : Tactic := fun stx =>
  match stx with
  | `(tactic| sympy) => do
    let goal ← getMainGoal
    let goalType ← goal.getType
    let accepted ← sympyExprCheckProp goalType
    if !accepted then
      throwError "sympy: oracle rejected the goal"
    let proof ← Meta.mkAppOptM ``sympy_oracle #[goalType]
    goal.assign proof
  | _ => throwUnsupportedSyntax

end SymPyTactic

#export_python_registry "SymPyTactic"

/-!
## Using the `sympy` tactic

Example proofs (paste into a REPL with sympy on `PYTHONPATH`):

```lean
example : (1 : Int) + 1 = 2 := by sympy
example : (3 : Int) * 4 = 12 := by sympy
```
-/
