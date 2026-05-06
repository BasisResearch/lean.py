SymPy Tactic
============

This example implements ``by sympy`` -- a real Lean tactic that closes
arithmetic goals by delegating to SymPy. When Lean sees a goal like
``(1 : Int) + 1 = 2``, it sends the entire ``Lean.Expr`` tree to Python,
SymPy verifies it, and the goal is closed.

`View full source on GitHub <https://github.com/kiranandcode/lean.py/tree/main/examples/04_sympy_tactic>`_

The architecture
----------------

The data flow looks like this:

1. The ``sympy`` tactic extracts the goal's type as a ``Lean.Expr``.
2. ``Py.ofLeanObj`` wraps the expression and sends it to Python.
3. On the Python side, ``derive_python`` for ``Lean.Expr`` (registered in
   ``LeanPy/Reflect.lean``) means the expression arrives as a fully-typed
   ``LeanInductiveValue`` tree.
4. A recursive converter walks the tree and builds the equivalent SymPy
   expression.
5. ``sympy.simplify`` checks whether the proposition holds.
6. If SymPy accepts, the tactic closes the goal with an oracle axiom.

The oracle axiom
----------------

The soundness story is explicit: an axiom declares that anything SymPy
accepts is true:

.. code-block:: lean

   axiom sympy_oracle (p : Prop) : p

This is the **only** point of unsoundness. If SymPy is wrong about
something, this axiom is where the blame falls. In practice, SymPy is
reliable for the arithmetic fragment.

The Lean tactic
---------------

The tactic itself is small. It gets the goal type, sends it to Python,
and assigns the oracle proof if accepted:

.. code-block:: lean

   @[python "sympy_expr_check_prop"]
   def sympyExprCheckProp (e : Lean.Expr) : IO Bool := do
     init ()
     let handle ← Py.ofLeanObj e
     let mod ← import_ "lean_to_sympy"
     let checkFn ← mod.getAttr "decode_and_check_prop"
     (← checkFn.call #[handle]).toBool

   syntax (name := sympyTac) "sympy" : tactic

   @[tactic sympyTac]
   def evalSympy : Tactic := fun stx =>
     match stx with
     | `(tactic| sympy) => do
       let goal ← getMainGoal
       let goalType ← goal.getType
       let accepted ← sympyExprCheckProp goalType
       if !accepted then
         throwError "sympy: oracle rejected the goal"
       let proof ← Meta.mkAppOptM ``sympy_oracle #[goalType]
       goal.assign proof
     | _ => throwUnsupportedSyntax

The key line is ``Py.ofLeanObj e`` -- this takes a Lean ``Expr`` and
makes it available to Python as a ``LeanInductiveValue`` tree, thanks to
the ``derive_python`` registrations for ``Lean.Expr``, ``Lean.Name``, etc.

Converting Expr to SymPy
-------------------------

The Python side walks the ``LeanInductiveValue`` tree recursively.
A ``Lean.Name`` like ``HAdd.hAdd`` gets pattern-matched and mapped to
SymPy's ``+`` operator. Here's the core dispatch:

.. code-block:: python

   _DISPATCH = {
       "HAdd.hAdd": _binop(lambda a, b: a + b),
       "HSub.hSub": _binop(lambda a, b: a - b),
       "HMul.hMul": _binop(lambda a, b: a * b),
       "HDiv.hDiv": _binop(lambda a, b: a / b),
       "HPow.hPow": _binop(lambda a, b: a ** b),
       "Eq":        (2, lambda args: Eq(expr_to_sympy(args[-2]),
                                        expr_to_sympy(args[-1]))),
       "Neg.neg":   _unop(lambda x: -x),
       "Nat.succ":  (1, lambda args: expr_to_sympy(args[-1]) + 1),
       "Int.ofNat": (1, lambda args: expr_to_sympy(args[-1])),
       ...
   }

The main converter handles literals, variables, ``mdata`` (unwrapped
transparently), and application nodes (uncurried and dispatched):

.. code-block:: python

   def expr_to_sympy(expr):
       if expr.ctor == "lit":
           return Integer(expr.fields[0].fields[0])
       if expr.ctor == "app":
           head, args = uncurry_app(expr)
           entry = _DISPATCH.get(name_to_str(head.fields[0]))
           if entry:
               _, builder = entry
               return builder(args)
       ...

The proposition checker just simplifies and checks:

.. code-block:: python

   def sympy_prop_check(prop):
       return simplify(prop) is sympy.true

Using the tactic
----------------

With everything in place, proofs look like this:

.. code-block:: lean

   import SymPyTactic

   example : (1 : Int) + 1 = 2 := by sympy
   example : (3 : Int) * 4 = 12 := by sympy
   example : (5 : Int) * 6 = 30 := by sympy

Running
-------

.. code-block:: bash

   cd examples/04_sympy_tactic
   cd lean && lake build && cd ..
   uv run --project python python/main.py

What to take away
-----------------

* ``Py.ofLeanObj`` bridges Lean's kernel AST into Python as structured data.
* ``derive_python`` for ``Lean.Expr`` / ``Lean.Name`` makes pattern-matching
  on Lean's internal representation possible from Python.
* The dispatch table pattern is **extensible** -- add entries to support
  more operations.
* The oracle axiom makes the trust boundary **explicit**.
* This architecture generalises: any decision procedure available from
  Python (Z3, CAS systems, ML models) can back a Lean tactic this way.
