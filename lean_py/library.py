"""
LeanPy Library - Main interface for loading and calling Lean code from Python.

This module provides the Library class which:
1. Loads libleanshared and initializes the Lean runtime
2. Loads user libraries compiled with @[python] annotations
3. Provides access to exported Lean functions via Python
"""

import ctypes
import os
from pathlib import Path
from typing import Callable, Dict, Optional

from lean_py.utils import run_command

from .lean_types import POINTER, LeanFFI, LeanIOResult, LeanObject, lean_box

# Global state to track if Lean has been initialized
_lean_initialized = False
_lean_ffi: Optional[LeanFFI] = None

class Library:
    """
    Wrapper for a Lean library with Python bindings.
    
    This class handles loading a compiled Lean library and accessing functions
    marked with @[python "name"] annotation.
    
    Example:
        lib = LeanPy.Library("./build/output.dylib", "MyLibrary")
        result = lib.my_function(arg1, arg2)
    """

    def __init__(self, dll_path: str, library_name: str, lean_path: Optional[str] = None):
        """
        Load and initialize a Lean library.
        
        Args:
            dll_path: Path to the compiled Lean library (.dylib, .so, or .dll)
            library_name: Name of the library (used to find initialize function)
            lean_path: Optional path to Lean toolchain directory
            
        Raises:
            RuntimeError: If library cannot be loaded or initialization fails
        """
        global _lean_ffi, _lean_initialized
        
        # Initialize global Lean FFI and runtime if needed
        if _lean_ffi is None:
            leanshared_path = _find_libleanshared(lean_path)
            _lean_ffi = LeanFFI(leanshared_path)
            _initialize_lean_runtime(_lean_ffi)
        
        self.ffi = _lean_ffi
        self.library_name = library_name
        self.dll_path = str(dll_path)
        
        # Load the user library
        try:
            self.lib = ctypes.CDLL(self.dll_path, mode=ctypes.RTLD_GLOBAL)
        except Exception as e:
            raise RuntimeError(f"Failed to load library {dll_path}: {e}")
        
        # Call the initialization function
        self._initialize_library()
        
        # Cache for function wrappers
        self._function_cache: Dict[str, Callable] = {}

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
            init_func.restype = POINTER(LeanObject)
            
            # Call with builtin=1 (same as Lean executables)
            result = init_func(1)
            
            # Check if initialization succeeded
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

    def _wrap_function(self, func_name: str, num_args: int) -> Callable:
        """
        Create a wrapper for a Lean function that handles boxing/unboxing.
        
        Args:
            func_name: Name of the exported Lean function
            num_args: Number of arguments the function takes
            
        Returns:
            A callable that takes Python objects and returns results
        """
        # Get the raw function
        try:
            raw_func = getattr(self.lib, f"py_{func_name}")
        except AttributeError:
            # Try without 'py_' prefix
            raw_func = getattr(self.lib, func_name)
        
        raw_func.argtypes = [POINTER(LeanObject)] * num_args
        raw_func.restype = POINTER(LeanObject)

        def wrapper(*args):
            """Call the Lean function and wrap the result."""
            if len(args) != num_args:
                raise TypeError(
                    f"{func_name} takes {num_args} arguments but {len(args)} were given"
                )
            
            # Convert Python arguments to Lean objects
            lean_args = []
            for arg in args:
                if isinstance(arg, int):
                    lean_args.append(lean_box(arg))
                elif isinstance(arg, str):
                    lean_args.append(self.ffi.mk_string(arg))
                else:
                    # Assume it's already a Lean object pointer
                    lean_args.append(arg)
            
            # Call the Lean function
            result = raw_func(*lean_args)
            
            # Wrap result and return
            return LeanIOResult(result, self.ffi)
        
        return wrapper

    def get_function(self, func_name: str, num_args: int = 1) -> Callable:
        """
        Get a wrapper for an exported Lean function.
        
        Args:
            func_name: Name of the exported function (without 'py_' prefix)
            num_args: Number of arguments (default: 1)
            
        Returns:
            A callable wrapper that handles calling the Lean function
        """
        cache_key = f"{func_name}_{num_args}"
        if cache_key not in self._function_cache:
            self._function_cache[cache_key] = self._wrap_function(func_name, num_args)
        return self._function_cache[cache_key]

    def __getattr__(self, name: str) -> Callable:
        """
        Access exported functions as attributes.
        
        Example:
            result = lib.my_function(42)
        
        This will look for a function named 'py_my_function' or 'my_function'
        in the library and return a wrapper for it.
        """
        if name.startswith('_'):
            raise AttributeError(f"No attribute {name}")
        
        # Try to find the function
        full_name = f"py_{name}"
        try:
            getattr(self.lib, full_name)
        except AttributeError:
            try:
                getattr(self.lib, name)
            except AttributeError:
                raise AttributeError(f"Library has no exported function '{name}'")
        
        # Return a wrapper that will dynamically determine argument count
        # For now, default to 1 argument
        return self.get_function(name, num_args=1)
