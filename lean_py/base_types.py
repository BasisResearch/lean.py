"""
Base python types wrapping Lean objects from FFI.

All struct types and constants are created dynamically at import time
by parsing lean.h. This module provides stable names for downstream use.
"""

from __future__ import annotations

from ctypes import POINTER, _Pointer

from lean_py._runtime import get_structs, get_constants

# Dynamically created struct types
_structs = get_structs()
_constants = get_constants()

# Core types
lean_object = _structs["lean_object"]
LeanObject = lean_object
LeanObjectPtr = _structs["_LeanObjectPtr"]
type LeanObjectPtrTy = _Pointer

# Struct types
LeanCtorObject = _structs.get("lean_ctor_object")
LeanArrayObject = _structs.get("lean_array_object")
LeanSArrayObject = _structs.get("lean_sarray_object")
LeanStringObject = _structs.get("lean_string_object")
LeanClosureObject = _structs.get("lean_closure_object")
LeanRefObject = _structs.get("lean_ref_object")
LeanThunkObject = _structs.get("lean_thunk_object")

# Constants
LeanMaxCtorTag = _constants.get("LeanMaxCtorTag", 243)
LeanPromise = _constants.get("LeanPromise", 244)
LeanClosure = _constants.get("LeanClosure", 245)
LeanArray = _constants.get("LeanArray", 246)
LeanStructArray = _constants.get("LeanStructArray", 247)
LeanScalarArray = _constants.get("LeanScalarArray", 248)
LeanString = _constants.get("LeanString", 249)
LeanMPZ = _constants.get("LeanMPZ", 250)
LeanThunk = _constants.get("LeanThunk", 251)
LeanTask = _constants.get("LeanTask", 252)
LeanRef = _constants.get("LeanRef", 253)
LeanExternal = _constants.get("LeanExternal", 254)
LeanReserved = _constants.get("LeanReserved", 255)

# Legacy LEAN_TAG_ aliases
LEAN_TAG_MAXCTOR = LeanMaxCtorTag
LEAN_TAG_PROMISE = LeanPromise
LEAN_TAG_CLOSURE = LeanClosure
LEAN_TAG_ARRAY = LeanArray
LEAN_TAG_STRUCT_ARRAY = LeanStructArray
LEAN_TAG_SCALAR_ARRAY = LeanScalarArray
LEAN_TAG_STRING = LeanString
LEAN_TAG_MPZ = LeanMPZ
LEAN_TAG_THUNK = LeanThunk
LEAN_TAG_TASK = LeanTask
LEAN_TAG_REF = LeanRef
LEAN_TAG_EXTERNAL = LeanExternal
LEAN_TAG_RESERVED = LeanReserved
