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

/-! ### Python-in-Lean smoke tests -/

open LeanPy.Python in
@[python "py_python_eval_int"]
def pythonEvalInt (src : String) : IO Int := do
  init ()
  toInt (← eval src)

open LeanPy.Python in
@[python "py_python_eval_str"]
def pythonEvalStr (src : String) : IO String := do
  init ()
  str (← eval src)


open LeanPy.Python in
@[python "py_python_call1_int"]
def pythonCall1Int (mod : String) (fn : String) (arg : Int) : IO Int := do
  init ()
  let m ← import_ mod
  let f ← getAttr m fn
  toInt (← call f #[← ofInt64 arg])

/-! ### sympy / numpy demos used by the test suite -/

open LeanPy.Python in
@[python "py_sympy_simplify"]
def sympySimplify (expr : String) : IO String := do
  init ()
  let sympy ← import_ "sympy"
  let simplify ← getAttr sympy "simplify"
  str (← call simplify #[← ofString expr])

open LeanPy.Python in
@[python "py_numpy_sum"]
def numpySum (xs : Array Int) : IO Int := do
  init ()
  let np ← import_ "numpy"
  let arrayFn ← getAttr np "array"
  let mut pylist : Array LeanPy.Python.Py := #[]
  for x in xs do
    pylist := pylist.push (← ofInt64 x)
  let arr ← call arrayFn #[← ofList pylist]
  let res ← call (← getAttr arr "sum") #[]
  toInt (← call (← getAttr res "item") #[])

#export_python_registry "TestLib"
