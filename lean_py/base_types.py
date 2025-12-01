"""
Base python types wrapping Lean objects from FFI.
"""

from __future__ import annotations

import ctypes
from ctypes import (
    POINTER,
    Structure,
    _Pointer,
    c_int,
    c_size_t,
    c_uint8,
    c_uint16,
    c_uint32,
    c_void_p,
)


class LeanObject(Structure):
    """
    Python representation of lean_object from lean.h.
    """
    _fields_ = [
        ("m_rc", c_int),                    # Reference counter
        ("m_cs_sz", c_uint32, 16),         # Compact size (16 bits)
        ("m_other", c_uint32, 8),          # Other field (8 bits)
        ("m_tag", c_uint32, 8),            # Tag (8 bits)
    ]

# Define pointer type after the structure
type LeanObjectPtrTy = _Pointer[LeanObject]
LeanObjectPtr = POINTER(LeanObject)

class LeanCtorObject(Structure):
    """Python representation of lean_array_object from lean.h:176."""
    _fields_ = [
        ("m_header", LeanObject),
        ("m_data", LeanObjectPtr) # first of an array depending on the inductive type
    ]


class LeanArrayObject(Structure):
    """Python representation of lean_array_object from lean.h:176."""
    _fields_ = [
        ("m_header", LeanObject),
        ("m_size", c_size_t),
        ("m_capacity", c_size_t),
        ("m_data", LeanObjectPtr) # first of an array of size size
    ]

class LeanSArrayObject(Structure):
    """Python representation of lean_sarray_object from lean.h:184."""
    _fields_ = [
        ("m_header", LeanObject),
        ("m_size", c_size_t),
        ("m_capacity", c_size_t),
        ("m_data", c_uint8)     # first of an array of size size
    ]

class LeanStringObject(Structure):
    """
    Python representation of lean_string_object from lean.h:191.
    """
    _fields_ = [
        ("m_header", LeanObject),
        ("m_size", c_size_t),              # Byte length including '\0' terminator
        ("m_capacity", c_size_t),
        ("m_length", c_size_t),            # UTF-8 length
        ("m_data", ctypes.c_char),
    ]

class LeanClosureObject(Structure):
    """
    Python representation of lean_closure_object from lean.h:199.
    """
    _fields_ = [
        ("m_header", LeanObject),
        ("m_fun", c_void_p),              # Byte length including '\0' terminator
        ("m_arity", c_uint16),
        ("m_num_fixed", c_uint16),            # no fixed args
        ("m_objs", LeanObjectPtr),            # first of fixed args
    ]

class LeanRefObject(Structure):
    """Python representation of lean_ref_object from lean.h:207."""
    _fields_ = [
        ("m_header", LeanObject),
        ("m_value", LeanObjectPtr),
    ]

class LeanThunkObject(Structure):
    """Python representation of lean_ref_object from lean.h:212."""
    _fields_ = [
        ("m_header", LeanObject),
        ("m_value", LeanObjectPtr),
        ("m_closure", LeanObjectPtr),
    ]

# ============================================================================
# Tag Constants (from lean.h:83-95)
# ============================================================================

LEAN_TAG_MAXCTOR = 243
LEAN_TAG_PROMISE = 244
LEAN_TAG_CLOSURE = 245
LEAN_TAG_ARRAY = 246
LEAN_TAG_STRUCT_ARRAY = 247
LEAN_TAG_SCALAR_ARRAY = 248
LEAN_TAG_STRING = 249
LEAN_TAG_MPZ = 250
LEAN_TAG_THUNK = 251
LEAN_TAG_TASK = 252
LEAN_TAG_REF = 253
LEAN_TAG_EXTERNAL = 254
LEAN_TAG_RESERVED = 255


