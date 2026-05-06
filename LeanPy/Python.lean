/-
Python-in-Lean: an opaque `Py` type backed by a `PyObject*` external object,
plus a small monadic API.

All operations live in `IO` because Python state is global and operations
can fail (exceptions surface as `IO.userError "...."`).

The implementation lives in C; this file declares the Lean-visible signatures.
The C code lives in `LeanPy/native/python_bridge.c` and is built into the
`LeanPy` static library. Loading the Python C library is deferred until the
first call to `Python.initialize`, so projects that don't use Python in Lean
pay no cost.
-/
import LeanPy.Registry
import LeanPy.Attr

namespace LeanPy.Python

/-- Opaque Python object handle. Lean only sees this as an `External`
object class. The reference count is the Lean refcount on the wrapper;
the wrapper owns one Python reference, released by the finaliser. -/
opaque PyObjectPointed : NonemptyType
def Py : Type := PyObjectPointed.type
instance : Nonempty Py := PyObjectPointed.property

/-- Initialise CPython. Idempotent; safe to call multiple times.
On first call, locates `libpython3.X` via known sonames, loads it,
calls `Py_Initialize`, and binds all needed CPython entry points by
`dlsym`. -/
@[extern "lean_py_initialize"]
opaque init : Unit → IO Unit

/-- Returns `true` if Python is initialised. -/
@[extern "lean_py_is_initialized"]
opaque isInitialized : Unit → IO Bool

/-- `Py.None` — the Python `None` singleton. -/
@[extern "lean_py_none"]
opaque none : Unit → IO Py

/-- `Py.True` and `Py.False`. -/
@[extern "lean_py_true"]  opaque true_  : Unit → IO Py
@[extern "lean_py_false"] opaque false_ : Unit → IO Py

/-! ### Conversions: Lean → Python -/

@[extern "lean_py_of_bool"]   opaque ofBool   : Bool → IO Py
@[extern "lean_py_of_int64"]  opaque ofInt64  : @& Int → IO Py
@[extern "lean_py_of_float"]  opaque ofFloat  : Float → IO Py
@[extern "lean_py_of_string"] opaque ofString : @& String → IO Py
@[extern "lean_py_of_bytes"]  opaque ofBytes  : @& ByteArray → IO Py

/-- Build a Python list from an Array of Py. -/
@[extern "lean_py_of_list"] opaque ofList : @& Array Py → IO Py

/-- Build a Python tuple from an Array of Py. -/
@[extern "lean_py_of_tuple"] opaque ofTuple : @& Array Py → IO Py

/-- Build a Python dict from an Array of (key, value) pairs. -/
@[extern "lean_py_of_dict"] opaque ofDict : @& Array (Py × Py) → IO Py

/-! ### Conversions: Python → Lean -/

@[extern "lean_py_to_bool"]   opaque toBool   : @& Py → IO Bool
@[extern "lean_py_to_int64"]  opaque toInt    : @& Py → IO Int
@[extern "lean_py_to_float"]  opaque toFloat  : @& Py → IO Float
@[extern "lean_py_to_string"] opaque toString' : @& Py → IO String
@[extern "lean_py_repr"]      opaque repr      : @& Py → IO String
@[extern "lean_py_str"]       opaque str       : @& Py → IO String

/-- Get the type name of a Python object (e.g. `"int"`, `"sympy.Symbol"`). -/
@[extern "lean_py_type_name"] opaque typeName : @& Py → IO String

/-! ### Object access -/

@[extern "lean_py_getattr"] opaque getAttr  : @& Py → @& String → IO Py
@[extern "lean_py_setattr"] opaque setAttr  : @& Py → @& String → @& Py → IO Unit
@[extern "lean_py_hasattr"] opaque hasAttr  : @& Py → @& String → IO Bool

@[extern "lean_py_getitem"] opaque getItem  : @& Py → @& Py → IO Py
@[extern "lean_py_setitem"] opaque setItem  : @& Py → @& Py → @& Py → IO Unit

@[extern "lean_py_length"]  opaque length   : @& Py → IO Int

/-- Equality (`==`). -/
@[extern "lean_py_eq"]      opaque eq       : @& Py → @& Py → IO Bool
/-- Identity (`is`). -/
@[extern "lean_py_is"]      opaque is_      : @& Py → @& Py → IO Bool

/-! ### Calling -/

/-- Call `f(*args)`. -/
@[extern "lean_py_call"]    opaque call     : @& Py → @& Array Py → IO Py
/-- Call `f(*args, **kwargs)`. -/
@[extern "lean_py_call_kw"] opaque callKw   : @& Py → @& Array Py → @& Array (String × Py) → IO Py

/-! ### Modules and globals -/

/-- `import name`. -/
@[extern "lean_py_import"]  opaque import_  : @& String → IO Py

/-- Evaluate a Python expression in a fresh module-scoped namespace.
Returns the value of the expression. -/
@[extern "lean_py_eval"]    opaque eval     : @& String → IO Py

/-- Execute a Python statement (no return). -/
@[extern "lean_py_exec"]    opaque exec     : @& String → IO Unit

/-! ### Numeric operators -/

@[extern "lean_py_add"]   opaque add  : @& Py → @& Py → IO Py
@[extern "lean_py_sub"]   opaque sub  : @& Py → @& Py → IO Py
@[extern "lean_py_mul"]   opaque mul  : @& Py → @& Py → IO Py
@[extern "lean_py_div"]   opaque div  : @& Py → @& Py → IO Py
@[extern "lean_py_pow"]   opaque pow  : @& Py → @& Py → IO Py
@[extern "lean_py_neg"]   opaque neg  : @& Py → IO Py

end LeanPy.Python
