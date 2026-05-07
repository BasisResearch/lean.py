Marshalling
===========

The marshalling layer converts between Python values and Lean runtime
objects (``lean_object*`` pointers). It handles scalars, strings,
arrays, options, and arbitrary inductives — in both directions.

`Source: lean_py/marshal.py <https://github.com/BasisResearch/lean.py/blob/main/lean_py/marshal.py>`_

How values cross the boundary
-----------------------------

When you call ``lib.increment(7)``, the marshaller:

1. Looks up the function's parameter types from the registry.
2. Converts ``7`` (a Python ``int``) to a Lean ``Int`` object using the
   appropriate ``to_lean`` function.
3. After the C call returns, converts the Lean result back to a Python
   ``int`` using the corresponding ``from_lean`` function.

Each type has a ``TypeWrapper`` — a pair of ``(to_lean, from_lean)``
functions plus the ctypes type used at the C ABI level.

Scalar types
^^^^^^^^^^^^

Lean scalars map directly to Python primitives:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Lean type
     - Python type
     - Notes
   * - ``Nat``, ``Int``
     - ``int``
     - Arbitrary precision (uses ``lean_int_big_*`` for large values)
   * - ``Float``
     - ``float``
     -
   * - ``String``
     - ``str``
     - UTF-8 encoded
   * - ``Bool``
     - ``bool``
     - Boxed as ``lean_box(0)`` / ``lean_box(1)``
   * - ``Char``
     - ``str`` (single char)
     -
   * - ``UInt8`` .. ``UInt64``
     - ``int``
     - Fixed-width, unboxed at the C level

Container types
^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Lean type
     - Python type
     - Notes
   * - ``Array α``
     - ``list``
     - Elements recursively marshalled
   * - ``List α``
     - ``list``
     - Converted via linked-list ctors
   * - ``Option α``
     - value or ``None``
     -
   * - ``Prod α β``
     - ``tuple``
     - ``(a, b)``

Inductive types
^^^^^^^^^^^^^^^

Any Lean inductive registered with ``derive_python`` is marshalled to
and from ``LeanInductiveValue``:

.. code-block:: python

   >>> lib.Shape.circle(5)
   Shape.circle(5)

   >>> val = lib.perimeter(lib.Shape.circle(5))
   30

Going to Lean, the marshaller encodes each ``LeanInductiveValue``
recursively: allocating a ``lean_ctor_object`` with the right tag,
writing object fields and scalar fields, and using *smart constructors*
(``lean_name_mk_string``, ``lean_expr_mk_app``, etc.) for types that
have computed fields like hashes.

Coming from Lean, the marshaller reads the constructor tag, looks up the
``CtorInfo``, and extracts fields by index.

LeanObj — owned pointers
------------------------

``LeanObj`` is a Python-side RAII wrapper around a ``lean_object*``:

.. code-block:: python

   from lean_py.marshal import LeanObj

   # Takes ownership — will call lean_dec_ref on __del__
   obj = LeanObj(raw_pointer)

   # Borrow without taking ownership
   borrowed = LeanObj.borrow(raw_pointer)

   # Release ownership back to caller
   ptr = obj.release()

The key invariant: constructing a ``LeanObj`` does **not** increment the
reference count. It assumes the caller is transferring ownership. On
destruction (or garbage collection), it calls ``lean_dec_ref`` to release
the reference.

LeanInductiveValue — Python-side inductives
--------------------------------------------

``LeanInductiveValue`` represents a Lean constructor application:

.. code-block:: python

   >>> val = LeanInductiveValue("Shape", "circle", tag=0, fields=(5,))
   >>> val.ctor
   'circle'
   >>> val.tag
   0
   >>> val.fields
   (5,)
   >>> val._0
   5

It supports Python 3.10+ structural pattern matching:

.. code-block:: python

   match val:
       case Shape.circle(r):
           print(f"radius = {r}")

The ``_CtorMeta`` metaclass makes ``isinstance(val, Shape.circle)`` work
by checking the constructor name rather than the Python class hierarchy.

Smart constructors
------------------

Some Lean types (``Name``, ``Level``, ``Expr``) have *computed fields* —
scalar values (like hashes) that are derived from the constructor
arguments. Allocating a plain ``lean_ctor_object`` and writing the fields
by hand would leave these computed fields uninitialised, breaking
environment lookups.

The marshaller uses **smart constructors** — C functions exported by the
Lean runtime with ``@[export]`` — that correctly compute and store these
fields:

.. list-table::
   :header-rows: 1
   :widths: 35 35 30

   * - C symbol
     - Lean constructor
     - Type
   * - ``lean_name_mk_string``
     - ``Name.str``
     - ``Name``
   * - ``lean_name_mk_numeral``
     - ``Name.num``
     - ``Name``
   * - ``lean_expr_mk_app``
     - ``Expr.app``
     - ``Expr``
   * - ``lean_expr_mk_forall``
     - ``Expr.forallE``
     - ``Expr``
   * - ``lean_expr_mk_lambda``
     - ``Expr.lam``
     - ``Expr``
   * - ...
     - ...
     - ...

These smart constructors take ownership of their arguments without
incrementing the reference count — the marshaller must **not** call
``lean_dec`` on the children after construction. This matches Lean's
compiler codegen convention.

The Marshaller class
--------------------

``Marshaller`` is the central registry of type wrappers. It is created
automatically by ``LeanLibrary`` from the ``LibraryRegistry``:

.. code-block:: python

   # Usually you don't create this directly — LeanLibrary does it
   marshaller = Marshaller(registry)

   # Look up conversion functions for a type
   wrapper = marshaller.wrapper_for(type_repr)
   lean_val = wrapper.to_lean(python_val)
   python_val = wrapper.from_lean(lean_val)

For custom types, the marshaller builds recursive encode/decode functions
at wrapper-creation time, so the per-call overhead is a chain of Python
function calls rather than a registry lookup.

API reference
-------------

.. autoclass:: lean_py.marshal.LeanObj
   :members:
   :show-inheritance:

.. autoclass:: lean_py.marshal.LeanInductiveValue
   :members:
   :show-inheritance:

.. autoclass:: lean_py.marshal.Marshaller
   :members:
   :show-inheritance:

.. autoclass:: lean_py.marshal.TypeWrapper
   :members:
   :show-inheritance:
