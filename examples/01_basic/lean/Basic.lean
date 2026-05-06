/-
The smallest possible lean-py example: a handful of functions, one
inductive, one structure, and a #export_python_registry at the bottom.

Build with `lake build`, then load from Python with `LeanLibrary`.
-/
import LeanPy

open LeanPy

@[python "py_increment"]
def increment (x : Int) : Int := x + 1

@[python "py_greet"]
def greet (name : String) : IO String :=
  return s!"Hello, {name}!"

@[python "py_sum_array"]
def sumArray (xs : Array Int) : Int :=
  xs.foldl (· + ·) 0

structure Point where
  x : Int
  y : Int
  deriving Repr

derive_python Point

@[python "py_origin"]
def origin (_ : Unit) : Point := ⟨0, 0⟩

@[python "py_norm_sq"]
def normSq (p : Point) : Int := p.x * p.x + p.y * p.y

inductive Shape where
  | circle (r : Int)
  | square (side : Int)
  | rect   (w h : Int)
  deriving Repr

derive_python Shape

@[python "py_perimeter"]
def perimeter (s : Shape) : Int :=
  match s with
  | .circle r => 6 * r
  | .square s => 4 * s
  | .rect w h => 2 * (w + h)

#export_python_registry "Basic"
