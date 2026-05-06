/-
Re-export Pantograph.Frontend.Refactor under LeanPy.Kernel.Frontend.

Our vendored copy was identical to Pantograph's version (modulo namespace);
now that Pantograph is a Lake dependency we just re-export.
-/
import Pantograph.Frontend

namespace LeanPy.Kernel.Frontend

-- `runRefactor` lives directly in `Pantograph.Frontend`
export Pantograph.Frontend (
  runRefactor
)

-- Everything else is in the `Refactor` sub-namespace
export Pantograph.Frontend.Refactor (
  Command
  CommandCategory
  Config
  Context
  State
  RefactorM
  readConfig
  readCoreOptions
  fail
  mergeFileMap
  pushNewCommand
  liftFrontend
  runCoreM
  pushNewCommand'
  constantDependencies
  hasSorry
  preprocess
  mkProdElem
  distilSearchTarget
  foldTheoremsFlat
  DependencyTracker
  DependencyStructure
  extractDependencyStructure
  collectNextCommand
)

end LeanPy.Kernel.Frontend
