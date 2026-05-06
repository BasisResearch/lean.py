/-
Example Lean library that exposes a few definitions to Python.

Building with `lake build` produces a shared library; the Python side
loads it via `LeanPy.Library`.
-/
import LeanPy
import LeanPy.Kernel

open LeanPy

/-- A simple int → int function. -/
@[python "py_bar"]
def bar (x : Int) : Int := x + 1

/-- An IO function. -/
@[python "py_foo"]
def foo (x : Int) : IO Int := do
  IO.println s!"foo({x})"
  return x + 1

/-- A function taking a string. -/
@[python "py_greet"]
def greet (name : String) : IO String := do
  return s!"Hello, {name}!"

/-- An Array argument. -/
@[python "py_sum_list"]
def sumList (xs : Array Int) : Int :=
  xs.foldl (· + ·) 0

/-- A simple inductive — derive Python wrappers. -/
inductive Color where
  | red | green | blue
  deriving Repr

derive_python Color

/-- A structure. -/
structure Point where
  x : Int
  y : Int
  deriving Repr

derive_python Point

/-- Sum-type with payload. -/
inductive Shape where
  | circle (r : Int)
  | square (side : Int)
  | rect   (w h : Int)
  deriving Repr

derive_python Shape

/-- Function that returns a derived type. -/
@[python "py_origin"]
def origin (_ : Unit) : Point := ⟨0, 0⟩

/-- Function that consumes a derived type. -/
@[python "py_point_norm_sq"]
def pointNormSq (p : Point) : Int := p.x * p.x + p.y * p.y

/-- Function returning an inductive with a payload. -/
@[python "py_make_circle"]
def mkCircle (r : Int) : Shape := .circle r

/-- Function pattern-matching on an inductive. -/
@[python "py_shape_perimeter"]
def shapePerimeter (s : Shape) : Int :=
  match s with
  | .circle r   => 6 * r        -- approx 2 π r
  | .square s   => 4 * s
  | .rect w h   => 2 * (w + h)

/-- Sum through a Lean Array of derived ints. -/
@[python "py_color_id"]
def colorId (c : Color) : Int :=
  match c with
  | .red => 0
  | .green => 1
  | .blue => 2

/-! ### Python-in-Lean: simple smoke tests using `LeanPy.Python` -/

open LeanPy.Python in
@[python "py_python_eval_int"]
def pythonEvalInt (src : String) : IO Int := do
  init ()
  let r ← eval src
  toInt r

open LeanPy.Python in
@[python "py_python_eval_str"]
def pythonEvalStr (src : String) : IO String := do
  init ()
  let r ← eval src
  str r

open LeanPy.Python in
/-- Import a Python module, look up an attribute, call it as a function with
one int arg, and return its int result. Used to demonstrate end-to-end
Python interop from Lean. -/
@[python "py_python_call1_int"]
def pythonCall1Int (mod : String) (fn : String) (arg : Int) : IO Int := do
  init ()
  let m ← import_ mod
  let f ← getAttr m fn
  let a ← ofInt64 arg
  let r ← call f #[a]
  toInt r

/-! ### SymPy demo: simplify a symbolic expression -/

open LeanPy.Python in
@[python "py_sympy_simplify"]
def sympySimplify (expr : String) : IO String := do
  init ()
  let sympy ← import_ "sympy"
  let simplify ← getAttr sympy "simplify"
  let e ← ofString expr
  let r ← call simplify #[e]
  str r

/-! ### NumPy demo: sum an Array of Ints by passing through NumPy -/

open LeanPy.Python in
@[python "py_numpy_sum"]
def numpySum (xs : Array Int) : IO Int := do
  init ()
  let np ← import_ "numpy"
  let arrayFn ← getAttr np "array"
  -- Build a Python list from xs.
  let mut pylist : Array LeanPy.Python.Py := #[]
  for x in xs do
    pylist := pylist.push (← ofInt64 x)
  let lst ← ofList pylist
  let arr ← call arrayFn #[lst]
  let sumFn ← getAttr arr "sum"
  let res ← call sumFn #[]
  toInt (← call (← getAttr res "item") #[])

#export_python_registry "PyleanExample"
