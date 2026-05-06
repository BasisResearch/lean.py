/-
Phantom-typed wrappers around `numpy.ndarray`.

This example is mostly about Python-from-Lean: a Lean library writes a
small, well-typed surface over `numpy` whose dtype and shape are
phantom parameters at the type level. Compile-time the shape calculus
is the Lean type checker; runtime the actual storage and arithmetic
are forwarded to numpy via the `LeanPy.Python` bridge. Python's only
job is to load the library and call a couple of demo entry points to
print results.

```lean
def NDArray.matmul {dt} {m k n : Nat}
    (a : NDArray dt [m, k]) (b : NDArray dt [k, n]) : IO (NDArray dt [m, n])
```

The signature alone enforces the inner-dimension contraction, the
outer dimensions, and the shared dtype. A caller who tries to multiply
incompatible shapes or mismatched dtypes gets a Lean type error.
-/
import LeanPy
import LeanPy.Python

open LeanPy LeanPy.Python

namespace TypedNumpy

/-! ### dtype as a tag at the type level -/

inductive DType where
  | f32 | f64 | i32 | i64
  deriving Repr, BEq

def DType.numpyName : DType → String
  | .f32 => "float32"
  | .f64 => "float64"
  | .i32 => "int32"
  | .i64 => "int64"

/-! ### `NDArray dt shape`: a phantom-typed wrapper around a numpy array -/

/-- A numpy array carrying its dtype and shape as phantom indices.
The wrapped `Py` is the actual `numpy.ndarray`; Lean sees only the
opaque handle, so all operations consult the type indices for their
shape contracts. -/
structure NDArray (_dt : DType) (_shape : List Nat) : Type where
  pyref : Py

/-- Total element count of a shape. Used as the reshape proof obligation. -/
def shapeSize : List Nat → Nat
  | [] => 1
  | n :: ns => n * shapeSize ns

/-! ### Bridge helpers -/

private def numpy : IO Py := do
  init ()
  import_ "numpy"

private def pyShapeOf (shape : List Nat) : IO Py := do
  let arr ← shape.toArray.mapM (fun n => Py.ofInt64 (Int.ofNat n))
  Py.ofTuple arr

private def pyDTypeOf (dt : DType) : IO Py := do
  let np ← numpy
  np.getAttr dt.numpyName

/-! ### Constructors -/

/-- `numpy.zeros(shape, dtype=dt)`. The result type pins both. -/
def NDArray.zeros (dt : DType) (shape : List Nat) : IO (NDArray dt shape) := do
  let np ← numpy
  let zerosFn ← np.getAttr "zeros"
  let pyShape ← pyShapeOf shape
  let pyDT ← pyDTypeOf dt
  let result ← zerosFn.callKw #[pyShape] #[("dtype", pyDT)]
  return ⟨result⟩

/-- `numpy.ones(shape, dtype=dt)`. -/
def NDArray.ones (dt : DType) (shape : List Nat) : IO (NDArray dt shape) := do
  let np ← numpy
  let onesFn ← np.getAttr "ones"
  let pyShape ← pyShapeOf shape
  let pyDT ← pyDTypeOf dt
  let result ← onesFn.callKw #[pyShape] #[("dtype", pyDT)]
  return ⟨result⟩

/-- `numpy.arange(0, n, dtype=dt)`. The result is a 1-D array of length `n`. -/
def NDArray.arange (dt : DType) (n : Nat) : IO (NDArray dt [n]) := do
  let np ← numpy
  let arangeFn ← np.getAttr "arange"
  let stop ← Py.ofInt64 (Int.ofNat n)
  let pyDT ← pyDTypeOf dt
  let result ← arangeFn.callKw #[stop] #[("dtype", pyDT)]
  return ⟨result⟩

/-! ### Operations — typed against the phantom shape -/

/-- Matrix multiplication. Inner dimensions must agree, dtypes must match,
and the result shape is computed at the type level. -/
def NDArray.matmul {dt : DType} {m k n : Nat}
    (a : NDArray dt [m, k]) (b : NDArray dt [k, n]) :
    IO (NDArray dt [m, n]) := do
  let np ← numpy
  let matmulFn ← np.getAttr "matmul"
  let result ← matmulFn.call #[a.pyref, b.pyref]
  return ⟨result⟩

/-- Element-wise sum. Same dtype, same shape — the type checker enforces both. -/
def NDArray.add {dt : DType} {shape : List Nat}
    (a b : NDArray dt shape) : IO (NDArray dt shape) := do
  let result ← a.pyref.add b.pyref
  return ⟨result⟩

/-- Element-wise product. Same dtype, same shape. -/
def NDArray.mul {dt : DType} {shape : List Nat}
    (a b : NDArray dt shape) : IO (NDArray dt shape) := do
  let result ← a.pyref.mul b.pyref
  return ⟨result⟩

/-- Transpose a 2-D array. Output shape is the swap. -/
def NDArray.transpose {dt : DType} {m n : Nat}
    (a : NDArray dt [m, n]) : IO (NDArray dt [n, m]) := do
  let result ← a.pyref.getAttr "T"
  return ⟨result⟩

/-- Reshape, with a proof obligation that total element count is preserved.
For closed shapes the obligation is discharged by `decide`. -/
def NDArray.reshape {dt : DType} {old : List Nat} (a : NDArray dt old)
    (new : List Nat) (_h : shapeSize old = shapeSize new := by decide) :
    IO (NDArray dt new) := do
  let np ← numpy
  let reshapeFn ← np.getAttr "reshape"
  let pyShape ← pyShapeOf new
  let result ← reshapeFn.call #[a.pyref, pyShape]
  return ⟨result⟩

/-- Render the underlying numpy array. -/
def NDArray.repr {dt : DType} {shape : List Nat}
    (a : NDArray dt shape) : IO String :=
  a.pyref.repr

/-- Read out a 1-D float64 array as `Array Float`. Useful in tests. -/
def NDArray.toArray {n : Nat} (a : NDArray .f64 [n]) : IO (Array Float) := do
  let pyList ← a.pyref.callMethod "tolist" #[]
  let len ← pyList.length
  let mut acc : Array Float := Array.mkEmpty len.toNat
  for i in [:len.toNat] do
    let idx ← Py.ofInt64 (Int.ofNat i)
    let item ← pyList.getItem idx
    acc := acc.push (← item.toFloat)
  return acc

end TypedNumpy

/-!
The driver lives in `Main.lean` (`def main : IO Unit`). Build with
`lake build` and run the resulting `./.lake/build/bin/demo`.

The following compile-time errors illustrate what the typing buys you.
Uncomment any line to see the type checker reject it:

```lean
-- inner dimensions disagree:
example : IO _ := do
  let a ← NDArray.ones .f64 [3, 4]
  let b ← NDArray.ones .f64 [5, 2]
  NDArray.matmul a b   -- expected NDArray .f64 [4, _], got [5, _]

-- dtypes disagree:
example : IO _ := do
  let a ← NDArray.ones .f32 [3, 4]
  let b ← NDArray.ones .f64 [4, 2]
  NDArray.matmul a b   -- expected NDArray .f32 [4, _], got .f64

-- reshape with wrong total size:
example : IO _ := do
  let v ← NDArray.arange .f64 6
  NDArray.reshape v [5]   -- shapeSize [6] ≠ shapeSize [5]
```
-/
