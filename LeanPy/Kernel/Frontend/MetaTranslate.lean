/-
Re-export Pantograph.Frontend.MetaTranslate under LeanPy.Kernel.Frontend.

Our vendored copy was identical to Pantograph's version (modulo namespace
and trace class name); now that Pantograph is a Lake dependency we just
re-export.
-/
import Pantograph.Frontend.MetaTranslate

namespace LeanPy.Kernel.Frontend

export Pantograph.Frontend (
  MetaTranslateM
)

export Pantograph.Frontend.MetaTranslate (
  Context
  State
  getSourceLCtx
  getSourceMCtx
  addTranslatedFVar
  addTranslatedMVar
  saveFVarMap
  restoreFVarMap
  resetFVarMap
  translateLocalInstance
  translateLocalDecl
  translateLCtx
  translateMVarId
  translateMVarFromTermInfo
  translateMVarFromTacticInfoBefore
)

end LeanPy.Kernel.Frontend
