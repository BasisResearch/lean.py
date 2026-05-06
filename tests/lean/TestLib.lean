/-
TestLib: a Lean library used as the fixture for the lean-py test suite.

It exists because the test suite exercises every marshalled type, every
kind of function signature, the kernel facade, and the Python-in-Lean
bridge — and bundling those into a single library keeps the fixture
side small. End-user examples live under `examples/`.
-/
import LeanPy
import LeanPy.Kernel

open LeanPy

@[python "py_bar"]
def bar (x : Int) : Int := x + 1

@[python "py_foo"]
def foo (x : Int) : IO Int := do
  IO.println s!"foo({x})"
  return x + 1

@[python "py_greet"]
def greet (name : String) : IO String :=
  return s!"Hello, {name}!"

@[python "py_sum_list"]
def sumList (xs : Array Int) : Int :=
  xs.foldl (· + ·) 0

inductive Color where
  | red | green | blue
  deriving Repr

derive_python Color

structure Point where
  x : Int
  y : Int
  deriving Repr

derive_python Point

inductive Shape where
  | circle (r : Int)
  | square (side : Int)
  | rect   (w h : Int)
  deriving Repr

derive_python Shape

@[python "py_origin"]
def origin (_ : Unit) : Point := ⟨0, 0⟩

@[python "py_point_norm_sq"]
def pointNormSq (p : Point) : Int := p.x * p.x + p.y * p.y

@[python "py_make_circle"]
def mkCircle (r : Int) : Shape := .circle r

@[python "py_shape_perimeter"]
def shapePerimeter (s : Shape) : Int :=
  match s with
  | .circle r => 6 * r
  | .square s => 4 * s
  | .rect w h => 2 * (w + h)

@[python "py_color_id"]
def colorId (c : Color) : Int :=
  match c with
  | .red => 0
  | .green => 1
  | .blue => 2

/-! ### Python-in-Lean smoke tests

These exercise the new (Phase 1) dot-syntax form: operations on `Py`
values now resolve through `Py.<op>` so `pyVal.getAttr "..."` works
just like a method call. -/

open LeanPy.Python in
@[python "py_python_eval_int"]
def pythonEvalInt (src : String) : IO Int := do
  init ()
  (← eval src).toInt

open LeanPy.Python in
@[python "py_python_eval_str"]
def pythonEvalStr (src : String) : IO String := do
  init ()
  (← eval src).str


open LeanPy.Python in
@[python "py_python_call1_int"]
def pythonCall1Int (mod : String) (fn : String) (arg : Int) : IO Int := do
  init ()
  let m ← import_ mod
  -- exercise dot-syntax chains: m.getAttr → returned Py is `f`,
  -- then f.call yields a Py whose `.toInt` we read.
  let f ← m.getAttr fn
  let r ← f.call #[← Py.ofInt64 arg]
  r.toInt

/-! ### sympy / numpy demos used by the test suite -/

open LeanPy.Python in
@[python "py_sympy_simplify"]
def sympySimplify (expr : String) : IO String := do
  init ()
  let sympy ← import_ "sympy"
  let result ← (← sympy.getAttr "simplify").call #[← Py.ofString expr]
  result.str

open LeanPy.Python in
@[python "py_numpy_sum"]
def numpySum (xs : Array Int) : IO Int := do
  init ()
  let np ← import_ "numpy"
  let arrayFn ← np.getAttr "array"
  let mut pylist : Array LeanPy.Python.Py := #[]
  for x in xs do
    pylist := pylist.push (← Py.ofInt64 x)
  let arr ← arrayFn.call #[← Py.ofList pylist]
  let res ← arr.callMethod "sum" #[]
  (← res.callMethod "item" #[]).toInt

/-! ### Phase 3: bidirectional introspection fixtures -/

open Lean

/-- Build a `Lean.Name` from Lean code. Python should be able to decode
this as a `Name.str (Name.str Name.anonymous "foo") "bar"`. -/
@[python "py_make_name"]
def makeName (_ : Unit) : Lean.Name :=
  .str (.str .anonymous "foo") "bar"

/-- Round-trip a `Name`: Python builds it, hands it to us, we render. -/
@[python "py_name_to_string"]
def nameToString (n : Lean.Name) : String := n.toString

/-- Build an `Lean.Expr.app f x` from Lean. Python should see the full
constructor structure. -/
@[python "py_make_app_expr"]
def makeAppExpr (_ : Unit) : Lean.Expr :=
  .app (.const `Nat.succ []) (.const `Nat.zero [])

/-- Read a Lean.Expr's app args; expects an `app` ctor and returns the
applied function and argument as strings. -/
@[python "py_expr_describe"]
def exprDescribe (e : Lean.Expr) : String :=
  match e with
  | .const n _ => s!"const {n}"
  | .app f x   => s!"app ({exprDescribe f}) ({exprDescribe x})"
  | .lit (.natVal n) => s!"natLit {n}"
  | .lit (.strVal s) => s!"strLit {s.length}"
  | _ => "<other>"

/-! ### Phase 3b: live `Py` round-trip fixture -/

open LeanPy.Python in
/-- Builds a Python list `[1, 2, 3]` in Lean and returns it as a `Py`.
The Python wrapper should decode this as a real `list`, not an opaque
`LeanObj`. -/
@[python "py_make_list_123"]
def makeList123 (_ : Unit) : IO Py := do
  init ()
  let xs ← #[1, 2, 3].mapM Py.ofInt64
  Py.ofList xs

/-! ### Phase 4: Python ↔ Lean exception support fixtures -/

open LeanPy.Python in
/-- Try a Python eval; on failure return a sentinel string carrying the
caught Python exception's type and message. Used by tests/test_exceptions.py. -/
@[python "py_eval_or_describe_error"]
def evalOrDescribeError (src : String) : IO String := do
  init ()
  tryCatchPy
    (do let r ← eval src; r.str)
    (fun e => return s!"caught:{e.typeName}:{e.message}")

open LeanPy.Python in
/-- Raise a Lean-level IO error. The Python wrapper should see this as a
typed `LeanError(kind="userError", ...)`. -/
@[python "py_lean_panic"]
def leanPanic (msg : String) : IO Unit := do
  throw (IO.userError msg)

open LeanPy.Python in
/-- Reraise a Python exception verbatim (no `tryCatch`). Used to verify
the typed `LeanPyCallbackError` decoding on the Python side. -/
@[python "py_propagate_python_error"]
def propagatePythonError (src : String) : IO String := do
  init ()
  let r ← eval src
  r.str

/-! ### Phase 1: dot-syntax compilability checks

These functions exist so the build catches regressions if dot-syntax
on `Py` ever stops resolving. They are not invoked from the test suite
but their compilation is the test. -/

open LeanPy.Python in
@[python "py_dot_syntax_smoke"]
def dotSyntaxSmoke (_ : Unit) : IO String := do
  init ()
  let mod ← import_ "math"
  let pi ← mod.getAttr "pi"
  let cos ← mod.getAttr "cos"
  let zero ← Py.ofFloat 0.0
  let r ← cos.call #[zero]
  -- chain: r.add(pi).mul(pi).repr — exercise method-style binding
  let s ← (← (← r.add pi).mul pi).repr
  return s

/-! ### Phase 3d: Expr-based Lean→Python interop -/

/-- A Lean.Expr that's been received as an argument from Python (the
Python caller built it via `lib.Expr.const(...)` etc.) is round-trippable
unchanged. Returns its `.toString` rendering. -/
@[python "py_expr_round_trip_to_string"]
def exprRoundTripToString (e : Lean.Expr) : String := e.dbgToString

/-- Render a Lean.Expr passed from Python as a structural string —
demonstrates that we can do per-constructor pattern matching on an
Expr that originated as a `LeanInductiveValue` in Python. -/
@[python "py_expr_structural_summary"]
partial def exprStructuralSummary : Lean.Expr → String
  | .const n _ => s!"const({n})"
  | .app f x => s!"app({exprStructuralSummary f}, {exprStructuralSummary x})"
  | .lam _ ty body _ => s!"lam(_, {exprStructuralSummary ty}, {exprStructuralSummary body})"
  | .bvar i => s!"bvar({i})"
  | .lit (.natVal n) => s!"nat({n})"
  | .lit (.strVal s) => s!"str({s})"
  | _ => "<other>"

/-! ### Phase 3c: Lean closures as Python callables

These fixtures expose Lean closures to Python via `Py.fromLeanCallable`
and `Py.fromLeanCallableKw`. The Python side calls the returned object
like any other callable; the closure runs in IO. -/

open LeanPy.Python in
/-- Wrap a Lean function `Array Py → IO Py` that sums its int args. -/
@[python "py_make_lean_sum_callable"]
def makeLeanSumCallable (_ : Unit) : IO Py := do
  init ()
  Py.fromLeanCallable fun args => do
    let mut total : Int := 0
    for a in args do
      total := total + (← a.toInt)
    Py.ofInt64 total

open LeanPy.Python in
/-- Wrap a Lean closure that returns its single argument's repr. -/
@[python "py_make_lean_repr_callable"]
def makeLeanReprCallable (_ : Unit) : IO Py := do
  init ()
  Py.fromLeanCallable fun args => do
    match h : args.size with
    | 1 =>
      have hLt : 0 < args.size := h ▸ Nat.zero_lt_one
      Py.ofString (← args[0].repr)
    | _ => throw (IO.userError s!"expected 1 arg, got {args.size}")

open LeanPy.Python in
/-- Closure that reads kwargs and returns
`{ "args_count": n, "kwargs_keys": ["a", "b"] }`. Demonstrates the
keyword-aware variant. -/
@[python "py_make_lean_kw_callable"]
def makeLeanKwCallable (_ : Unit) : IO Py := do
  init ()
  Py.fromLeanCallableKw fun args kwargs => do
    let n := args.size
    let keys := kwargs.map (·.fst)
    let mut keyPyList : Array Py := #[]
    for k in keys do
      keyPyList := keyPyList.push (← Py.ofString k)
    let keysPy ← Py.ofList keyPyList
    Py.ofStringDict #[
      ("args_count", ← Py.ofInt64 n),
      ("kwargs_keys", keysPy)
    ]

open LeanPy.Python in
/-- A closure that throws an IO error — the Python caller should see
this as a `RuntimeError` whose message is the IO.userError payload. -/
@[python "py_make_lean_failing_callable"]
def makeLeanFailingCallable (_ : Unit) : IO Py := do
  init ()
  Py.fromLeanCallable fun _ => do
    throw (IO.userError "intentional Lean failure from closure")

open LeanPy.Python in
/-- A Lean callback usable as a 3-arg setter: `(self, key, value) →
self[key] = value*2`. The Python side will invoke it imperatively. -/
@[python "py_make_doubling_setter"]
def makeDoublingSetter (_ : Unit) : IO Py := do
  init ()
  Py.fromLeanCallable fun args => do
    match h : args.size with
    | 3 =>
      let self := args[0]
      let key := args[1]
      let val := args[2]
      let vint ← val.toInt
      let doubled ← Py.ofInt64 (vint * 2)
      self.setItem key doubled
      Py.none ()
    | _ => throw (IO.userError s!"expected 3 args, got {args.size}")

#export_python_registry "TestLib"
