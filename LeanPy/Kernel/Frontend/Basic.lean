/-
Re-export Pantograph.Frontend.Basic under LeanPy.Kernel.Frontend.

Our vendored copy was identical to Pantograph's version (modulo namespace);
now that Pantograph is a Lake dependency we just re-export.
-/
import Pantograph.Frontend.Basic

open Lean

namespace LeanPy.Kernel.Frontend

/-! Re-export every public definition so downstream files that
    `open LeanPy.Kernel.Frontend` see the same names as before. -/

export Pantograph.Frontend (
  Context
  FrontendM
  CompilationStep
  stxByteRange
  runCommandElabM
  elabCommandAtFrontend
  processCommand
  processOneCommand
  executeFrontend
  mapCompilationSteps
  findSourcePath
  defaultFileName
  createContextStateFromFile
  collectEndState
)

end LeanPy.Kernel.Frontend
