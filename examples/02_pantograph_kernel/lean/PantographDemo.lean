/-
LeanPy.Kernel: a Pantograph-equivalent kernel facade exposed to Python.

Most of the surface lives in `LeanPy.Kernel` itself — this file only
re-exports a few @[python] stable names that the Python driver uses,
so the example doesn't break if the upstream LeanPy names get renamed.
For everything else, the python driver uses
`lib.leanpy_kernel_*` directly.
-/
import Lean
import LeanPy
import LeanPy.Kernel

namespace PantographDemo

/-- Stable @[python] aliases the demo driver expects. -/
@[python "demo_init_search"]
def initSearch (sp : String) : IO Unit :=
  LeanPy.Kernel.initSearch sp

@[python "demo_load_env"]
unsafe def loadEnv (modules : Array String) : IO Unit :=
  LeanPy.Kernel.loadEnv modules

end PantographDemo

#export_python_registry "PantographDemo"
