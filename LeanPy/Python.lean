/-
Python-in-Lean: an opaque `Py` type backed by a `PyObject*` external object,
plus a small monadic API.

All operations live in `IO` because Python state is global and operations
can fail (exceptions surface as `IO.userError "...."`).

Operations that take a `Py` as the first argument live under the `Py`
namespace so Lean's dot syntax resolves: `(p : Py).getAttr "x"` elaborates
to `LeanPy.Python.Py.getAttr p "x"`. Operations that don't take a `Py`
receiver (initialisation, module-level helpers, builders that synthesise
a fresh `Py`) live in `LeanPy.Python` itself.

The implementation lives in C; this file declares the Lean-visible signatures.
The C code lives in `LeanPy/native/python_bridge.c` and is built into the
`LeanPy` static library. Loading the Python C library is deferred until the
first call to `LeanPy.Python.init`, so projects that don't use Python in
Lean pay no cost.
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

/-! ## Module-level operations

These are not methods on `Py` — they construct a fresh `Py` from scratch
or operate on the CPython runtime as a whole.
-/

/-- Initialise CPython. Idempotent; safe to call multiple times.
On first call, locates `libpython3.X` via known sonames, loads it,
calls `Py_Initialize`, and binds all needed CPython entry points by
`dlsym`. -/
@[extern "lean_py_initialize"]
opaque init : Unit → IO Unit

/-- Returns `true` if Python is initialised. -/
@[extern "lean_py_is_initialized"]
opaque isInitialized : Unit → IO Bool

/-! ### Module imports and code execution -/

/-- `import name`. -/
@[extern "lean_py_import"]  opaque import_  : @& String → IO Py

/-- Evaluate a Python expression in `__main__`'s namespace.
Returns the value of the expression. -/
@[extern "lean_py_eval"]    opaque eval     : @& String → IO Py

/-- Execute a Python statement (no return). -/
@[extern "lean_py_exec"]    opaque exec     : @& String → IO Unit

/-! ## `Py` namespace — operations on `Py` values

All functions here take a `Py` first (or none, in which case they act as
constructors) so they can be invoked via Lean's dot notation. -/

namespace Py

/-! ### Singletons -/

/-- `Py.None` — the Python `None` singleton. -/
@[extern "lean_py_none"]
opaque none : Unit → IO Py

/-- `Py.True` and `Py.False`. -/
@[extern "lean_py_true"]  opaque true_  : Unit → IO Py
@[extern "lean_py_false"] opaque false_ : Unit → IO Py

/-! ### Constructors: Lean → Python -/

@[extern "lean_py_of_bool"]   opaque ofBool   : Bool → IO Py
@[extern "lean_py_of_int64"]  opaque ofInt64  : @& Int → IO Py
@[extern "lean_py_of_float"]  opaque ofFloat  : Float → IO Py
@[extern "lean_py_of_string"] opaque ofString : @& String → IO Py
@[extern "lean_py_of_bytes"]  opaque ofBytes  : @& ByteArray → IO Py

/-- `Py.ofInt` is a synonym for `Py.ofInt64`. -/
abbrev ofInt : @& Int → IO Py := ofInt64

/-- Build a Python list from an Array of Py. -/
@[extern "lean_py_of_list"] opaque ofList : @& Array Py → IO Py

/-- Build a Python tuple from an Array of Py. -/
@[extern "lean_py_of_tuple"] opaque ofTuple : @& Array Py → IO Py

/-- Build a Python dict from an Array of (key, value) pairs.
The keys may be any hashable Python values; pass strings via `ofString`. -/
@[extern "lean_py_of_dict"] opaque ofDict : @& Array (Py × Py) → IO Py

/-- Convenience: build a Python dict whose keys are strings. -/
def ofStringDict (entries : Array (String × Py)) : IO Py := do
  let mut pairs : Array (Py × Py) := Array.emptyWithCapacity entries.size
  for (k, v) in entries do
    pairs := pairs.push (← ofString k, v)
  ofDict pairs

/-! ### Conversions: Python → Lean -/

@[extern "lean_py_to_bool"]   opaque toBool   : @& Py → IO Bool
@[extern "lean_py_to_int64"]  opaque toInt    : @& Py → IO Int
@[extern "lean_py_to_float"]  opaque toFloat  : @& Py → IO Float
@[extern "lean_py_to_string"] opaque toString' : @& Py → IO String
@[extern "lean_py_repr"]      opaque repr      : @& Py → IO String
@[extern "lean_py_str"]       opaque str       : @& Py → IO String

/-- Get the type name of a Python object (e.g. `"int"`, `"sympy.Symbol"`). -/
@[extern "lean_py_type_name"] opaque typeName : @& Py → IO String

/-! ### Attribute, item, and identity access -/

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

/-- Convenience: `getItem` with a string key. -/
def getItemStr (p : Py) (k : String) : IO Py := do
  getItem p (← ofString k)

/-- Convenience: `setItem` with a string key. -/
def setItemStr (p : Py) (k : String) (v : Py) : IO Unit := do
  setItem p (← ofString k) v

/-! ### Calling -/

/-- Call `f(*args)`. -/
@[extern "lean_py_call"]    opaque call     : @& Py → @& Array Py → IO Py
/-- Call `f(*args, **kwargs)`. -/
@[extern "lean_py_call_kw"] opaque callKw   : @& Py → @& Array Py → @& Array (String × Py) → IO Py

/-- Call a method `obj.name(*args)`. -/
def callMethod (p : Py) (name : String) (args : Array Py) : IO Py := do
  call (← getAttr p name) args

/-! ### Numeric operators -/

@[extern "lean_py_add"]   opaque add  : @& Py → @& Py → IO Py
@[extern "lean_py_sub"]   opaque sub  : @& Py → @& Py → IO Py
@[extern "lean_py_mul"]   opaque mul  : @& Py → @& Py → IO Py
@[extern "lean_py_div"]   opaque div  : @& Py → @& Py → IO Py
@[extern "lean_py_pow"]   opaque pow  : @& Py → @& Py → IO Py
@[extern "lean_py_neg"]   opaque neg  : @& Py → IO Py

/-! ### Lean closures as Python callables -/

/-- Wrap a Lean closure as a Python callable. The resulting `Py` is a Python
object whose `__call__` invokes the closure with the positional arguments
unpacked into an `Array Py`. Keyword arguments are accepted but ignored at
the closure level (use `fromLeanCallableKw` to access them).

Each invocation runs in IO; exceptions raised by the closure surface to the
Python caller as `RuntimeError`s carrying the Lean error message. -/
@[extern "leanpy_make_callable"]
opaque fromLeanCallable : (@& Array Py → IO Py) → IO Py

/-- Like `fromLeanCallable` but the closure also receives the kwargs
dict. -/
@[extern "leanpy_make_callable_kw"]
opaque fromLeanCallableKw : (@& Array Py → @& Array (String × Py) → IO Py) → IO Py

end Py

/-! ## Exception handling

Python exceptions raised inside a `LeanPy.Python.*` call surface as
`IO.userError` whose payload is `"<TypeName>: <message>"`. Use
`tryCatchPy` to recover with access to the original Python type name.
-/

/-- A decoded Python exception caught at the Lean→Python boundary.
The C bridge formats the original CPython exception as
`"<typeName>: <message>"`; this struct is the parsed form. -/
structure PyException where
  /-- Name of the Python exception class (e.g. `"KeyError"`). -/
  typeName : String
  /-- `str(exc)` from the Python side. -/
  message  : String
  deriving Inhabited, Repr

/-- Parse the `IO.userError` message left by the bridge. Returns a
`PyException`. If the message doesn't have the expected shape (no `": "`
separator, or a leading non-CamelCase token) we treat the whole message
as the body and the type name as `"PythonError"`. -/
def parsePyExceptionMessage (raw : String) : PyException :=
  match raw.splitOn ": " with
  | typeName :: rest =>
    if typeName.isEmpty then
      { typeName := "PythonError", message := raw }
    else if typeName.any (fun c => c == ' ' || c == '\t' || c == '\n') then
      { typeName := "PythonError", message := raw }
    else
      { typeName, message := ": ".intercalate rest }
  | [] => { typeName := "PythonError", message := raw }

/-- Like `IO`'s `try/catch` but presents the caught Python exception in
parsed form. Non-Python errors are also caught and surface with
`typeName = "PythonError"` and the raw message body. -/
def tryCatchPy {α} (act : IO α) (handler : PyException → IO α) : IO α := do
  try
    act
  catch e =>
    let raw := toString e
    let exc := parsePyExceptionMessage raw
    handler exc

/-! ## Backwards-compatibility aliases

The pre-Phase-1 API located these operations directly under `LeanPy.Python`.
We keep abbrev aliases so existing code keeps building, but new code should
prefer the dot-syntax form. -/

@[deprecated Py.none (since := "2026-05-05")] abbrev none      := Py.none
@[deprecated Py.true_ (since := "2026-05-05")] abbrev true_     := Py.true_
@[deprecated Py.false_ (since := "2026-05-05")] abbrev false_    := Py.false_
@[deprecated Py.ofBool (since := "2026-05-05")] abbrev ofBool    := Py.ofBool
@[deprecated Py.ofInt64 (since := "2026-05-05")] abbrev ofInt64   := Py.ofInt64
@[deprecated Py.ofFloat (since := "2026-05-05")] abbrev ofFloat   := Py.ofFloat
@[deprecated Py.ofString (since := "2026-05-05")] abbrev ofString  := Py.ofString
@[deprecated Py.ofBytes (since := "2026-05-05")] abbrev ofBytes   := Py.ofBytes
@[deprecated Py.ofList (since := "2026-05-05")] abbrev ofList    := Py.ofList
@[deprecated Py.ofTuple (since := "2026-05-05")] abbrev ofTuple   := Py.ofTuple
@[deprecated Py.ofDict (since := "2026-05-05")] abbrev ofDict    := Py.ofDict
@[deprecated Py.toBool (since := "2026-05-05")] abbrev toBool    := Py.toBool
@[deprecated Py.toInt (since := "2026-05-05")] abbrev toInt     := Py.toInt
@[deprecated Py.toFloat (since := "2026-05-05")] abbrev toFloat   := Py.toFloat
@[deprecated Py.toString' (since := "2026-05-05")] abbrev toString' := Py.toString'
@[deprecated Py.repr (since := "2026-05-05")] abbrev repr      := Py.repr
@[deprecated Py.str (since := "2026-05-05")] abbrev str       := Py.str
@[deprecated Py.typeName (since := "2026-05-05")] abbrev typeName  := Py.typeName
@[deprecated Py.getAttr (since := "2026-05-05")] abbrev getAttr   := Py.getAttr
@[deprecated Py.setAttr (since := "2026-05-05")] abbrev setAttr   := Py.setAttr
@[deprecated Py.hasAttr (since := "2026-05-05")] abbrev hasAttr   := Py.hasAttr
@[deprecated Py.getItem (since := "2026-05-05")] abbrev getItem   := Py.getItem
@[deprecated Py.setItem (since := "2026-05-05")] abbrev setItem   := Py.setItem
@[deprecated Py.length (since := "2026-05-05")] abbrev length    := Py.length
@[deprecated Py.eq (since := "2026-05-05")] abbrev eq        := Py.eq
@[deprecated Py.is_ (since := "2026-05-05")] abbrev is_       := Py.is_
@[deprecated Py.call (since := "2026-05-05")] abbrev call      := Py.call
@[deprecated Py.callKw (since := "2026-05-05")] abbrev callKw    := Py.callKw
@[deprecated Py.add (since := "2026-05-05")] abbrev add       := Py.add
@[deprecated Py.sub (since := "2026-05-05")] abbrev sub       := Py.sub
@[deprecated Py.mul (since := "2026-05-05")] abbrev mul       := Py.mul
@[deprecated Py.div (since := "2026-05-05")] abbrev div       := Py.div
@[deprecated Py.pow (since := "2026-05-05")] abbrev pow       := Py.pow
@[deprecated Py.neg (since := "2026-05-05")] abbrev neg       := Py.neg

end LeanPy.Python
