Basic Example
=============

The smallest end-to-end demo: a few ``@[python]`` functions, a structure,
and an inductive type exported from Lean and called from Python.

`View source on GitHub <https://github.com/kiranandcode/lean.py/tree/main/examples/01_basic>`_

Lean Side
---------

The Lean file defines three exported functions, a ``Point`` structure, and
a ``Shape`` inductive, then registers them all for Python access:

.. literalinclude:: ../../../examples/01_basic/lean/Basic.lean
   :language: lean
   :caption: examples/01_basic/lean/Basic.lean

The ``lakefile.toml`` links against the required static libraries:

.. literalinclude:: ../../../examples/01_basic/lean/lakefile.toml
   :language: toml
   :caption: examples/01_basic/lean/lakefile.toml

Python Side
-----------

The Python script loads the compiled library and exercises every
exported symbol:

.. literalinclude:: ../../../examples/01_basic/python/main.py
   :language: python
   :caption: examples/01_basic/python/main.py

Running
-------

.. code-block:: bash

   cd examples/01_basic
   cd lean && lake build && cd ..
   uv run --project python python/main.py

Key Takeaways
-------------

* ``@[python "name"]`` exports a Lean function with the given symbol name.
* ``derive_python`` registers a type so that Python can construct and
  destructure its values.
* ``#export_python_registry "Prefix"`` emits the JSON metadata that
  ``LeanLibrary`` reads at load time.
* Structures become callable on the Python side (``lib.Point(1, 2)``).
* Inductives become namespaces with constructor attributes
  (``lib.Shape.circle(5)``).
