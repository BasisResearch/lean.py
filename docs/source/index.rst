lean-py
=======

Effortless interop between **Lean 4** and **Python**, in both directions.

* **Lean -> Python.** Annotate any Lean definition with ``@[python "name"]``
  and call it from Python with automatic type marshalling.
  ``derive_python`` exposes inductives and structures as Python constructors.

* **Python -> Lean.** ``LeanPy.Python`` gives Lean code a ``Py`` type with
  ``import_``, ``eval``, ``exec``, ``getAttr``, ``call``, etc. CPython is
  loaded lazily via ``dlopen``.

* **Kernel facade.** ``LeanPy.Kernel`` wraps the
  `Pantograph <https://github.com/leanprover/Pantograph>`_ library so a
  Python process can drive Lean's type-checker, elaborator, and tactic
  engine without spawning a subprocess.

.. toctree::
   :maxdepth: 1
   :caption: Getting Started

   getting_started
   project_setup
   z3py-guide

.. toctree::
   :maxdepth: 1
   :caption: Examples

   examples/01_basic
   examples/02_pantograph_kernel
   examples/03_numpy_typed
   examples/04_sympy_tactic
   examples/05_knuckledragger
   examples/06_effectful_verifier

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/library
   api/kernel
   api/marshal
   api/registry
   api/exceptions

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
