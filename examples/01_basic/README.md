# 01 — Basic example

The smallest end-to-end demo. The Lean side declares a few `@[python]`
functions, an inductive, and a structure; the Python side loads the
compiled dylib and calls them.

## Layout

```
lean/         standalone Lake project, depends on LeanPy via path
python/       standalone uv project, depends on lean_py via path
```

Both projects path-depend on the repository root, so `lake build` and
`uv run` both work straight out of a fresh clone.

## Run

```bash
# Build the Lean library
cd lean && lake build && cd ..

# Run the Python client
uv run --project python python/main.py
```

Expected output:

```
py_increment(7)        = 8
py_greet("world")      = Hello, world!
py_sum_array([1..10])  = 55
py_origin(())          = Point.mk(0, 0)
py_norm_sq((3, 4))     = 25
py_perimeter(circle 5) = 30
py_perimeter(square 4) = 16
py_perimeter(rect 2 3) = 10
```
