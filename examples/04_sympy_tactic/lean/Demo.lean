/-
Driver file that exercises the `sympy` tactic. Build the LeanPy +
SymPyTactic libraries first, then run with sympy on the host process's
PYTHONPATH so the in-Lean Python bridge can find it.

```bash
cd lean
lake build
LEANPY_LIBPYTHON=$(python -c 'import ctypes.util; print(ctypes.util.find_library("python3.12"))') \
  lake env lean Demo.lean
```
-/
import SymPyTactic

example : (1 : Int) + 1 = 2 := by sympy
example : (3 : Int) * 4 = 12 := by sympy
example : (5 : Int) * 6 = 30 := by sympy
