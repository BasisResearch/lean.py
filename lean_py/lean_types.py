"""
Higher level types wrapping Lean objects.
"""


# ============================================================================
# Higher-level Python Type Wrappers
# ============================================================================

from ctypes import POINTER, addressof
import ctypes
from lean_py.base_types import LeanArrayObject, LeanStringObject
from lean_py.lean_ffi import LeanFFI, lean_box


class LeanValue:
    """Base class for Python-friendly Lean value wrappers."""

    def __init__(self, ptr, ffi=None):
        """
        Initialize with a Lean object pointer.
        
        Args:
            ptr: Pointer to Lean object
            ffi: LeanFFI instance for managing the value
        """
        self.ptr = ptr
        self.ffi : LeanFFI | None = ffi

    def __del__(self):
        """Automatically decrement reference when Python object is garbage collected."""
        if self.ffi and self.ptr:
            self.ffi.dec_ref(self.ptr)


class LeanString(LeanValue):
    """Python wrapper for Lean strings."""

    def to_python_string(self):
        """Convert to Python string."""
        if self.ptr is None:
            return ""
        
        string_obj = ctypes.cast(self.ptr, POINTER(LeanStringObject)).contents
        if string_obj.m_size == 0:
            return ""
        m_data_start = addressof(string_obj) + LeanStringObject.m_data.offset
        
        # m_data is a pointer to char, get the raw bytes
        return ctypes.string_at(m_data_start, string_obj.m_size - 1).decode('utf-8')

    def __str__(self):
        return self.to_python_string()

    def __repr__(self):
        return f"LeanString({self.to_python_string()!r})"


class LeanArray(LeanValue):
    """Python wrapper for Lean arrays."""

    def size(self):
        """Get the size of the array."""
        array_obj = ctypes.cast(self.ptr, POINTER(LeanArrayObject)).contents
        return array_obj.m_size

    def get(self, index):
        """Get element at index."""
        array_obj = ctypes.cast(self.ptr, POINTER(LeanArrayObject)).contents
        if index < 0 or index >= array_obj.m_size:
            raise IndexError(f"Index {index} out of bounds for array of size {array_obj.m_size}")
        
        elem_ptr = array_obj.m_data[index]
        if self.ffi:
            self.ffi.inc_ref(elem_ptr)
        return LeanValue(elem_ptr, self.ffi)

    def to_python_list(self):
        """Convert to Python list."""
        return [self.get(i) for i in range(self.size())]

    def __len__(self):
        return self.size()

    def __getitem__(self, index):
        return self.get(index)


class LeanIOResult(LeanValue):
    """Python wrapper for Lean IO results."""

    def is_ok(self):
        """Check if result is Ok."""
        if self.ffi:
            return self.ffi.io_result_is_ok(self.ptr)
        return self.ptr.contents.m_tag == 0

    def is_error(self):
        """Check if result is Error."""
        return not self.is_ok()

    def get_or_raise(self):
        """
        Get the value if Ok, or raise an exception if Error.
        
        Raises:
            RuntimeError: If the result is an Error
        """
        if self.is_ok():
            # For Ok, the value is in the second field of the Result
            result_obj = ctypes.cast(self.ptr, POINTER(LeanArrayObject)).contents
            if result_obj.m_size > 0:
                val_ptr = result_obj.m_data[0]
                if self.ffi:
                    self.ffi.inc_ref(val_ptr)
                return LeanValue(val_ptr, self.ffi)
            return LeanValue(lean_box(0), self.ffi)
        else:
            # For Error, display and raise
            if self.ffi:
                self.ffi.io_result_show_error(self.ptr)
            raise RuntimeError("Lean IO error occurred")

