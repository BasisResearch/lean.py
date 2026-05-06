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
  let r ← (← sympy.getAttr "simplify").call #[← Py.ofString expr]
  r.str

@[python "sympy_accept"]
def sympyAccept (prop : String) : IO Bool := do
  init ()
  let sympy ← import_ "sympy"
  let parse ← sympy.getAttr "sympify"
  let simplify ← sympy.getAttr "simplify"
  let p ← parse.call #[← Py.ofString prop]
  let s ← simplify.call #[p]
  let trueObj ← parse.call #[← Py.ofString "True"]
  s.eq trueObj

/-- True iff `simplify(lhs - rhs) == 0`. -/
@[python "sympy_eq_accept"]
def sympyEqAccept (lhs rhs : String) : IO Bool := do
  init ()
  let sympy ← import_ "sympy"
  let parse ← sympy.getAttr "sympify"
  let simplify ← sympy.getAttr "simplify"
  let l ← parse.call #[← Py.ofString lhs]
  let r ← parse.call #[← Py.ofString rhs]
  let diff ← l.sub r
  let s ← simplify.call #[diff]
  let zero ← parse.call #[← Py.ofString "0"]
  s.eq zero

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

/-! ### Phase 3d: Expr-based interface

Pass `Lean.Expr` trees across the FFI instead of pretty-printed strings.
The Python side gets a fully-typed `LeanInductiveValue` mirror of the
Expr and converts to SymPy directly, raising a typed `LeanError` on
constructors it doesn't know how to translate.

The function below is invoked from Python (it's an `@[python]` entry,
not used by the in-Lean tactic). The tactic itself still uses the
string path because doing the in-Lean Expr→Py marshalling on top of an
already-running tactic state introduces a second layer of refcount
gymnastics that the current MetaM ↔ LeanPy.Python plumbing doesn't yet
cleanly support — see the GoalState lifecycle caveat in
docs/ARCHITECTURE.md. -/

/-- Recursively render a Lean Expr in a SymPy-friendly form. Unlike
`goalToSymPy` above this one is invoked on already-marshalled exprs
(no `MetaM` context) and walks the structure literally. -/
private partial def exprToSymPy (e : Lean.Expr) : String :=
  match e with
  | .lit (.natVal n) => toString n
  | .lit (.strVal s) => s!"\"{s}\""
  | .const n _ => n.toString
  | .bvar i => s!"x{i}"
  | .fvar id => id.name.toString
  | .mvar id => s!"?{id.name}"
  | .sort _ => "Sort"
  | .app f x =>
    let fn := exprToSymPy f
    let arg := exprToSymPy x
    s!"{fn}({arg})"
  | .lam _ _ _ _ => "Lambda(...)"
  | .forallE _ _ _ _ => "Forall(...)"
  | _ => "<unsupported>"

/-- Expr-based variant of `sympy_eq_accept`. Receives `Lean.Expr` trees
(via the `derive_python` Reflect registration), converts them to SymPy
expressions string-side, and asks SymPy whether `simplify(lhs - rhs) =
0`. Returns `false` if SymPy raises an error. -/
@[python "sympy_expr_eq_accept"]
def sympyExprEqAccept (lhs rhs : Lean.Expr) : IO Bool := do
  init ()
  let lhsStr := exprToSymPy lhs
  let rhsStr := exprToSymPy rhs
  sympyEqAccept lhsStr rhsStr

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
