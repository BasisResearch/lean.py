"""
Lean FFI bindings.

The LeanFFI class and all its methods are created dynamically at runtime
by parsing lean.h — no generated files needed.
"""

from lean_py._runtime import get_lean_ffi, get_ffi_class

LeanFFI = get_ffi_class()

__all__ = ["LeanFFI", "get_lean_ffi"]
