/-
Driver file that exercises the `knuckle` tactic.

```bash
cd lean
lake build
LEANPY_LIBPYTHON=$(python -c 'import ctypes.util; print(ctypes.util.find_library("python3.12"))') \
  lake env lean Demo.lean
```
-/
import KnuckleTactic

example : (1 : Int) + 1 = 2 := by knuckle
example : (3 : Int) * 4 = 12 := by knuckle
example : (5 : Int) * 6 = 30 := by knuckle
