Z3 / Knuckledragger Tactic
==========================

This example follows the same architecture as the :doc:`04_sympy_tactic`
example, but swaps the backend: instead of SymPy, the oracle is
`Z3 <https://github.com/Z3Prover/z3>`_ (optionally wrapped by
`Knuckledragger <https://github.com/philzook58/knuckledragger>`_). Z3 is
an SMT solver, so it can handle a richer fragment -- quantified formulas,
integer arithmetic, and more.

`View full source on GitHub <https://github.com/kiranandcode/lean.py/tree/main/examples/05_knuckledragger>`_

Same architecture, different solver
------------------------------------

The Lean side is structurally identical to the SymPy tactic:

.. code-block:: lean

   axiom knuckle_oracle (p : Prop) : p

   @[python "knuckle_expr_check_prop"]
   def knuckleExprCheckProp (e : Lean.Expr) : IO Bool := do
     init ()
     let handle ← Py.ofLeanObj e
     let mod ← import_ "lean_to_z3"
     let checkFn ← mod.getAttr "decode_and_check_prop"
     (← checkFn.call #[handle]).toBool

   syntax (name := knuckleTac) "knuckle" : tactic

The tactic gets the goal, sends the ``Lean.Expr`` to Python, and closes
the goal if Z3 says it's valid.

Converting Expr to Z3
----------------------

The Python converter mirrors the SymPy version but targets Z3 expressions.
Lean names like ``HAdd.hAdd`` map to Z3 arithmetic:

.. code-block:: python

   _DISPATCH = {
       "HAdd.hAdd": _binop(lambda a, b: a + b),
       "HSub.hSub": _binop(lambda a, b: a - b),
       "HMul.hMul": _binop(lambda a, b: a * b),
       "Eq":        (2, lambda args: expr_to_z3(args[-2])
                                     == expr_to_z3(args[-1])),
       ...
   }

Z3 variables are created on demand:

.. code-block:: python

   _VAR_CACHE: dict[str, z3.ArithRef] = {}

   def _get_var(name: str) -> z3.ArithRef:
       if name not in _VAR_CACHE:
           _VAR_CACHE[name] = z3.Int(name)
       return _VAR_CACHE[name]

The converter also handles ``ForAll`` expressions, which SymPy's version
cannot:

.. code-block:: python

   if ctor == "forallE":
       binder_name = name_to_str(expr.fields[0])
       body = expr.fields[2]
       var = z3.Int(binder_name)
       return z3.ForAll([var], expr_to_z3(body, bound=[var] + bound))

Checking with Z3
-----------------

The proposition checker uses Z3's solver. If Knuckledragger is installed,
it uses the higher-level ``lemma`` wrapper; otherwise raw Z3:

.. code-block:: python

   def z3_proves(prop) -> bool:
       s = z3.Solver()
       s.add(z3.Not(prop))
       return s.check() == z3.unsat

   def check_prop(prop) -> bool:
       if HAS_KDR:
           try:
               kd.lemma(prop)
               return True
           except Exception:
               return False
       return z3_proves(prop)

Using the tactic
----------------

.. code-block:: lean

   import KnuckleTactic

   example : (1 : Int) + 1 = 2 := by knuckle
   example : (3 : Int) * 4 = 12 := by knuckle
   example : (5 : Int) * 6 = 30 := by knuckle

Running
-------

.. code-block:: bash

   cd examples/05_knuckledragger
   cd lean && lake build && cd ..
   uv pip install z3-solver
   uv run --project python python/main.py

Optionally add Knuckledragger for its higher-level interface:

.. code-block:: bash

   uv add --project python kdrag

Comparing SymPy and Z3
-----------------------

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * -
     - SymPy tactic
     - Z3 tactic
   * - Backend
     - CAS (symbolic algebra)
     - SMT solver
   * - Strengths
     - Simplification, calculus
     - Quantifiers, satisfiability
   * - ``ForAll`` support
     - No
     - Yes
   * - Dependency
     - ``sympy``
     - ``z3-solver``

Both share the same architecture: Lean sends ``Lean.Expr`` to Python,
Python converts and checks, Lean closes the goal with an oracle. The only
difference is what happens inside the converter and checker.

What to take away
-----------------

* The tactic architecture **generalises**: swap the converter and checker,
  and you can back a Lean tactic with any Python-accessible decision
  procedure.
* Z3 handles **richer formulas** (quantifiers, SMT theories) than SymPy.
* Knuckledragger is **optional** -- the tactic falls back to raw Z3 if
  it's not installed.
