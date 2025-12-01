from lean_py.library import LeanLibrary
from tests.utils import find_examples_dylib

def test_library():
    dylib = find_examples_dylib()
    lib = LeanLibrary(dylib, "PyleanExample")
