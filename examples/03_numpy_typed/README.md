# 03 — Phantom-typed numpy from Lean

This example is a **pure Lean executable** that uses numpy as a
runtime dependency. The Lean side wraps `numpy.ndarray` in a
structure parameterised by phantom indices for dtype and shape:

```lean
structure NDArray (_dt : DType) (_shape : List Nat) : Type where
  pyref : Py
```

Operations carry their shape contract in the type:

```lean
def NDArray.matmul {dt} {m k n : Nat}
    (a : NDArray dt [m, k]) (b : NDArray dt [k, n]) : IO (NDArray dt [m, n])

def NDArray.transpose {dt} {m n : Nat}
    (a : NDArray dt [m, n]) : IO (NDArray dt [n, m])

def NDArray.reshape {dt old} (a : NDArray dt old) (new : List Nat)
    (_h : shapeSize old = shapeSize new := by decide) : IO (NDArray dt new)
```

Shape mismatches and dtype mismatches are **Lean type errors**.
Storage and arithmetic are forwarded to numpy via `LeanPy.Python` —
the phantom types are erased at runtime.

There is no Python driver. `lake build` produces a binary at
`lean/.lake/build/bin/demo`; the `run` wrapper at the example root
just sets `LEANPY_LIBPYTHON` to a `libpython3.X` and runs the binary
with `uv run` so numpy from the local venv is on `sys.path`.

## Layout

```
pyproject.toml           # numpy as a uv dependency
run                      # wrapper that sets LEANPY_LIBPYTHON & exec's demo
lean/
  Main.lean              # def main : IO Unit — runs three demos
  TypedNumpy.lean        # NDArray + typed wrappers around numpy
  lakefile.toml          # lean_lib + lean_exe
  lean-toolchain
```

## Run

```bash
uv sync     # installs numpy
./run
```

Or by hand, without the helper:

```bash
cd lean && lake build && cd ..
LEANPY_LIBPYTHON=$(python -c '
import os, sysconfig
libdir = sysconfig.get_config_var("LIBDIR")
soname = sysconfig.get_config_var("INSTSONAME") or sysconfig.get_config_var("LDLIBRARY")
print(os.path.join(libdir, soname))
') ./lean/.lake/build/bin/demo
```

Expected output:

```
demo_run:
  array([4., 4., 4., 4., 4., 4.])

demo_pipeline -> Array Float of length 4
  #[6.000000, 15.000000, 15.000000, 51.000000]

demo_explain:
  matmul (3,4) @ (4,5) -> shape inferred by Lean = [3, 5]; numpy says: ...
```

## Compile-time shape checks

Try uncommenting any of the `example` blocks at the bottom of
`TypedNumpy.lean` to see the type checker reject them:

```lean
-- inner dimensions disagree:
let a ← NDArray.ones .f64 [3, 4]
let b ← NDArray.ones .f64 [5, 2]
NDArray.matmul a b   -- expected NDArray .f64 [4, _], got [5, _]

-- dtypes disagree:
let a ← NDArray.ones .f32 [3, 4]
let b ← NDArray.ones .f64 [4, 2]
NDArray.matmul a b   -- expected NDArray .f32 [4, _], got .f64

-- reshape with wrong total size:
let v ← NDArray.arange .f64 6
NDArray.reshape v [5]   -- shapeSize [6] ≠ shapeSize [5]
```
