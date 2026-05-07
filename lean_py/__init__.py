"""LeanPy: Python ↔ Lean 4 interop.

Load a compiled Lean 4 library that uses ``@[python]`` annotations and call
its functions directly from Python. Lean inductive types are automatically
marshalled to :class:`LeanInductiveValue` instances that support Python 3.10+
structural pattern matching::

    from lean_py import LeanLibrary

    lib = LeanLibrary.from_lake("./my-project", "MyLib", build=True)

    # Call an exported function
    result = lib.myFunction(42)

    # Pattern match on inductive types
    match lib.mkExpr():
        case lib.Expr.app(fn, arg):
            print(f"application: {fn} {arg}")
        case lib.Expr.const(name):
            print(f"constant: {name}")
"""

from lean_py.exceptions import LeanError, LeanPyCallbackError
from lean_py.kernel import GoalState, Kernel, TacticResult
from lean_py.library import LeanLibrary, Library
from lean_py.marshal import LeanInductiveValue, LeanObj, Marshaller
from lean_py.registry import (
    CtorInfo,
    FuncInfo,
    LibraryRegistry,
    TypeInfo,
    TypeRepr,
)

__all__ = [
    "LeanLibrary",
    "Library",
    "LeanObj",
    "LeanInductiveValue",
    "Marshaller",
    "LibraryRegistry",
    "TypeInfo",
    "TypeRepr",
    "CtorInfo",
    "FuncInfo",
    "LeanError",
    "LeanPyCallbackError",
    "Kernel",
    "GoalState",
    "TacticResult",
]
