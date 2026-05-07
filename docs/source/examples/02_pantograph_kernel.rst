Pantograph Kernel
=================

lean-py ships a high-level ``Kernel`` class that gives Python direct access
to Lean's type-checker, elaborator, and tactic engine. No custom Lean
project is needed -- any library that imports ``LeanPy.Kernel`` already
has the full API surface.

`View full source on GitHub <https://github.com/BasisResearch/lean.py/tree/main/examples/02_pantograph_kernel>`_

Setting up
----------

The ``Kernel`` wraps a ``LeanLibrary``. The library just needs to import
``LeanPy.Kernel`` and call ``#export_python_registry``:

.. code-block:: lean

   import LeanPy
   import LeanPy.Kernel
   #export_python_registry "PantographDemo"

That single file is the entire Lean side. All ~30 kernel functions are
pre-registered in ``LeanPy.Kernel`` upstream.

On the Python side:

.. code-block:: python

   from lean_py import LeanLibrary
   from lean_py.kernel import Kernel

   lib = LeanLibrary.from_lake("path/to/lean", "PantographDemo", build=True)
   k = Kernel(lib)

Loading an environment
----------------------

Before you can do anything, load one or more Lean modules into the kernel:

.. code-block:: python

   >>> k.init_search("")
   >>> k.load(["Init"])
   >>> k.is_loaded()
   True
   >>> k.decl_count()
   8947

This loads the full ``Init`` library -- all of Lean's built-in types,
tactics, and notation.

Introspecting declarations
--------------------------

Once the environment is loaded, you can query any declaration:

.. code-block:: python

   >>> k.decl_exists("Nat.succ")
   True

   >>> k.decl_type("Nat.succ")
   'Nat → Nat'

   >>> k.module_of("Nat.succ")
   'Init.Prelude'

``catalog()`` returns all declaration names, ``search("add")`` filters by
substring.

Running the elaborator
----------------------

The kernel can elaborate expressions, compute weak-head normal forms,
and decide propositions:

.. code-block:: python

   >>> k.infer_type("Nat.succ Nat.zero")
   'Nat'

   >>> k.whnf("(fun x => x + 1) 4")
   '5'

   >>> k.decide("1 + 1 = 2")
   'true'

   >>> k.decide("3 < 2")
   'false'

``parse_type`` parses a type expression, and ``expr_echo`` returns both the
elaborated expression and its type.

Creating goals and running tactics
----------------------------------

This is the core of the kernel facade. Create a goal from a type string,
then apply tactics step by step:

.. code-block:: python

   >>> state = k.goal_create("∀ n : Nat, n + 0 = n")
   >>> state.n_goals()
   1
   >>> state.is_solved()
   False
   >>> print(state.pretty())
   ⊢ ∀ (n : Nat), n + 0 = n

Apply a tactic:

.. code-block:: python

   >>> result = state.try_tactic("intro n")
   >>> result.ok
   True
   >>> print(result.state.pretty())
   n : Nat
   ⊢ n + 0 = n

Each ``try_tactic`` call returns a ``TacticResult`` with a status
(``"success"`` / ``"failure"`` / ``"parseError"``), diagnostic messages,
and the new ``GoalState`` if successful.

Beyond ``try_tactic``, there are prograde tactics for structured proof
construction:

.. code-block:: python

   result = state.try_have("h", "n = n")     # have h : n = n := ?
   result = state.try_let("x", "Nat")        # let x : Nat := ?
   result = state.try_define("x", "42")      # let x := 42
   result = state.try_draft("Nat.add_zero n")  # may leave sorry subgoals

Frontend processing
-------------------

You can also process raw Lean source code against the current environment:

.. code-block:: python

   >>> k.process("def myFn : Nat := 42\n")
   'myFn'

   >>> k.find_source_path("Init.Prelude")
   '/path/to/.elan/toolchains/.../lib/lean/library/Init/Prelude.lean'

   >>> state, msg = k.collect_sorrys("def f : Nat := sorry\n")
   >>> state.pretty()  # the sorry becomes a goal
   '⊢ Nat'

Goal state lifecycle
--------------------

Goal states support serialisation and branching:

.. code-block:: python

   # Pickle / unpickle
   state.pickle("/tmp/goal.bin")
   restored = k.goal_unpickle("/tmp/goal.bin")

   # Branch and merge
   branch = state.try_tactic("intro n").state
   merged = state.continue_with(branch)

The full ``GoalState`` API is documented in :doc:`../api/kernel`.

What to take away
-----------------

The kernel facade lets you drive Lean's proof engine entirely from Python.
The pattern is always:

1. ``Kernel(lib)`` -- wrap a ``LeanLibrary``
2. ``k.load(["Init"])`` -- load modules
3. ``k.goal_create(...)`` -- create goals
4. ``state.try_tactic(...)`` -- apply tactics
5. ``state.is_solved()`` -- check completion

This is useful for proof search, tactic synthesis, AI-driven theorem
proving, and any workflow where you want programmatic control over the
proof state.
