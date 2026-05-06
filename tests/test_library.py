from pathlib import Path

from lean_py import LeanLibrary
from lean_py.utils import add_lean_lib_to_dyld_path


def test_library():
    add_lean_lib_to_dyld_path()
    LeanLibrary.from_lake(Path(__file__).parent / "lean", "TestLib", build=True)
