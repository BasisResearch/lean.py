Getting Started
===============

lean-py bridges Lean 4 and Python so you can call Lean functions from Python
(and vice versa) with automatic type marshalling. This page walks you through
a minimal end-to-end example.

Prerequisites
-------------

* A working `elan <https://github.com/leanprover/elan>`_ install (``lean`` on PATH).
* Python 3.12+ with `uv <https://docs.astral.sh/uv/>`_ (recommended) or pip.

Installation
------------

**Python side:**

.. code-block:: bash

   uv pip install "lean_py @ git+https://github.com/kiranandcode/lean.py"

Or in ``pyproject.toml``:

.. code-block:: toml

   [project]
   dependencies = ["lean_py @ git+https://github.com/kiranandcode/lean.py"]

The Python package discovers ``lean.h`` and ``libleanshared`` from the active
Lean toolchain at import time.

**Lean side:**

Add to your ``lakefile.toml``:

.. code-block:: toml

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
   # macOS only:
   moreLinkArgs = ["-Wl,-headerpad_max_install_names"]

Then build:

.. code-block:: bash

   lake build

.. note::

   **Why three static libs?** ``LeanPy:static`` is the Lean module,
   ``leanPyNative:static`` is the C bridge (``python_bridge.c``), and
   ``Pantograph:static`` is the proof-assistant kernel that ``LeanPy.Kernel``
   depends on. All three must be linked into the shared library that
   Python loads.

Quick Start
-----------

**1. Write Lean code**

.. code-block:: lean

   -- MyLib.lean
   import LeanPy
   open LeanPy

   @[python "add"]
   def add (a b : Int) : Int := a + b

   structure Point where
     x : Int
     y : Int

   derive_python Point

   @[python "origin"]
   def origin (_ : Unit) : Point := { x := 0, y := 0 }

   #export_python_registry "MyLib"

**2. Call from Python**

.. code-block:: python

   from lean_py import LeanLibrary

   lib = LeanLibrary.from_lake("path/to/lake/project", "MyLib", build=True)

   lib.add(3, 4)          # 7
   lib.origin(None)       # Point.mk(0, 0)
   lib.Point(10, 20)      # Point.mk(10, 20)

``from_lake`` finds the shared library produced by ``lake build``. Pass
``build=True`` to run ``lake build`` automatically.

Calling Python from Lean
------------------------

.. code-block:: lean

   open LeanPy.Python in
   @[python "numpy_dot"]
   def numpyDot (xs ys : Array Int) : IO Int := do
     init ()
     let np <- import_ "numpy"
     let dot <- np.getAttr "dot"
     let a <- Py.ofList (xs.toList.map Py.ofInt)
     let b <- Py.ofList (ys.toList.map Py.ofInt)
     (<- dot.call #[<- a, <- b]).toInt

.. code-block:: python

   lib.numpy_dot([1, 2, 3], [4, 5, 6])   # 32

Kernel Facade
-------------

Drive Lean's type-checker and tactic engine from Python:

.. code-block:: python

   from lean_py import LeanLibrary
   from lean_py.kernel import Kernel

   lib = LeanLibrary.from_lake("path/to/project", "MyLib", build=True)
   k = Kernel(lib)
   k.load(["Init"])

   state = k.goal_create("forall n : Nat, n + 0 = n")
   print(state.pretty())             # |- forall (n : Nat), n + 0 = n

   result = state.try_tactic("intro n")
   print(result.state.pretty())      # n : Nat  |- n + 0 = n

   result2 = result.state.try_tactic("simp")
   print(result2.state.is_solved())  # True

Exception Handling
------------------

Errors carry type information across the boundary:

.. code-block:: python

   from lean_py import LeanError, LeanPyCallbackError

   try:
       lib.some_io_function()
   except LeanPyCallbackError as e:    # Python error inside Lean callback
       print(e.python_type, e.python_message)
   except LeanError as e:              # Lean IO error
       print(e.kind, e.message)

Next Steps
----------

* :doc:`project_setup` -- detailed guide for setting up your own project
* :doc:`examples/01_basic` -- the smallest end-to-end example
* :doc:`examples/02_pantograph_kernel` -- using the kernel facade
* :doc:`api/library` -- full API reference
