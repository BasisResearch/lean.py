Exceptions
==========

lean-py raises two exception types for errors that originate in Lean code.

`Source: lean_py/exceptions.py <https://github.com/BasisResearch/lean.py/blob/main/lean_py/exceptions.py>`_

LeanError
---------

Raised when a Lean ``IO`` function returns an error result. The message
is extracted from the Lean ``IO.Error`` value:

.. code-block:: python

   from lean_py.exceptions import LeanError

   try:
       lib.some_io_function("bad input")
   except LeanError as e:
       print(e)  # "userError: ..."

The most common case is ``IO.userError`` from ``throw`` in Lean code.

LeanPyCallbackError
-------------------

Raised when a Python callback invoked from Lean (via ``LeanPy.Python``)
throws an exception. This wraps the original Python exception so the
Lean caller sees a structured error rather than a segfault:

.. code-block:: python

   from lean_py.exceptions import LeanPyCallbackError

   try:
       lib.run_lean_that_calls_python()
   except LeanPyCallbackError as e:
       print(e.__cause__)  # the original Python exception

API reference
-------------

.. automodule:: lean_py.exceptions
   :members: LeanError, LeanPyCallbackError
   :show-inheritance:
