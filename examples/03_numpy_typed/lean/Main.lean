import TypedNumpy

open TypedNumpy

/-- Compose a few typed operations and print the final array.
Every shape below is checked at compile time. -/
def runDemo : IO Unit := do
  IO.println "demo_run:"
  let a ← NDArray.ones .f64 [3, 4]
  let b ← NDArray.ones .f64 [4, 2]
  let c ← NDArray.matmul a b              -- type-level: NDArray .f64 [3, 2]
  let d ← NDArray.reshape c [6]           -- proof discharged by `decide`
  IO.println s!"  {← d.repr}"

#eval runDemo

/-- A "real" computation: build `[1.0 ... 6.0]`, reshape to `(2, 3)`,
multiply with its transpose to get `(2, 2)`, and add `ones (2, 2)`.
The reshaped result is read back as an `Array Float`. -/
def runPipeline : IO Unit := do
  let v ← NDArray.arange .f64 6           -- NDArray .f64 [6]
  let m ← NDArray.reshape v [2, 3]        -- NDArray .f64 [2, 3]
  let mt ← NDArray.transpose m            -- NDArray .f64 [3, 2]
  let prod ← NDArray.matmul m mt          -- NDArray .f64 [2, 2]
  let bias ← NDArray.ones .f64 [2, 2]
  let out ← NDArray.add prod bias
  let flat ← NDArray.reshape out [4]      -- NDArray .f64 [4]
  let arr ← flat.toArray
  IO.println s!"\ndemo_pipeline -> Array Float of length {arr.size}"
  IO.println s!"  {arr}"

def runExplain : IO Unit := do
  let a ← NDArray.zeros .f64 [3, 4]
  let b ← NDArray.zeros .f64 [4, 5]
  let c ← NDArray.matmul a b
  IO.println s!"\ndemo_explain:"
  IO.println s!"  matmul (3,4) @ (4,5) -> shape inferred by Lean = [3, 5]; numpy says: {← c.repr}"

def main : IO Unit := do
  runDemo
  runPipeline
  runExplain
