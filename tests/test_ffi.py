import ctypes

from lean_py.lean_ffi import LeanFFI, get_lean_ffi


def _lean_string_to_py(ffi, ptr) -> str:
    """Decode a Lean string object into a Python str via the safe ffi path."""
    size = ffi.lean_string_size(ptr)
    if size <= 1:
        return ""
    cstr = ffi.lean_string_cstr(ptr)
    raw = cstr.value if isinstance(cstr, ctypes.c_char_p) else cstr
    return (raw or b"").decode("utf-8")


def test_ffi_can_be_created():
    ffi = get_lean_ffi()
    assert isinstance(ffi, LeanFFI)


def test_ffi_has_initialised():
    ffi = get_lean_ffi()
    isinstance(ffi.lean_initialize, ctypes._CFuncPtr)


def test_lean_string_wrap():
    ffi = get_lean_ffi()
    kiran_str = ffi.mk_string("kiran")
    try:
        assert _lean_string_to_py(ffi, kiran_str) == "kiran"
    finally:
        ffi.lean_dec(kiran_str)
