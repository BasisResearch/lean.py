SymPy Tactic
============

This example implements a real Lean tactic (``by sympy``) that delegates to
SymPy. When Lean encounters a goal like ``1 + 1 = 2``, it sends the
``Lean.Expr`` tree to Python, where SymPy simplifies and verifies it.

`View source on GitHub <https://github.com/kiranandcode/lean.py/tree/main/examples/04_sympy_tactic>`_

How It Works
------------

1. The ``sympy`` tactic extracts the main goal's type as a ``Lean.Expr``.
2. It wraps the expression with ``Py.ofLeanObj`` and calls a Python function.
3. On the Python side, a recursive ``expr_to_sympy`` function walks the
   ``Lean.Expr`` ADT (available thanks to ``derive_python``) and builds the
   equivalent SymPy expression.
4. SymPy's ``simplify`` checks whether the expression holds.
5. If SymPy accepts, the tactic closes the goal using an oracle axiom.

Lean Side
---------

.. literalinclude:: ../../../examples/04_sympy_tactic/lean/SymPyTactic.lean
   :language: lean
   :caption: examples/04_sympy_tactic/lean/SymPyTactic.lean

Demo proofs using the tactic:

.. literalinclude:: ../../../examples/04_sympy_tactic/lean/Demo.lean
   :language: lean
   :caption: examples/04_sympy_tactic/lean/Demo.lean

Python Side
-----------

The ``lean_to_sympy`` module converts Lean expression trees to SymPy:

.. literalinclude:: ../../../examples/04_sympy_tactic/python/lean_to_sympy.py
   :language: python
   :caption: examples/04_sympy_tactic/python/lean_to_sympy.py

Running
-------

.. code-block:: bash

   cd examples/04_sympy_tactic
   uv pip install sympy
   cd lean && lake build && cd ..
   uv run --project python python/main.py

Key Takeaways
-------------

* ``Py.ofLeanObj`` converts a Lean value into a Python-accessible handle.
* ``derive_python`` for ``Lean.Expr``, ``Lean.Name``, etc. makes it possible
  to pattern-match on Lean's kernel AST from Python.
* The dispatch table pattern (mapping Lean operator names to SymPy builders)
  is extensible -- add entries to support more operations.
* The oracle axiom pattern keeps the tactic sound within Lean's logic: if
  SymPy is wrong, the axiom is the only point of unsoundness.
