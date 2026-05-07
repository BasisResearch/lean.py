Kernel
======

The kernel module gives Python direct access to Lean 4's type-checker,
elaborator, and tactic engine. It wraps ~30 ``@[python]`` functions from
``LeanPy.Kernel`` into two classes: ``Kernel`` (the environment facade)
and ``GoalState`` (an opaque proof state handle).

`Source: lean_py/kernel.py <https://github.com/BasisResearch/lean.py/blob/main/lean_py/kernel.py>`_

Setup
-----

Any Lean project that imports ``LeanPy.Kernel`` automatically has the
kernel surface available. On the Python side:

.. code-block:: python

   from lean_py import LeanLibrary
   from lean_py.kernel import Kernel

   lib = LeanLibrary.from_lake("path/to/lean", "MyLib", build=True)
   k = Kernel(lib)

Loading an environment
----------------------

Before any queries, load one or more Lean modules:

.. code-block:: python

   >>> k.init_search("")
   >>> k.load(["Init"])
   >>> k.is_loaded()
   True
   >>> k.decl_count()
   8947

``init_search`` sets the search path (empty string uses the default
toolchain path). ``load`` imports one or more modules — pass
``["Init", "Mathlib.Tactic.Omega"]`` to get multiple.

Querying declarations
---------------------

Once loaded, the full Lean environment is queryable:

.. code-block:: python

   >>> k.decl_exists("Nat.succ")
   True

   >>> k.decl_type("Nat.succ")
   'Nat → Nat'

   >>> k.module_of("Nat.succ")
   'Init.Prelude'

   >>> k.search("add_comm")
   ['Nat.add_comm', 'Int.add_comm', ...]

``catalog()`` returns all declaration names. ``all_decls()`` returns them
including internal names. ``decl_value`` retrieves the definition body.

Elaboration
-----------

The kernel can elaborate, reduce, and decide:

.. code-block:: python

   >>> k.infer_type("Nat.succ Nat.zero")
   'Nat'

   >>> k.whnf("(fun x => x + 1) 4")
   '5'

   >>> k.decide("1 + 1 = 2")
   'true'

``expr_echo`` returns both the elaborated expression and its type:

.. code-block:: python

   >>> expr, ty = k.expr_echo("(1 : Int) + 1")
   >>> expr
   '@HAdd.hAdd Int Int Int (@instHAdd Int Int.instAdd) ...'
   >>> ty
   'Int'

This is useful for discovering the fully-elaborated form of Lean
expressions — for instance, the exact instance names needed when building
``Lean.Expr`` trees programmatically.

Creating goals and running tactics
----------------------------------

This is the heart of the kernel facade. Create a goal from a type string,
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
   >>> result.status
   'success'
   >>> print(result.state.pretty())
   n : Nat
   ⊢ n + 0 = n

Close the proof:

.. code-block:: python

   >>> result2 = result.state.try_tactic("simp")
   >>> result2.state.is_solved()
   True

Failed tactics return ``result.ok == False`` with diagnostic messages:

.. code-block:: python

   >>> bad = state.try_tactic("exact rfl")
   >>> bad.ok
   False
   >>> bad.messages
   ['type mismatch...']

Prograde tactics
^^^^^^^^^^^^^^^^

Beyond ``try_tactic``, structured proof construction is available:

.. code-block:: python

   result = state.try_have("h", "n = n")      # have h : n = n := ?
   result = state.try_let("x", "Nat")          # let x : Nat := ?
   result = state.try_define("x", "42")         # let x := 42
   result = state.try_draft("Nat.add_zero n")   # may leave sorry subgoals

Conv and calc modes
^^^^^^^^^^^^^^^^^^^

Enter conversion or calculation mode, then exit when done:

.. code-block:: python

   conv_state = state.conv_enter().state
   # ... apply conv tactics ...
   final_state = conv_state.fragment_exit().state

Goal state lifecycle
--------------------

Goal states support serialisation, branching, and merging:

.. code-block:: python

   # Pickle to disk and restore later
   state.pickle("/tmp/goal.bin")
   restored = k.goal_unpickle("/tmp/goal.bin")

   # Branch: apply different tactics to the same state
   branch_a = state.try_tactic("intro n").state
   branch_b = state.try_tactic("intros").state

   # Continue: merge a branch back
   merged = state.continue_with(branch_a)

   # Resume with specific goal names
   resumed = state.resume(["_uniq.42"])

Environment serialisation
-------------------------

The entire Lean environment can be saved and restored:

.. code-block:: python

   k.env_pickle("/tmp/env.bin")
   k.env_unpickle("/tmp/env.bin")

Frontend processing
-------------------

Process raw Lean source code against the current environment:

.. code-block:: python

   >>> k.process("def myFn : Nat := 42\\n")

   >>> state, msg = k.collect_sorrys("def f : Nat := sorry\\n")
   >>> state.pretty()
   '⊢ Nat'

``collect_sorrys`` extracts all ``sorry`` placeholders as goals — useful
for AI-driven proof completion.

API reference
-------------

.. autoclass:: lean_py.kernel.Kernel
   :members:
   :show-inheritance:

.. autoclass:: lean_py.kernel.GoalState
   :members:
   :show-inheritance:

.. autoclass:: lean_py.kernel.TacticResult
   :members:
   :show-inheritance:
