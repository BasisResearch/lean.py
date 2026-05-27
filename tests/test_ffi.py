import ctypes

from lean_py.lean_ffi import LeanFFI, get_lean_ffi
from lean_py.lean_types import LeanString


def test_ffi_can_be_created():
    ffi = get_lean_ffi()
    assert isinstance(ffi, LeanFFI)


def test_ffi_has_initialised():
    ffi = get_lean_ffi()
    isinstance(ffi.lean_initialize, ctypes._CFuncPtr)


def test_lean_string_wrap():
    ffi = get_lean_ffi()
    kiran_str = ffi.mk_string("kiran")
    obj = LeanString(kiran_str)
    assert str(obj) == "kiran"
