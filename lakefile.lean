import Lake
open Lake DSL System

package LeanPy where
  version := v!"0.1.0"

require Pantograph from git
  "https://github.com/leanprover/Pantograph.git" @ "dev"

require Regex from git
  "https://github.com/pandaman64/lean-regex.git" @ "v4.29.0" / "regex"

/-- Compile the Python-bridge C source against the active Lean toolchain. -/
target pythonBridgeO pkg : FilePath := do
  let oFile := pkg.buildDir / "native" / "python_bridge.o"
  let srcJob ← inputTextFile <| pkg.dir / "LeanPy" / "native" / "python_bridge.c"
  let weakArgs := #["-I", (← getLeanIncludeDir).toString]
  let traceArgs := #["-fPIC", "-O2", "-Wall", "-Wno-unused-parameter"]
  buildO oFile srcJob weakArgs traceArgs (compiler := "cc")

/-- Bundle the C bridge as a static library so it can be linked into
downstream `@[python]`-using libraries. -/
extern_lib leanPyNative pkg := do
  let bridgeO ← fetch <| pkg.target ``pythonBridgeO
  buildStaticLib (pkg.staticLibDir / nameToStaticLib "leanpy_native") #[bridgeO]

@[default_target]
lean_lib LeanPy where
  defaultFacets := #[LeanLib.staticFacet]
  precompileModules := false
