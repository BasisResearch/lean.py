Knuckledragger / Z3 Tactic
==========================

Same pattern as the :doc:`04_sympy_tactic` example, but using
`Z3 <https://github.com/Z3Prover/z3>`_ (via
`Knuckledragger <https://github.com/philzook58/knuckledragger>`_)
as the oracle backend. When Lean encounters ``by knuckle``, the goal is
converted to a Z3 expression and discharged by the SMT solver.

`View source on GitHub <https://github.com/kiranandcode/lean.py/tree/main/examples/05_knuckledragger>`_

How It Works
------------

1. The ``knuckle`` tactic extracts the goal's ``Lean.Expr``.
2. ``Py.ofLeanObj`` wraps the expression and sends it to Python.
3. ``expr_to_z3`` walks the ``Lean.Expr`` ADT and builds a Z3 expression.
4. Z3's solver checks validity (or Knuckledragger's ``lemma`` wrapper if
   installed).
5. If proven, the tactic closes the goal with an oracle axiom.

Lean Side
---------

.. literalinclude:: ../../../examples/05_knuckledragger/lean/KnuckleTactic.lean
   :language: lean
   :caption: examples/05_knuckledragger/lean/KnuckleTactic.lean

Demo proofs:

.. literalinclude:: ../../../examples/05_knuckledragger/lean/Demo.lean
   :language: lean
   :caption: examples/05_knuckledragger/lean/Demo.lean

Python Side
-----------

.. literalinclude:: ../../../examples/05_knuckledragger/python/lean_to_z3.py
   :language: python
   :caption: examples/05_knuckledragger/python/lean_to_z3.py

Running
-------

.. code-block:: bash

   cd examples/05_knuckledragger
   uv pip install z3-solver
   cd lean && lake build && cd ..
   uv run --project python python/main.py

Optionally install Knuckledragger for its higher-level interface:

.. code-block:: bash

   uv add --project python kdrag

Key Takeaways
-------------

* The SymPy and Z3 tactics share the same architecture: Lean sends
  ``Lean.Expr`` trees to Python, Python converts and checks, Lean closes
  the goal with an oracle.
* Z3 can handle more complex propositions (quantified formulas, integer
  arithmetic) than SymPy's ``simplify``.
* The ``check_prop`` function falls back to raw Z3 if Knuckledragger is
  not installed, making the dependency optional.
* This pattern generalises to any decision procedure available from Python.
