import ctypes
from pathlib import Path

from lean_py.base_types import LeanObject
from lean_py.lean_ffi import get_lean_ffi

from .lean_types import LeanFFI

class LeanLibrary:
    """
    Wrapper for a Lean library with Python bindings.
    """
    def __init__(self, dll_path: Path, library_name: str):
        """Loads and initialises a Lean Library"""
        self.ffi : LeanFFI = get_lean_ffi()
        self.library_name: str = library_name
        self.lib = ctypes.CDLL(dll_path, mode=ctypes.RTLD_GLOBAL)
        
    #     # Call the initialization function
        self._initialize_library()
        
    #     # Cache for function wrappers
    #     self._function_cache: Dict[str, Callable] = {}

    def _initialize_library(self):
        """
        Call the library initialization function.
        
        This calls initialize_<library_name> with builtin=1 to register
        all exported functions.
        
        Raises:
            RuntimeError: If initialization fails
        """
        init_func_name = f"initialize_{self.library_name}"
        try:
            init_func = getattr(self.lib, init_func_name)
            init_func.argtypes = [ctypes.c_uint8]
            init_func.restype = ctypes.POINTER(LeanObject)
            
            result = init_func(1)
            
    #         # Check if initialization succeeded
            if result.contents.m_tag == 0:
                # Success (IO Ok)
                self.ffi.dec_ref(result)
            else:
                # Error (IO Error)
                self.ffi.io_result_show_error(result)
                self.ffi.dec_ref(result)
                raise RuntimeError(f"Lean library initialization failed for {self.library_name}")
        except AttributeError:
            raise RuntimeError(
                f"Library does not have initialization function {init_func_name}. "
                f"Make sure the library was compiled with @[python] annotations."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize library {self.library_name}: {e}")

