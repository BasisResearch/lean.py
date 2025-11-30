from pathlib import Path
import subprocess
import ctypes
import os

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


def lean_box(n):
    ptr_val = (n << 1) | 1
    return ctypes.cast(ctypes.c_void_p(ptr_val), ctypes.POINTER(LeanObject))

run_command(
    ["lake", "build"],
    cwd="../lean"
)


dylib_file = next(Path('../').rglob('*.dylib'))
get_symbols(dylib_file)

deps = ctypes.CDLL(dylib_file)

LEAN_PATH = Path(run_command(["lake", "env", "printenv", "LEAN_PATH"]))
leanshared_lib_file = LEAN_PATH / "libleanshared.dylib"
leanshared_lib = ctypes.CDLL(leanshared_lib_file)

init_pylean = deps.initialize_PyleanExample
init_pylean(1, lean_box(0))
# leanshared_lib.lean_initialize()

deps.py_bar(0)
