/-
Re-export Pantograph.Frontend.Distil under LeanPy.Kernel.Frontend.

Our vendored copy was identical to Pantograph's version (modulo namespace
and @[export] names); now that Pantograph is a Lake dependency we just
re-export.
-/
import Pantograph.Frontend

namespace LeanPy.Kernel.Frontend

export Pantograph.Frontend (
  TacticInvocation
  collectTactics
  collectTacticsFromCompilationStep
  InfoWithContext
  GoalCollectionOptions
  collectSorrys
  AnnotatedGoalState
  sorrysToGoalState
  DistilConfig
  DistilledSearchTarget
  distilGoalStateFrom
  distilSearchTargets
)

end LeanPy.Kernel.Frontend
