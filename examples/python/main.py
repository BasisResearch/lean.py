from pathlib import Path
import subprocess
import ctypes
import os
import sys

def run_command(args: list[str], **kwargs) -> str:
    """Run command specified by `args` and return the result"""
    res = subprocess.run(args, capture_output=True, **kwargs)
    return bytes.decode(res.stdout).strip()

def get_symbols(dylib: Path) -> list[str]:
    return run_command(["nm", "-j", str(dylib.absolute())]).splitlines()

class LeanObject(ctypes.Structure):
    _fields_ = [
        ("m_rc", ctypes.c_int),
        ("_bits", ctypes.c_uint32),  # holds m_cs_sz:16, m_other:8, m_tag:8
    ]

    @property
    def m_cs_sz(self):
        return self._bits & 0xFFFF

    @property
    def m_other(self):
        return (self._bits >> 16) & 0xFF

    @property
    def m_tag(self):
        return (self._bits >> 24) & 0xFF

def lean_object(ptr_val):
    return ctypes.cast(ctypes.c_void_p(ptr_val), ctypes.POINTER(LeanObject))

def lean_box(n):
    ptr_val = (n << 1) | 1
    return ctypes.cast(ctypes.c_void_p(ptr_val), ctypes.POINTER(LeanObject))

print("Building Lean library", file=sys.stderr)
run_command(
    ["lake", "build"],
    cwd="../lean"
)

print("Finding dylib", file=sys.stderr)
dylib_file = next(Path('../').rglob('*.dylib'))
print(f"Found: {dylib_file}", file=sys.stderr)

symbols = get_symbols(dylib_file)

print("Loading dylib with ctypes", file=sys.stderr)
deps = ctypes.CDLL(str(dylib_file), mode=ctypes.RTLD_GLOBAL)

print("Finding leanshared library", file=sys.stderr)
LEAN_PATH = Path(run_command(["lake", "env", "printenv", "LEAN_PATH"]))
leanshared_lib_file = LEAN_PATH / "libleanshared.dylib"

print("Loading leanshared with ctypes", file=sys.stderr)
leanshared_lib = ctypes.CDLL(str(leanshared_lib_file), mode=ctypes.RTLD_GLOBAL)

print("Initializing Lean runtime", file=sys.stderr)
# Initialize Lean runtime first
lean_initialize = leanshared_lib.lean_initialize
lean_initialize()

print("Getting initialize_PyleanExample", file=sys.stderr)
init_pylean = deps.initialize_PyleanExample

print("Calling initialize_PyleanExample(1, lean_box(0))", file=sys.stderr)
result = init_pylean(1, lean_box(0))
print(f"init_pylean result: {result}", file=sys.stderr)

print("Calling py_bar(0)", file=sys.stderr)
result = deps.py_bar(lean_box(0))
print(f"py_bar result: {result}", file=sys.stderr)

result = lean_object(deps.py_foo(lean_box(100), lean_box(0)))
print(f"py_foo result: {result}", file=sys.stderr)

print("SUCCESS: Script completed without crash!")
