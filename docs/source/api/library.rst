Library Loading
===============

``LeanLibrary`` is the entry point to lean-py. It loads a compiled Lean
shared library, discovers its ``@[python]``-annotated functions and
``derive_python`` types, and exposes them as ordinary Python callables.

`Source: lean_py/library.py <https://github.com/BasisResearch/lean.py/blob/main/lean_py/library.py>`_

Loading from a Lake project
---------------------------

The most common way to create a library is from a Lake project directory:

.. code-block:: python

   from lean_py import LeanLibrary

   lib = LeanLibrary.from_lake("examples/01_basic/lean", "Basic", build=True)

``from_lake`` does three things:

1. Optionally runs ``lake build`` (when ``build=True``).
2. Locates the shared library under ``.lake/build/lib/``.
3. Returns a fully initialised ``LeanLibrary`` with all wrappers ready.

If the project produces a single shared library, the name can be omitted:

.. code-block:: python

   lib = LeanLibrary.from_lake("examples/01_basic/lean", build=True)

Loading from a path
^^^^^^^^^^^^^^^^^^^

You can also load a pre-built ``.dylib`` / ``.so`` directly:

.. code-block:: python

   lib = LeanLibrary("/path/to/libBasic.dylib", "Basic")

What happens at load time
-------------------------

When you create a ``LeanLibrary``, the following steps execute in order:

1. **dylib is loaded** via ``ctypes.PyDLL`` with ``RTLD_GLOBAL`` so that
   subsequently loaded libraries can see its symbols.

2. **macOS rpath fixup** — on macOS, any ``@rpath/libFoo.dylib`` references
   in the dylib are rewritten to absolute paths under Lean's ``lib/lean/``
   directory. This means you don't need ``DYLD_LIBRARY_PATH``.

3. **Lean task manager** is initialised once per process (required by
   ``importModules`` and any kernel operation that allocates a ``Task``).

4. **Module initialiser** is called — the ``initialize_<LibName>`` symbol
   that Lean's compiler generates. This runs all ``initialize`` blocks.

5. **JSON registry** is read — the ``#export_python_registry "LibName"``
   command in Lean emits two C functions (``LibName_funcs_json`` and
   ``LibName_types_json``) that return JSON describing every exported
   function and type. ``LeanLibrary`` calls these and parses the result
   into a :class:`~lean_py.registry.LibraryRegistry`.

6. **Wrappers are built** for each function and type. Functions get a
   Python callable that handles marshalling; types get either an
   ``_InductiveType`` or ``_StructureType`` namespace.

Calling functions
-----------------

Every ``@[python "name"]`` function becomes an attribute on the library:

.. code-block:: python

   >>> lib.increment(7)
   8

   >>> lib.greet("world")
   'Hello, world!'

   >>> lib.sumArray(list(range(1, 11)))
   55

The wrapper automatically marshals Python values to Lean objects (and back)
according to the type registry. ``IO``-returning functions have their
``IO`` unwrapped transparently — if the Lean function throws, Python gets
a ``LeanError``.

Working with types
------------------

Types registered with ``derive_python`` appear as namespaces on the library.

**Structures** (single-constructor types) are callable:

.. code-block:: python

   >>> p = lib.Point(3, 4)
   >>> p
   Point.mk(3, 4)

   >>> lib.normSq(p)
   25

**Inductives** expose each constructor as an attribute:

.. code-block:: python

   >>> lib.Shape.circle(5)
   Shape.circle(5)

   >>> lib.perimeter(lib.Shape.rect(2, 3))
   10

Both support Python 3.10+ structural pattern matching:

.. code-block:: python

   match shape:
       case lib.Shape.circle(r):
           print(f"circle with radius {r}")
       case lib.Shape.rect(w, h):
           print(f"{w}x{h} rectangle")

And ``isinstance`` checks work against constructor classes:

.. code-block:: python

   >>> isinstance(lib.Shape.circle(5), lib.Shape.circle)
   True

API reference
-------------

.. autoclass:: lean_py.library.LeanLibrary
   :members: from_lake, __init__, __getitem__, __repr__
   :show-inheritance:
