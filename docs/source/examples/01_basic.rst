Basic Example
=============

This walkthrough builds the smallest possible lean-py project: a handful
of functions, a structure, and an inductive type, all callable from Python.

`View full source on GitHub <https://github.com/BasisResearch/lean.py/tree/main/examples/01_basic>`_

The Lean side
-------------

We start with the imports. Every lean-py project needs ``import LeanPy``:

.. code-block:: lean

   import LeanPy
   open LeanPy

Exporting a function
^^^^^^^^^^^^^^^^^^^^

The simplest thing you can do is export a function. Annotate it with
``@[python "symbol_name"]`` and lean-py takes care of the rest -- type
marshalling, C ABI, everything:

.. code-block:: lean

   @[python "py_increment"]
   def increment (x : Int) : Int := x + 1

On the Python side, this becomes ``lib.increment(7)`` and returns ``8``.

Functions can return ``IO`` too. lean-py unwraps the ``IO`` result
automatically (and raises ``LeanError`` on failure):

.. code-block:: lean

   @[python "py_greet"]
   def greet (name : String) : IO String :=
     return s!"Hello, {name}!"

Collection types like ``Array`` are marshalled to Python lists:

.. code-block:: lean

   @[python "py_sum_array"]
   def sumArray (xs : Array Int) : Int :=
     xs.foldl (· + ·) 0

Exporting a structure
^^^^^^^^^^^^^^^^^^^^^

Structures need one extra step: ``derive_python`` registers the type's
constructor so Python can both create and destructure values:

.. code-block:: lean

   structure Point where
     x : Int
     y : Int
     deriving Repr

   derive_python Point

Now you can export functions that take or return ``Point``:

.. code-block:: lean

   @[python "py_origin"]
   def origin (_ : Unit) : Point := ⟨0, 0⟩

   @[python "py_norm_sq"]
   def normSq (p : Point) : Int := p.x * p.x + p.y * p.y

Exporting an inductive
^^^^^^^^^^^^^^^^^^^^^^

Inductives work the same way. Each constructor becomes accessible on the
Python side as an attribute of the type:

.. code-block:: lean

   inductive Shape where
     | circle (r : Int)
     | square (side : Int)
     | rect   (w h : Int)
     deriving Repr

   derive_python Shape

   @[python "py_perimeter"]
   def perimeter (s : Shape) : Int :=
     match s with
     | .circle r => 6 * r
     | .square s => 4 * s
     | .rect w h => 2 * (w + h)

Making it all visible
^^^^^^^^^^^^^^^^^^^^^

The last line in the Lean file is what actually makes everything
discoverable by Python:

.. code-block:: lean

   #export_python_registry "Basic"

This emits two C functions (``Basic_funcs_json`` and ``Basic_types_json``)
that ``LeanLibrary`` reads at load time to build wrappers.

The Python side
---------------

After ``lake build``, the Python code is straightforward:

.. code-block:: python

   from lean_py import LeanLibrary

   lib = LeanLibrary.from_lake("path/to/lean", "Basic", build=True)

Now call everything we exported:

.. code-block:: python

   >>> lib.increment(7)
   8

   >>> lib.greet("world")
   'Hello, world!'

   >>> lib.sumArray(list(range(1, 11)))
   55

Structures are callable -- ``lib.Point(3, 4)`` constructs a
``LeanInductiveValue`` that can be passed back to Lean:

.. code-block:: python

   >>> p = lib.Point(3, 4)
   >>> p
   Point.mk(3, 4)

   >>> lib.normSq(p)
   25

Inductives expose their constructors as attributes:

.. code-block:: python

   >>> lib.Shape.circle(5)
   Shape.circle(5)

   >>> lib.perimeter(lib.Shape.circle(5))
   30

   >>> lib.perimeter(lib.Shape.rect(2, 3))
   10

Pattern matching works naturally with Python 3.10+ ``match``/``case``:

.. code-block:: python

   Shape = lib.Shape

   def describe(s):
       match s:
           case Shape.circle(r):
               return f"circle with radius {r}"
           case Shape.square(side):
               return f"square with side {side}"
           case Shape.rect(w, h):
               return f"{w}x{h} rectangle"

   >>> describe(lib.Shape.circle(5))
   'circle with radius 5'

   >>> describe(lib.Shape.rect(2, 3))
   '2x3 rectangle'

Running it
----------

.. code-block:: bash

   cd examples/01_basic/lean && lake build && cd ..
   uv run --project python python/main.py

Output:

.. code-block:: text

   py_increment(7)        = 8
   py_greet("world")      = Hello, world!
   py_sum_array([1..10])  = 55
   py_origin(())          = Point.mk(0, 0)
   py_norm_sq((3, 4))     = 25
   py_perimeter(circle 5) = 30
   py_perimeter(square 4) = 16
   py_perimeter(rect 2 3) = 10

What to take away
-----------------

Three annotations power the whole thing:

1. ``@[python "name"]`` -- export a function.
2. ``derive_python T`` -- register a type's constructors.
3. ``#export_python_registry "Prefix"`` -- emit the metadata Python reads.

On the Python side, ``LeanLibrary.from_lake(...)`` does all the work:
finding the shared library, calling the JSON registry, and building
typed wrappers.
