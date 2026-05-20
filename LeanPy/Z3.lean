/-
LeanPy.Z3: Z3-style expression AST with compilation to Lean.Expr.

Defines Z3Sort, Z3BinOp, Z3UnOp, Z3Expr inductives (registered via
`derive_python`). The `z3Compile` function walks the AST in MetaM,
building fully elaborated Lean.Expr with automatic instance resolution.
-/
import Lean
import LeanPy.Attr
import LeanPy.Kernel
import Pantograph

open Lean Meta Elab Pantograph

namespace LeanPy.Z3

/-! ## Inductives -/

inductive Z3Sort where
  | prop | int | nat | real | type
  | bitvec (width : Nat)
  | uninterp (name : String)
  | arrow (dom cod : Z3Sort)
  deriving Inhabited

inductive Z3BinOp where
  | add | sub | mul | div | mod
  | lt | le | gt | ge | eq | ne
  | and | or | implies | xor
  | band | bor | bxor | bshl | bshr
  deriving Inhabited

inductive Z3UnOp where
  | neg | not | bnot
  deriving Inhabited

inductive Z3Expr where
  | var (name : String)
  | intLit (val : Int)
  | natLit (val : Nat)
  | boolLit (val : Bool)
  | bvLit (val : Nat) (width : Nat)
  | binop (op : Z3BinOp) (lhs rhs : Z3Expr)
  | unop (op : Z3UnOp) (arg : Z3Expr)
  | ite (cond then_ else_ : Z3Expr)
  | forall_ (name : String) (sort : Z3Sort) (body : Z3Expr)
  | exists_ (name : String) (sort : Z3Sort) (body : Z3Expr)
  | app (func : Z3Expr) (args : Array Z3Expr)
  | distinct (args : Array Z3Expr)
  | select (arr idx : Z3Expr)
  | store (arr idx val : Z3Expr)
  | constArray (domSort : Z3Sort) (val : Z3Expr)
  deriving Inhabited

derive_python LeanPy.Z3.Z3Sort
derive_python LeanPy.Z3.Z3BinOp
derive_python LeanPy.Z3.Z3UnOp
derive_python LeanPy.Z3.Z3Expr

/-! ## Sort compilation -/

partial def compileSort (varMap : Std.HashMap String Lean.Expr) : Z3Sort → MetaM Lean.Expr
  | .prop    => return mkSort .zero
  | .int     => return mkConst ``Int
  | .nat     => return mkConst ``Nat
  | .real    => return mkConst `Real
  | .type    => return mkSort (.succ .zero)
  | .bitvec w => return mkApp (mkConst ``BitVec) (mkNatLit w)
  | .uninterp name =>
    match varMap.get? name with
    | some e => return e
    | none   => throwError s!"compileSort: unknown uninterpreted sort '{name}'"
  | .arrow dom cod => do
    let domExpr ← compileSort varMap dom
    let codExpr ← compileSort varMap cod
    return Expr.forallE `_ domExpr codExpr .default

/-! ## Expression compiler -/

partial def compileExpr (varMap : Std.HashMap String Lean.Expr) : Z3Expr → MetaM Lean.Expr
  | .var name =>
    match varMap.get? name with
    | some e => return e
    | none   => throwError s!"compileExpr: unknown variable '{name}'"
  | .intLit n => do
    if n >= 0 then
      Meta.mkNumeral (mkConst ``Int) n.toNat
    else
      -- Build negative int: Neg.neg (mkNumeral |n|)
      let posLit ← Meta.mkNumeral (mkConst ``Int) n.natAbs
      Meta.mkAppM ``Neg.neg #[posLit]
  | .natLit n => Meta.mkNumeral (mkConst ``Nat) n
  | .boolLit true  => return mkConst ``True
  | .boolLit false => return mkConst ``False
  | .bvLit val width => do
    let bvType := mkApp (mkConst ``BitVec) (mkNatLit width)
    Meta.mkNumeral bvType val
  | .binop op lhs rhs => do
    let a ← compileExpr varMap lhs
    let b ← compileExpr varMap rhs
    match op with
    | .add     => Meta.mkAppM ``HAdd.hAdd #[a, b]
    | .sub     => Meta.mkAppM ``HSub.hSub #[a, b]
    | .mul     => Meta.mkAppM ``HMul.hMul #[a, b]
    | .div     => Meta.mkAppM ``HDiv.hDiv #[a, b]
    | .mod     => Meta.mkAppM ``HMod.hMod #[a, b]
    | .lt      => Meta.mkAppM ``LT.lt #[a, b]
    | .le      => Meta.mkAppM ``LE.le #[a, b]
    | .gt      => Meta.mkAppM ``GT.gt #[a, b]
    | .ge      => Meta.mkAppM ``GE.ge #[a, b]
    | .eq      => Meta.mkEq a b
    | .ne      => do let eq ← Meta.mkEq a b; Meta.mkAppM ``Not #[eq]
    | .and     => Meta.mkAppM ``And #[a, b]
    | .or      => Meta.mkAppM ``Or #[a, b]
    | .implies => return Expr.forallE `_ a b .default
    | .xor     => do
      -- Prop-level XOR: (a ∧ ¬b) ∨ (¬a ∧ b)
      let notA ← Meta.mkAppM ``Not #[a]
      let notB ← Meta.mkAppM ``Not #[b]
      let left ← Meta.mkAppM ``And #[a, notB]
      let right ← Meta.mkAppM ``And #[notA, b]
      Meta.mkAppM ``Or #[left, right]
    | .band    => Meta.mkAppM ``HAnd.hAnd #[a, b]
    | .bor     => Meta.mkAppM ``HOr.hOr #[a, b]
    | .bxor    => Meta.mkAppM ``HXor.hXor #[a, b]
    | .bshl    => Meta.mkAppM ``HShiftLeft.hShiftLeft #[a, b]
    | .bshr    => Meta.mkAppM ``HShiftRight.hShiftRight #[a, b]
  | .unop op arg => do
    let a ← compileExpr varMap arg
    match op with
    | .neg  => Meta.mkAppM ``Neg.neg #[a]
    | .not  => Meta.mkAppM ``Not #[a]
    | .bnot => Meta.mkAppM ``Complement.complement #[a]
  | .ite cond then_ else_ => do
    let c ← compileExpr varMap cond
    let t ← compileExpr varMap then_
    let e ← compileExpr varMap else_
    -- Try with synthesized Decidable; fall back to classical
    try
      Meta.mkAppOptM ``ite #[none, c, none, t, e]
    catch _ =>
      let dec ← Meta.mkAppM ``Classical.propDecidable #[c]
      Meta.mkAppOptM ``ite #[none, c, some dec, t, e]
  | .forall_ name sort body => do
    let sortExpr ← compileSort varMap sort
    Meta.withLocalDecl name.toName .default sortExpr fun fvar => do
      let varMap' := varMap.insert name fvar
      let bodyExpr ← compileExpr varMap' body
      Meta.mkForallFVars #[fvar] bodyExpr
  | .exists_ name sort body => do
    let sortExpr ← compileSort varMap sort
    Meta.withLocalDecl name.toName .default sortExpr fun fvar => do
      let varMap' := varMap.insert name fvar
      let bodyExpr ← compileExpr varMap' body
      let lam ← Meta.mkLambdaFVars #[fvar] bodyExpr
      Meta.mkAppM ``Exists #[lam]
  | .app func args => do
    let mut result ← compileExpr varMap func
    for arg in args do
      let argExpr ← compileExpr varMap arg
      result := Lean.mkApp result argExpr
    return result
  | .distinct args => do
    if args.size <= 1 then
      return mkConst ``True
    let compiled ← args.mapM (compileExpr varMap)
    let mut result ← Meta.mkEq compiled[0]! compiled[1]!
    result ← Meta.mkAppM ``Not #[result]
    for i in [0:compiled.size] do
      for j in [i+1:compiled.size] do
        if i == 0 && j == 1 then continue
        let neq ← do
          let eq ← Meta.mkEq compiled[i]! compiled[j]!
          Meta.mkAppM ``Not #[eq]
        result ← Meta.mkAppM ``And #[result, neq]
    return result
  | .select arr idx => do
    let a ← compileExpr varMap arr
    let i ← compileExpr varMap idx
    return Lean.mkApp a i
  | .store arr idx val => do
    let a ← compileExpr varMap arr
    let i ← compileExpr varMap idx
    let v ← compileExpr varMap val
    let idxTy ← Meta.inferType i
    Meta.withLocalDecl `_idx .default idxTy fun xvar => do
      let cond ← Meta.mkEq xvar i
      let iteExpr ← do
        try
          Meta.mkAppOptM ``ite #[none, cond, none, v, Lean.mkApp a xvar]
        catch _ =>
          let dec ← Meta.mkAppM ``Classical.propDecidable #[cond]
          Meta.mkAppOptM ``ite #[none, cond, some dec, v, Lean.mkApp a xvar]
      Meta.mkLambdaFVars #[xvar] iteExpr
  | .constArray domSort val => do
    let domExpr ← compileSort varMap domSort
    let v ← compileExpr varMap val
    Meta.withLocalDecl `_ .default domExpr fun xvar => do
      Meta.mkLambdaFVars #[xvar] v

/-! ## Top-level @[python] functions -/

@[python "z3_compile"]
def z3Compile (expr : Z3Expr) : IO Lean.Expr := do
  match (← LeanPy.Kernel.envRef.get) with
  | none => throw (IO.userError "no environment loaded")
  | some env =>
    let ctx ← LeanPy.Kernel.freshCoreContext
    let cs : Core.State := { env }
    let act : MetaM Lean.Expr := compileExpr {} expr
    let (r, _) ← (act.run' {} {}).toIO ctx cs
    return r

@[python "z3_goal_create_expr"]
def z3GoalCreateExpr (e : Lean.Expr) : IO GoalState := do
  match (← LeanPy.Kernel.envRef.get) with
  | none => throw (IO.userError "no environment loaded")
  | some env =>
    let ctx ← LeanPy.Kernel.freshCoreContext
    let cs : Core.State := { env }
    let act : CoreM GoalState := do
      Meta.MetaM.run' do
        Meta.check e
        Term.TermElabM.run' do
          GoalState.create e
    let (r, _) ← act.toIO ctx cs
    return r

end LeanPy.Z3
