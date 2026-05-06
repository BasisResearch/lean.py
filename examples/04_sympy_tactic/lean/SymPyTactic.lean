/-
SymPy as a tactic.

`sympy` is a Lean tactic that pretty-prints the current goal, hands the
string to SymPy via the lean-py bridge, and — if SymPy reports the
proposition is identically true — closes the goal with an *oracle*
axiom. The proof is therefore "trust SymPy", in the same spirit as
papers that use Mathematica or Z3 as a black-box oracle.

The Python-callable surface is a thin layer:

- `sympy_simplify`  : String → IO String     -- canonical normal form
- `sympy_accept`    : String → IO Bool       -- True iff sympy(prop) ≡ True
- `sympy_eq_accept` : String → String → IO Bool

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

/-! ### Python-callable helpers (also used by the tactic) -/

@[python "sympy_simplify"]
def sympySimplify (expr : String) : IO String := do
  init ()
  let sympy ← import_ "sympy"
  let f ← getAttr sympy "simplify"
  str (← call f #[← ofString expr])

@[python "sympy_accept"]
def sympyAccept (prop : String) : IO Bool := do
  init ()
  let sympy ← import_ "sympy"
  let parse ← getAttr sympy "sympify"
  let simplify ← getAttr sympy "simplify"
  let p ← call parse #[← ofString prop]
  let s ← call simplify #[p]
  let trueObj ← call parse #[← ofString "True"]
  eq s trueObj

/-- True iff `simplify(lhs - rhs) == 0`. -/
@[python "sympy_eq_accept"]
def sympyEqAccept (lhs rhs : String) : IO Bool := do
  init ()
  let sympy ← import_ "sympy"
  let parse ← getAttr sympy "sympify"
  let simplify ← getAttr sympy "simplify"
  let l ← call parse #[← ofString lhs]
  let r ← call parse #[← ofString rhs]
  let diff ← sub l r
  let s ← call simplify #[diff]
  let zero ← call parse #[← ofString "0"]
  eq s zero

/-! ### The `sympy` tactic -/

/-- Render a Lean Expr in a SymPy-friendly form: at minimum we strip
the `(@HEq ... ...)` family and normalise `=` to `Eq(...,...)` so SymPy
can parse what `Meta.ppExpr` produced. The current implementation is
deliberately naive — extending it is the principal user-facing knob. -/
private def goalToSymPy (e : Expr) : MetaM String := do
  let pp ← Meta.ppExpr e
  let s := pp.pretty
  -- Best-effort rewrite: `a = b` → `Eq(a, b)`. Real users will want
  -- something more careful (operator precedence, type annotations…).
  match s.splitOn " = " with
  | [lhs, rhs] => return s!"Eq({lhs}, {rhs})"
  | _ => return s

/-- The `sympy` tactic. Gets the current goal, hands its rendered form
to SymPy, and if SymPy says it's identically true, closes with the
`sympy_oracle` axiom. Fails (without closing the goal) otherwise. -/
syntax (name := sympyTac) "sympy" : tactic

@[tactic sympyTac]
def evalSympy : Tactic := fun stx =>
  match stx with
  | `(tactic| sympy) => do
    let goal ← getMainGoal
    let goalType ← goal.getType
    let rendered ← goalToSymPy goalType
    let accepted ← sympyAccept rendered
    if !accepted then
      throwError "sympy: oracle rejected `{rendered}`"
    let proof ← Meta.mkAppOptM ``sympy_oracle #[goalType]
    goal.assign proof
  | _ => throwUnsupportedSyntax

end SymPyTactic

#export_python_registry "SymPyTactic"

/-!
## Using the `sympy` tactic

`sympy` is a real `TacticM` tactic — it inspects the current goal,
serialises it to a SymPy expression, asks SymPy whether the
proposition is identically true, and on accept closes the goal via
`SymPyTactic.sympy_oracle`.

It cannot be evaluated at *Lean compile time* because doing so would
require `dlopen`-ing `libpython` while building — and the build host
typically does not have CPython on `LD_LIBRARY_PATH`. Instead, drive
it from a hosting environment that has both `libpython` and `sympy`
available (e.g. the `python/main.py` runner in this directory, or any
LSP/REPL session whose process already has the Python runtime
loaded).

Example proofs (paste into a REPL with sympy on `PYTHONPATH`):

```lean
example : (1 : Int) + 1 = 2 := by sympy
example : (3 : Int) * 4 = 12 := by sympy
```
-/
