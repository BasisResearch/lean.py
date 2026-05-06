Pantograph Kernel
=================

This example demonstrates the full kernel facade: loading Lean environments,
introspecting declarations, running the elaborator, creating goal states, and
applying tactics -- all from Python.

`View source on GitHub <https://github.com/kiranandcode/lean.py/tree/main/examples/02_pantograph_kernel>`_

Lean Side
---------

The Lean file is minimal -- just importing ``LeanPy.Kernel`` is enough to
get the full kernel API surface. All ``leanpy_kernel_*`` functions are
pre-registered upstream:

.. literalinclude:: ../../../examples/02_pantograph_kernel/lean/PantographDemo.lean
   :language: lean
   :caption: examples/02_pantograph_kernel/lean/PantographDemo.lean

Python Side
-----------

The Python script walks through the kernel surface:

.. literalinclude:: ../../../examples/02_pantograph_kernel/python/main.py
   :language: python
   :caption: examples/02_pantograph_kernel/python/main.py

Running
-------

.. code-block:: bash

   cd examples/02_pantograph_kernel
   cd lean && lake build && cd ..
   uv run --project python python/main.py

What the Kernel Can Do
----------------------

**Environment operations:**

.. code-block:: python

   k = Kernel(lib)
   k.load(["Init"])           # load Lean modules
   k.catalog()                # list all declarations
   k.decl_type("Nat.succ")   # "Nat -> Nat"
   k.decl_exists("Nat.add")  # True
   k.module_of("Nat.succ")   # "Init.Prelude"

**Elaboration:**

.. code-block:: python

   k.infer_type("Nat.succ 0")       # "Nat"
   k.parse_type("Nat -> Nat")       # parsed type
   k.decide("1 + 1 = 2")            # "true"

**Goal state and tactics:**

.. code-block:: python

   state = k.goal_create("forall n : Nat, n + 0 = n")
   print(state.n_goals())            # 1
   print(state.pretty())             # "|- ..."

   result = state.try_tactic("intro n")
   print(result.ok)                  # True
   print(result.state.pretty())      # "n : Nat |- n + 0 = n"

**Frontend processing:**

.. code-block:: python

   output = k.process("def foo := 42")
   k.find_source_path("Init")
   state, msg = k.collect_sorrys("def bar : Nat := sorry")
