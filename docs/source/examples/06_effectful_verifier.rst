Effectful Refinement-Type Verifier
===================================

This example combines two libraries to build a **refinement-type
verifier** entirely in Python: `effectful <https://github.com/BasisResearch/effectful>`_'s
algebraic effects provide symbolic arithmetic, and lean-py's kernel
facade sends the resulting propositions to Lean's ``omega`` tactic for
formal verification.

The user writes plain Python functions with ``Annotated[int, Gt(0)]``
type hints. The system extracts verification conditions, builds them as
``Lean.Expr`` trees, and proves (or disproves) them automatically.

`View full source on GitHub <https://github.com/BasisResearch/lean.py/tree/main/examples/06_effectful_verifier>`_

The idea
--------

Consider this Python function:

.. code-block:: python

   def positive_increment(x: Annotated[int, Gt(0)]):
       y = x + 3
       assert_refined(y, Gt(3))

The annotation ``Gt(0)`` says *x is greater than 0*. The assertion claims
*y = x + 3 is greater than 3*. The system should verify that the
precondition implies the postcondition — i.e., prove the proposition:

.. math::

   \forall\, x : \mathbb{Z},\; x > 0 \;\Rightarrow\; x + 3 > 3

The pipeline has four stages:

1. **Inspect** the function's type annotations to extract preconditions.
2. **Execute symbolically** using effectful to collect verification
   conditions as ``Term`` trees.
3. **Convert** each ``Term`` to a fully-elaborated ``Lean.Expr`` tree.
4. **Verify** by sending the ``Lean.Expr`` to Lean's kernel via
   ``goalFromExpr`` + ``omega``.

The Lean side
-------------

The Lean project is minimal — one file that defines a single
``@[python]`` function:

.. code-block:: lean

   import LeanPy
   import LeanPy.Kernel

   @[python "effectful_goal_from_expr"]
   def goalFromExpr (e : Lean.Expr) : IO GoalState := do
     match (← LeanPy.Kernel.envRef.get) with
     | none => throw (IO.userError "no environment loaded")
     | some env =>
       let ctx ← freshCoreContext
       let cs : Core.State := { env }
       let inner : CoreM GoalState :=
         Meta.MetaM.run' do
           Term.TermElabM.run' do
             Meta.check e
             GoalState.create e
       let (gs, _) ← inner.toIO ctx cs
       return gs

Unlike ``goalCreate`` (which takes a string), ``goalFromExpr`` takes a
``Lean.Expr`` directly. The expression is built on the Python side as a
``LeanInductiveValue`` tree and marshalled across the FFI — lean-py
handles the conversion automatically via ``derive_python Lean.Expr``.

Refinement annotations
----------------------

The DSL uses Python's ``Annotated`` type hints with two refinement
classes:

.. code-block:: python

   from typing import Annotated

   class Gt:
       """Refinement: value > n."""
       def __init__(self, n: int):
           self.n = n

   class Ge:
       """Refinement: value >= n."""
       def __init__(self, n: int):
           self.n = n

Preconditions come from parameter annotations:

.. code-block:: python

   def f(x: Annotated[int, Gt(0)], y: Annotated[int, Ge(1)]):
       ...

Postconditions are stated with ``assert_refined``, an effectful
operation:

.. code-block:: python

   @defop
   def assert_refined(value: int, refinement) -> None:
       pass  # no-op in concrete mode; intercepted during symbolic execution

Symbolic execution with effectful
----------------------------------

effectful's ``defdata.dispatch(int)`` overloads Python arithmetic
operators (``+``, ``-``, ``*``, ``>``, ``>=``, etc.) to build symbolic
``Term[int]`` and ``Term[bool]`` trees instead of computing values.

For each parameter, we create a symbolic variable:

.. code-block:: python

   from effectful.ops.syntax import defdata, defop
   from effectful.ops.semantics import handler, evaluate

   # Symbolic variable for parameter "x"
   x_op = defop(int, name="x")

   # x_op() returns a Term; x_op() + 3 returns a Term tree
   symbolic_y = x_op() + 3

During symbolic execution, an effectful ``handler`` intercepts
``assert_refined`` calls and collects the verification conditions:

.. code-block:: python

   vc_terms = []

   def handle_assert(value, refinement):
       if isinstance(refinement, Gt):
           vc_terms.append(value > refinement.n)

   with handler({assert_refined: handle_assert}):
       fn(**{name: var_ops[name]() for name in params})

After execution, ``vc_terms`` contains symbolic ``Term[bool]`` trees
like ``x_op() + 3 > 3``.

Building Lean.Expr trees
-------------------------

Each verification condition must become a fully-elaborated ``Lean.Expr``
— the internal representation Lean uses for propositions. The
``ExprBuilder`` class constructs these as ``LeanInductiveValue`` trees:

.. code-block:: python

   eb = ExprBuilder(lib)

   # ∀ (x : Int), ...
   eb.mk_forall("x", eb.INT, body)

   # x + 3  (fully elaborated with type classes)
   eb.mk_int_add(eb.mk_bvar(0), eb.mk_int(3))

   # x + 3 > 3
   eb.mk_int_gt(eb.mk_int_add(eb.mk_bvar(0), eb.mk_int(3)), eb.mk_int(3))

The expressions must be *fully elaborated* — every type class instance
is explicit. For example, ``x + 3`` in Lean notation becomes:

.. code-block:: text

   @HAdd.hAdd Int Int Int (@instHAdd Int Int.instAdd) x 3

The builder handles this automatically with helpers like ``mk_int_add``.

De Bruijn indices
^^^^^^^^^^^^^^^^^

Lean uses de Bruijn indices for bound variables. In
``∀ (x : Int), x > 0 → x + 3 > 3``:

- The outer ``∀`` binds ``x``. In the precondition body, ``x = bvar 0``.
- The ``→`` is itself a ``∀ _ : (x > 0), ...``. In the conclusion,
  ``x = bvar 1`` (one more binder above).

The code rebuilds the ``handler`` at each binder depth so the de Bruijn
indices are always correct.

Converting Terms to Exprs with handlers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

effectful's ``handler`` + ``evaluate`` mechanism converts the symbolic
``Term`` trees into ``Lean.Expr`` trees. We define a handler that maps
each arithmetic/comparison operation to the corresponding ``ExprBuilder``
method:

.. code-block:: python

   int_ops = defdata.dispatch(int)

   expr_handler = {
       int_ops.__add__: lambda a, b: eb.mk_int_add(coerce(a), coerce(b)),
       int_ops.__gt__:  lambda a, b: eb.mk_int_gt(coerce(a), coerce(b)),
       x_op:           lambda: eb.mk_bvar(depth - 1 - i),
       # ... etc
   }

   with handler(expr_handler):
       lean_body = evaluate(vc_term)

The same ``Term`` tree can be evaluated with a *string handler* to
produce a human-readable description like
``∀ (x : Int), (x > 0) → ((x + 3) > 3)``.

Verification via omega
----------------------

The final step sends the ``Lean.Expr`` to Lean's kernel:

.. code-block:: python

   gs_handle = lib.effectful_goal_from_expr(lean_expr)
   gs = GoalState(kernel, gs_handle)
   result = gs.try_tactic("intros; simp [Int.ofNat] at *; omega")
   verified = result.ok and result.state.is_solved()

The tactic sequence:

1. ``intros`` — introduces all universally quantified variables and
   hypotheses into the context.
2. ``simp [Int.ofNat] at *`` — normalises ``Int.ofNat n`` to ``↑n`` so
   ``omega`` can handle the literals.
3. ``omega`` — decides the resulting linear arithmetic goal.

The demo
--------

Three programs demonstrate the system:

.. code-block:: python

   def positive_increment(x: Annotated[int, Gt(0)]):
       y = x + 3
       assert_refined(y, Gt(3))
       z = x + 10
       assert_refined(z, Gt(10))

   def bounded_sum(x: Annotated[int, Gt(0)], y: Annotated[int, Gt(0)]):
       s = x + y
       assert_refined(s, Gt(1))
       assert_refined(s, Ge(2))

   def failing(x: Annotated[int, Gt(0)]):
       y = x + 1
       assert_refined(y, Gt(10))

Running it:

.. code-block:: bash

   cd examples/06_effectful_verifier
   cd lean && lake build && cd ..
   uv run --project python python/main.py

Output:

.. code-block:: text

   === positive_increment ===
     VERIFIED: ∀ (x : Int), (x > 0) → ((x + 3) > 3)
     VERIFIED: ∀ (x : Int), (x > 0) → ((x + 10) > 10)

   === bounded_sum ===
     VERIFIED: ∀ (x : Int) (y : Int), (x > 0) → (y > 0) → ((x + y) > 1)
     VERIFIED: ∀ (x : Int) (y : Int), (x > 0) → (y > 0) → ((x + y) >= 2)

   === failing ===
     FAILED: ∀ (x : Int), (x > 0) → ((x + 1) > 10)

The first two programs are fully verified. The third is correctly
rejected — ``x > 0`` does not imply ``x + 1 > 10``.

What to take away
-----------------

- **Symbolic execution via algebraic effects**: effectful's ``defdata``
  and ``defop`` let you overload Python operators to build term trees
  with zero custom AST code.

- **Lean.Expr as data**: lean-py's bidirectional marshalling lets Python
  construct ``Lean.Expr`` trees as ``LeanInductiveValue`` objects and
  pass them directly to Lean's kernel — no string parsing needed.

- **Handler-based interpretation**: the same symbolic ``Term`` tree can
  be interpreted in multiple ways (``Lean.Expr`` for verification, string
  for display) by swapping the effectful handler.

- **Formal verification from Python**: the combination gives Python
  programs access to Lean's proof engine. The ``omega`` tactic decides
  linear arithmetic, but any Lean tactic is available.
