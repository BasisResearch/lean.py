/-
The pantograph-style kernel surface is now part of `LeanPy.Kernel`
itself, so this Lean library only needs to import `LeanPy.Kernel`
and emit the Python registry. All the operations
(`leanpy_kernel_*`) come from upstream and are immediately usable
from Python via `lean_py.kernel.Kernel`.
-/
import LeanPy
import LeanPy.Kernel

#export_python_registry "PantographDemo"
