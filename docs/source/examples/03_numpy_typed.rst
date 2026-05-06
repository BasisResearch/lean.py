Typed NumPy
===========

This example flips the direction: instead of calling Lean from Python,
we call Python from Lean. The result is a numpy wrapper where **array
shapes are checked at compile time by Lean's type system**. Shape
mismatches become type errors before any Python code runs.

`View full source on GitHub <https://github.com/kiranandcode/lean.py/tree/main/examples/03_numpy_typed>`_

The idea
--------

Define a ``structure NDArray (_dt : DType) (_shape : List Nat)`` in Lean.
The ``_dt`` and ``_shape`` parameters are **phantom types** -- they exist
only at the type level. At runtime, the wrapped value is just a raw
numpy array.

.. code-block:: lean

   structure NDArray (_dt : DType) (_shape : List Nat) : Type where
     pyref : Py

Lean's type checker enforces shape contracts. For example, ``matmul``
requires the inner dimensions to agree:

.. code-block:: lean

   def NDArray.matmul {dt} {m k n : Nat}
       (a : NDArray dt [m, k]) (b : NDArray dt [k, n])
       : IO (NDArray dt [m, n]) := ...

If you write ``matmul a b`` where the shapes don't line up, Lean rejects
it at compile time -- you never get a runtime ``ValueError`` from numpy.

Calling into Python
-------------------

Each operation uses the ``LeanPy.Python`` bridge to call numpy. For
example, ``zeros`` constructs an array by calling ``numpy.zeros``:

.. code-block:: lean

   def NDArray.zeros (dt : DType) (shape : List Nat)
       : IO (NDArray dt shape) := do
     let np ← numpy
     let zerosFn ← np.getAttr "zeros"
     let pyShape ← pyShapeOf shape
     let pyDT ← pyDTypeOf dt
     let result ← zerosFn.callKw #[pyShape] #[("dtype", pyDT)]
     return ⟨result⟩

The pattern is always: get a Python function via ``getAttr``, convert
arguments with helpers like ``Py.ofInt64``, call it, and wrap the result.

Reshape with proof obligations
------------------------------

``reshape`` is where it gets interesting. The type signature carries a
proof that the total element count is preserved:

.. code-block:: lean

   def NDArray.reshape {dt} {old : List Nat} (a : NDArray dt old)
       (new : List Nat)
       (_h : shapeSize old = shapeSize new := by decide)
       : IO (NDArray dt new) := ...

For concrete shapes, ``decide`` discharges the proof automatically. But
if the sizes don't match, it fails at compile time:

.. code-block:: lean

   -- This compiles:
   let v ← NDArray.arange .f64 6
   NDArray.reshape v [2, 3]      -- 6 = 2*3 ✓

   -- This doesn't:
   NDArray.reshape v [5]          -- 6 ≠ 5, `decide` fails

A demo pipeline
---------------

``Main.lean`` composes several operations into a pipeline:

.. code-block:: lean

   def runPipeline : IO Unit := do
     let v ← NDArray.arange .f64 6           -- [6]
     let m ← NDArray.reshape v [2, 3]        -- [2, 3]
     let mt ← NDArray.transpose m            -- [3, 2]
     let prod ← NDArray.matmul m mt          -- [2, 2]
     let bias ← NDArray.ones .f64 [2, 2]
     let out ← NDArray.add prod bias
     let flat ← NDArray.reshape out [4]      -- [4]
     let arr ← flat.toArray
     IO.println s!"result: {arr}"

Every intermediate shape is inferred and checked by Lean. The actual
computation happens in numpy.

Running it
----------

This example is a pure Lean executable -- Python is just numpy's runtime:

.. code-block:: bash

   cd examples/03_numpy_typed/lean && lake build && cd ..
   PYTHONPATH=python lean/.lake/build/bin/demo

Output:

.. code-block:: text

   demo_run:
     [4. 4. 4. 4. 4. 4.]

   demo_pipeline -> Array Float of length 4
     #[6.000000, 10.000000, 10.000000, 15.000000]

   demo_explain:
     matmul (3,4) @ (4,5) -> shape inferred by Lean = [3, 5]; numpy says: ...

What to take away
-----------------

* **Phantom types** let Lean enforce invariants on foreign data without
  runtime overhead.
* ``reshape`` carries a **compile-time proof** that element counts match.
* ``matmul`` requires **inner dimensions to agree** at the type level.
* The pattern generalises: any Python library with well-defined shape or
  type contracts (torch, jax, scipy) can be wrapped this way.
