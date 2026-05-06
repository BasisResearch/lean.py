Typed NumPy
===========

This example shows how Lean's type system can enforce array shape
constraints on numpy operations at compile time. Shape mismatches become
Lean type errors, caught before any Python code runs.

`View source on GitHub <https://github.com/kiranandcode/lean.py/tree/main/examples/03_numpy_typed>`_

Overview
--------

The key idea is **phantom typing**: a Lean ``NDArray`` structure carries dtype
and shape information as type parameters, but the runtime representation is
just a raw numpy array. Lean's type-checker ensures that only shape-compatible
operations are composed, while numpy does the actual computation.

.. code-block:: lean

   structure NDArray (_dt : DType) (_shape : List Nat)

Operations like ``matmul`` require the inner dimensions to agree:

.. code-block:: lean

   def matmul (a : NDArray dt [m, k]) (b : NDArray dt [k, n])
       : IO (NDArray dt [m, n]) := ...

If you write ``matmul a b`` where the shapes don't align, Lean rejects it
at compile time.

Lean Side
---------

``TypedNumpy.lean`` defines the phantom-typed wrappers:

.. literalinclude:: ../../../examples/03_numpy_typed/lean/TypedNumpy.lean
   :language: lean
   :caption: examples/03_numpy_typed/lean/TypedNumpy.lean

``Main.lean`` runs three demo pipelines:

.. literalinclude:: ../../../examples/03_numpy_typed/lean/Main.lean
   :language: lean
   :caption: examples/03_numpy_typed/lean/Main.lean

Running
-------

This example is a pure Lean executable -- Python is just numpy's runtime.
Build and run with:

.. code-block:: bash

   cd examples/03_numpy_typed
   cd lean && lake build && cd ..
   PYTHONPATH=python lean/.lake/build/bin/demo

Key Takeaways
-------------

* Phantom types let Lean enforce invariants on foreign data.
* ``reshape`` carries a compile-time proof obligation (``decide``) that the
  total element count is preserved.
* ``matmul`` requires the inner dimensions to match at the type level.
* The pattern generalises: any Python library whose operations have
  well-defined shape/type contracts can be wrapped this way.
