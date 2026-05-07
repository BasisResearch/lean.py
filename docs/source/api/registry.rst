Registry
========

The registry module mirrors the Lean-side ``LeanPy.TypeRepr`` data model
in Python. It describes the shape of every exported function and type so
the marshaller knows how to convert values across the FFI boundary.

`Source: lean_py/registry.py <https://github.com/BasisResearch/lean.py/blob/main/lean_py/registry.py>`_

Where the data comes from
-------------------------

On the Lean side, the command ``#export_python_registry "MyLib"`` emits
two C functions:

- ``MyLib_funcs_json`` — JSON array of exported functions
- ``MyLib_types_json`` — JSON array of registered inductive types

``LeanLibrary`` calls these at load time and parses the result into a
``LibraryRegistry``.

TypeRepr — describing Lean types
--------------------------------

Every parameter, return type, and constructor field is described by a
``TypeRepr``. It captures the *structural shape* of the type, not its
full Lean name:

.. code-block:: python

   >>> from lean_py.registry import TypeRepr
   >>> TypeRepr(kind="int")            # Lean Int
   >>> TypeRepr(kind="array", elem=TypeRepr(kind="string"))  # Array String
   >>> TypeRepr(kind="named", name="Point")   # a derive_python'd type
   >>> TypeRepr(kind="io", elem=TypeRepr(kind="nat"))  # IO Nat

The ``short()`` method produces a compact pseudo-Lean rendering:

.. code-block:: python

   >>> TypeRepr(kind="array", elem=TypeRepr(kind="int")).short()
   'Array[Int]'

Supported kinds:

- Primitives: ``"unit"``, ``"bool"``, ``"nat"``, ``"int"``, ``"float"``,
  ``"char"``, ``"string"``
- Fixed-width: ``"uint"`` / ``"sint"`` with a ``bits`` field (8, 16, 32, 64)
- Containers: ``"array"``, ``"list"``, ``"option"``, ``"prod"``
- Wrappers: ``"io"`` (unwrapped automatically), ``"pyobject"`` (raw
  ``PyObject*``), ``"opaque"`` (untouched ``lean_object*``)
- Named: ``"named"`` with a ``name`` field pointing to a ``derive_python``
  type

CtorInfo — constructor metadata
-------------------------------

Each constructor of a ``derive_python``'d inductive is described by a
``CtorInfo``:

.. code-block:: python

   >>> CtorInfo(name="circle", tag=0, fields=[TypeRepr(kind="int")])
   >>> CtorInfo(name="rect", tag=2, fields=[TypeRepr(kind="int"), TypeRepr(kind="int")])

- ``name``: the constructor name (e.g. ``"circle"``, ``"mk"``)
- ``tag``: the runtime tag value
- ``fields``: list of ``TypeRepr`` for each field, in declaration order

TypeInfo — type metadata
------------------------

A ``TypeInfo`` bundles all constructors for a registered type:

.. code-block:: python

   >>> TypeInfo(name="Shape", isStructure=False, isEnum=False,
   ...          ctors=[circle_info, square_info, rect_info])

- ``isStructure``: true if the type has exactly one constructor
- ``isEnum``: true if all constructors are nullary

FuncInfo — function metadata
----------------------------

Each ``@[python]``-annotated function is described by a ``FuncInfo``:

.. code-block:: python

   >>> FuncInfo(
   ...     declName="increment",
   ...     exportName="py_increment",
   ...     params=[TypeRepr(kind="int")],
   ...     returnType=TypeRepr(kind="int"),
   ... )

``declName`` is the Lean name; ``exportName`` is the C symbol registered
with ``@[python "py_increment"]``.

LibraryRegistry — the full picture
-----------------------------------

``LibraryRegistry`` holds all types and functions for a loaded library:

.. code-block:: python

   >>> reg = LibraryRegistry.from_json_strings(funcs_json, types_json)
   >>> reg.types     # list[TypeInfo]
   >>> reg.funcs     # list[FuncInfo]
   >>> reg.find_type("Shape")  # Optional[TypeInfo]
   >>> reg.find_func("py_increment")  # Optional[FuncInfo]

The registry handles deduplication — recursive inductives may register
the same type multiple times, and the parser merges them.

API reference
-------------

.. autoclass:: lean_py.registry.TypeRepr
   :members:
   :show-inheritance:

.. autoclass:: lean_py.registry.CtorInfo
   :members:
   :show-inheritance:

.. autoclass:: lean_py.registry.TypeInfo
   :members:
   :show-inheritance:

.. autoclass:: lean_py.registry.FuncInfo
   :members:
   :show-inheritance:

.. autoclass:: lean_py.registry.LibraryRegistry
   :members:
   :show-inheritance:
