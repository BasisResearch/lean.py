import ctypes
import functools
from ctypes import c_int, c_char_p, c_size_t, c_void_p, _CFuncPtr # type: ignore
from lean_py.utils import find_lean_dynlib
from lean_py.base_types import LeanObject, LeanObjectPtr, LeanObjectPtrTy

_ffi_initialized = False

# ============================================================================
# Lean Library FFI Interface
# ============================================================================
class LeanFFI:
    """Wrapper around Lean C library functions.
    This class loads the libleanshared library and provides access to core FFI functions.

    You should not create it yourself and instead use `get_lean_ffi()`
    to get an instance of this class.

    """
    lean_dec_ref_cold : _CFuncPtr

    # Object creation and deletion
    lean_alloc_object : _CFuncPtr
    lean_free_object : _CFuncPtr

    # String operations
    lean_mk_string : _CFuncPtr
    lean_mk_string_unchecked : _CFuncPtr
    lean_mk_string_from_bytes : _CFuncPtr

    # Array operations
    lean_array_mk : _CFuncPtr
    lean_array_push : _CFuncPtr

    # Object size
    lean_object_byte_size : _CFuncPtr
    lean_object_data_byte_size : _CFuncPtr

    lean_io_result_show_error : _CFuncPtr

    lean_initialize : _CFuncPtr

    def __init__(self):
        """
        Initialize FFI bindings by loading the libleanshared library.
        
        Args:
            lib_path: Path to libleanshared (dylib, so, or dll)
        """
        lib_path = find_lean_dynlib()
        self.lib = ctypes.CDLL(lib_path, mode=ctypes.RTLD_GLOBAL)
        self._setup_functions()
        global _ffi_initialized
        if not _ffi_initialized:
            _ffi_initialized = True
            self.lean_initialize()

    def _setup_functions(self):
        """Configure return types and argtypes for Lean FFI functions."""

        self.lean_initialize = self.lib.lean_initialize
        
        # Reference counting
        self.lean_dec_ref_cold = self.lib.lean_dec_ref_cold
        self.lean_dec_ref_cold.argtypes = [LeanObjectPtr]

        # Object creation and deletion
        self.lean_alloc_object = self.lib.lean_alloc_object
        self.lean_alloc_object.argtypes = [c_size_t]
        self.lean_alloc_object.restype = LeanObjectPtr

        self.lean_free_object = self.lib.lean_free_object
        self.lean_free_object.argtypes = [LeanObjectPtr]

        # String operations
        self.lean_mk_string = self.lib.lean_mk_string
        self.lean_mk_string.argtypes = [c_char_p]
        self.lean_mk_string.restype = LeanObjectPtr
        
        self.lean_mk_string_unchecked = self.lib.lean_mk_string_unchecked
        self.lean_mk_string_unchecked.argtypes = [c_char_p, c_size_t, c_size_t]
        self.lean_mk_string_unchecked.restype = LeanObjectPtr
        
        self.lean_mk_string_from_bytes = self.lib.lean_mk_string_from_bytes
        self.lean_mk_string_from_bytes.argtypes = [c_char_p, c_size_t]
        self.lean_mk_string_from_bytes.restype = LeanObjectPtr

        # Array operations
        self.lean_array_mk = self.lib.lean_array_mk
        self.lean_array_mk.argtypes = [LeanObjectPtr]
        self.lean_array_mk.restype = LeanObjectPtr
        
        self.lean_array_push = self.lib.lean_array_push
        self.lean_array_push.argtypes = [LeanObjectPtr, LeanObjectPtr]
        self.lean_array_push.restype = LeanObjectPtr

        # Object size
        self.lean_object_byte_size = self.lib.lean_object_byte_size
        self.lean_object_byte_size.argtypes = [LeanObjectPtr]
        self.lean_object_byte_size.restype = c_size_t

        self.lean_object_data_byte_size = self.lib.lean_object_data_byte_size
        self.lean_object_data_byte_size.argtypes = [LeanObjectPtr]
        self.lean_object_data_byte_size.restype = c_size_t

        self.lean_io_result_show_error = self.lib.lean_io_result_show_error
        self.lean_io_result_show_error.argtypes = [LeanObjectPtr]


    def inc_ref(self, obj: LeanObjectPtrTy):
        """Increment reference counter of a Lean object."""
        if self.lean_is_st(obj):
            obj.contents.m_rc += 1
        elif obj.contents.m_rc != 0:
            # For multi-threaded objects, use atomic decrement
            raise RuntimeError("Reference counting for atomic operations isn't currently supported.")

    def dec_ref(self, obj: LeanObjectPtrTy):
        """Decrement reference counter of a Lean object."""
        if self.lean_is_st(obj):
            obj.contents.m_rc -= 1
            if obj.contents.m_rc == 0:
                self.lean_free_object(obj)
        elif obj.contents.m_rc != 0:
            # For multi-threaded objects or cold path
            self.lean_dec_ref_cold(obj)

    def mk_string(self, s) -> LeanObjectPtrTy:
        """Create a Lean string from a Python string."""
        if isinstance(s, str):
            s = s.encode('utf-8')
        return self.lean_mk_string(s)

    def io_result_is_ok(self, res) -> bool:
        """Check if an IO result is Ok (tag == 0)."""
        return res.contents.m_tag == 0

    def io_result_show_error(self, res):
        """Display an IO error result."""
        self.lean_io_result_show_error(res)


    def lean_box(self, n):
        """
        Box an integer into a Lean object pointer.
        Small integers are directly encoded in the pointer value.
        Formula: (n << 1) | 1
        """
        n = ctypes.cast(n, c_void_p).value or 0
        ptr_val = (n << 1) | 1
        return ctypes.cast(ctypes.c_void_p(ptr_val), LeanObjectPtr)

    def lean_unbox(self, obj):
        """
        Unbox a Lean object pointer back to an integer.
        Formula: (pointer >> 1)
        """
        ptr_value = ctypes.cast(obj, c_void_p).value or 0
        return ptr_value >> 1

    def lean_is_scalar(self, obj):
        """Check if a Lean object is a scalar (boxed integer)."""
        ptr_value = ctypes.cast(obj, c_void_p).value or 0 
        return (ptr_value & 1) == 1

    def lean_is_mt(self, obj):
        """Check if object is multi-threaded (m_rc < 0)."""
        return obj.contents.m_rc < 0

    def lean_is_st(self, obj):
        """Check if object is single-threaded (m_rc > 0)."""
        return obj.contents.m_rc > 0

    def lean_is_persistent(self, obj):
        """Check if object's reference counting is not needed (m_rc == 0)."""
        return obj.contents.m_rc == 0

    def lean_has_rc(self, obj):
        """Check if object has reference counting (m_rc != 0)."""
        return obj.contents.m_rc != 0

    def lean_ptr_tag(self, obj):
        """Get the tag of a Lean object."""
        return obj.contents.m_tag

    def lean_ptr_other(self, obj):
        """Get the 'other' field of a Lean object."""
        return obj.contents.m_other




@functools.lru_cache(maxsize=1)
def get_lean_ffi() -> LeanFFI:
    return LeanFFI()
