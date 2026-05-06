Setting Up a Project
====================

This guide walks through creating a new project that uses lean-py from
scratch. By the end you will have a Lean library that exports functions,
structures, and inductives to Python with full type marshalling.

Directory Layout
----------------

A typical lean-py project has two halves -- a Lake project for Lean and a
``pyproject.toml`` for Python:

.. code-block:: text

   my-project/
     lean/
       lakefile.toml
       lean-toolchain
       MyLib.lean
     python/
       pyproject.toml
       main.py

Step 1: Create the Lean Project
-------------------------------

.. code-block:: bash

   mkdir -p my-project/lean && cd my-project/lean
   lake init MyLib

Set the toolchain to match lean-py's pinned version:

.. code-block:: bash

   echo "leanprover/lean4:v4.29.1" > lean-toolchain

Edit ``lakefile.toml``:

.. code-block:: toml

   [package]
   name = "MyLib"
   version = "0.1.0"
   leanOptions = []

   [[require]]
   name = "LeanPy"
   git  = "https://github.com/kiranandcode/lean.py"

   [[lean_lib]]
   name = "MyLib"
   moreLinkObjs = [
     "LeanPy/LeanPy:static",
     "LeanPy/leanPyNative:static",
     "Pantograph/Pantograph:static",
   ]
   precompileModules = true
   defaultFacets = ["shared"]
   moreLinkArgs = ["-Wl,-headerpad_max_install_names"]

Step 2: Write Lean Code
------------------------

Create ``MyLib.lean``:

.. code-block:: lean

   import LeanPy
   open LeanPy

   -- Export a simple function
   @[python "increment"]
   def increment (n : Int) : Int := n + 1

   -- Export a structure
   structure Point where
     x : Int
     y : Int

   derive_python Point

   @[python "origin"]
   def origin (_ : Unit) : Point := { x := 0, y := 0 }

   @[python "norm_sq"]
   def normSq (p : Point) : Int := p.x * p.x + p.y * p.y

   -- Export an inductive
   inductive Shape where
     | circle (radius : Int)
     | rect (width height : Int)

   derive_python Shape

   @[python "area"]
   def area (s : Shape) : Int :=
     match s with
     | .circle r => 3 * r * r     -- approximate
     | .rect w h => w * h

   -- Make the registry visible to Python
   #export_python_registry "MyLib"

Key concepts:

* ``@[python "name"]`` marks a function for export with the given symbol name.
* ``derive_python T`` registers a type's constructors so Python can create and
  destructure values of type ``T``.
* ``#export_python_registry "Prefix"`` emits the JSON metadata that Python
  reads at load time.

Step 3: Build
-------------

.. code-block:: bash

   cd lean && lake build

This fetches LeanPy and Pantograph, compiles everything, and produces a
shared library at ``lean/.lake/build/lib/libMyLib.{dylib,so}``.

Step 4: Create the Python Project
----------------------------------

.. code-block:: bash

   cd ../python
   cat > pyproject.toml << 'EOF'
   [project]
   name = "my-project"
   version = "0.1.0"
   requires-python = ">=3.12"
   dependencies = ["lean_py @ git+https://github.com/kiranandcode/lean.py"]

   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"
   EOF

Install:

.. code-block:: bash

   uv sync

Step 5: Call Lean from Python
-----------------------------

Create ``main.py``:

.. code-block:: python

   from lean_py import LeanLibrary

   lib = LeanLibrary.from_lake("../lean", "MyLib")

   # Functions
   print(lib.increment(41))        # 42

   # Structures
   p = lib.Point(3, 4)
   print(p)                        # Point.mk(3, 4)
   print(lib.norm_sq(p))           # 25

   # Inductives
   c = lib.Shape.circle(5)
   r = lib.Shape.rect(3, 4)
   print(lib.area(c))              # 75
   print(lib.area(r))              # 12

Run:

.. code-block:: bash

   uv run python main.py

Using Additional Lake Dependencies
-----------------------------------

If your Lean code depends on other libraries (Batteries, Mathlib, etc.),
add them as ``[[require]]`` entries and include them in ``moreLinkObjs``
if their symbols are called at runtime:

.. code-block:: toml

   [[require]]
   name = "batteries"
   git  = "https://github.com/leanprover-community/batteries"
   rev  = "main"

   [[lean_lib]]
   name = "MyLib"
   moreLinkObjs = [
     "LeanPy/LeanPy:static",
     "LeanPy/leanPyNative:static",
     "Pantograph/Pantograph:static",
     "batteries/Batteries:static",
   ]

**Rule of thumb:** if ``lake build`` succeeds but Python fails with
``symbol not found``, add the missing package as
``"<package>/<LibName>:static"`` to ``moreLinkObjs``.

Type Marshalling Reference
--------------------------

lean-py automatically marshals these types between Lean and Python:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Lean type
     - Python type
     - Notes
   * - ``Unit``
     - ``None``
     -
   * - ``Bool``
     - ``bool``
     -
   * - ``Nat``
     - ``int``
     - Non-negative
   * - ``Int``
     - ``int``
     -
   * - ``Float``
     - ``float``
     -
   * - ``String``
     - ``str``
     -
   * - ``Char``
     - ``str`` (length 1)
     -
   * - ``UInt8/16/32/64``
     - ``int``
     -
   * - ``Array a``
     - ``list``
     -
   * - ``List a``
     - ``list``
     -
   * - ``Option a``
     - value or ``None``
     -
   * - ``a x b``
     - ``tuple``
     -
   * - ``IO a``
     - unwrapped value
     - Raises ``LeanError`` on error
   * - User inductives
     - ``LeanInductiveValue``
     - Via ``derive_python``
   * - User structures
     - ``LeanInductiveValue``
     - Callable constructor
