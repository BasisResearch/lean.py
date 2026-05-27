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
import Regex

open Lean Meta Elab Pantograph

namespace LeanPy.Z3

/-! ## Inductives -/

inductive Z3Sort where
  | prop | int | nat | real | type | string
  | bitvec (width : Nat)
  | fp (ebits : Nat) (sbits : Nat)
  | finDomain (size : Nat)
  | uninterp (name : String)
  | arrow (dom cod : Z3Sort)
  | inductive_ (name : String)
  | char
  | seq (elemSort : Z3Sort)
  deriving Inhabited

inductive Z3BinOp where
  | add | sub | mul | div | mod
  | lt | le | gt | ge | eq | ne
  | and | or | implies | xor
  | band | bor | bxor | bshl | bshr
  | pow | concat
  | rotl | rotr | sdiv | srem | ashr
  | slt | sle | sgt | sge | smod
  | ediv | emod
  deriving Inhabited

inductive Z3UnOp where
  | neg | not | bnot | bv2int | bv2nat
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
  | lambda_ (name : String) (sort : Z3Sort) (body : Z3Expr)
  | extract (hi lo : Nat) (arg : Z3Expr)
  | zeroExt (bits : Nat) (arg : Z3Expr)
  | signExt (bits : Nat) (arg : Z3Expr)
  | int2bv (width : Nat) (arg : Z3Expr)
  | toReal (arg : Z3Expr)
  | toInt (arg : Z3Expr)
  -- String operations
  | stringLit (val : String)
  | strLen (arg : Z3Expr)
  | strContains (haystack needle : Z3Expr)
  | strPrefixOf (prefix_ s : Z3Expr)
  | strSuffixOf (suffix_ s : Z3Expr)
  | strReplace (s old new_ : Z3Expr)
  | strConcat (lhs rhs : Z3Expr)
  | strSubstr (s offset length : Z3Expr)
  | strIndexOf (s substr offset : Z3Expr)
  | strToInt (arg : Z3Expr)
  | intToStr (arg : Z3Expr)
  -- Regex operations
  | reStar (arg : Z3Expr)
  | rePlus (arg : Z3Expr)
  | reOption (arg : Z3Expr)
  | reUnion (a b : Z3Expr)
  | reIntersect (a b : Z3Expr)
  | reConcat (a b : Z3Expr)
  | reRange (lo hi : Char)
  | reComplement (arg : Z3Expr)
  | reLoop (arg : Z3Expr) (lo hi : Nat)
  | inRe (s re : Z3Expr)
  -- Floating-point operations
  | fpLit (bits : Nat) (ebits : Nat) (sbits : Nat)
  | fpOp (name : String) (args : Array Z3Expr)
  -- Finite domain
  | finDomainLit (val : Nat) (size : Nat)
  -- Inductive datatypes
  | inductiveCtor (typeName : String) (ctorName : String) (args : Array Z3Expr)
  | inductiveAccessor (typeName : String) (accessorName : String) (arg : Z3Expr)
  | inductiveRecognizer (typeName : String) (recognizerName : String) (arg : Z3Expr)
  -- Char operations
  | charLit (val : Nat)
  | charToNat (arg : Z3Expr)
  | charFromBv (arg : Z3Expr)
  | charIsDigit (arg : Z3Expr)
  -- Sequence operations
  | seqEmpty (elemSort : Z3Sort)
  | seqUnit (arg : Z3Expr)
  | seqLen (arg : Z3Expr)
  | seqConcat (lhs rhs : Z3Expr)
  | seqContains (haystack needle : Z3Expr)
  | seqPrefixOf (prefix_ s : Z3Expr)
  | seqSuffixOf (suffix_ s : Z3Expr)
  | seqNth (s idx : Z3Expr)
  deriving Inhabited

structure Z3CtorField where
  name : String
  sort : Z3Sort
  deriving Inhabited

structure Z3CtorDesc where
  name : String
  fields : Array Z3CtorField
  deriving Inhabited

structure Z3InductiveDesc where
  name : String
  ctors : Array Z3CtorDesc
  deriving Inhabited

derive_python LeanPy.Z3.Z3Sort
derive_python LeanPy.Z3.Z3BinOp
derive_python LeanPy.Z3.Z3UnOp
derive_python LeanPy.Z3.Z3Expr
derive_python LeanPy.Z3.Z3CtorField
derive_python LeanPy.Z3.Z3CtorDesc
derive_python LeanPy.Z3.Z3InductiveDesc

/-! ## SMT-LIB Euclidean division helpers -/

/-- SMT-LIB Euclidean modulo: result is always non-negative. -/
def smt_emod (a b : Int) : Int :=
  let r := a % b
  if r < 0 then r + (if b < 0 then -b else b) else r

/-- SMT-LIB Euclidean division: satisfies a = b * smt_ediv a b + smt_emod a b. -/
def smt_ediv (a b : Int) : Int :=
  if b == 0 then 0
  else (a - smt_emod a b) / b

/-- Z3-compatible substring containment (String.contains takes Char, not String). -/
def strContainsSubstr (haystack needle : String) : Bool :=
  let h := haystack.toList
  let n := needle.toList
  match h_nLen : n.length with
  | 0 => true
  | _ + 1 => go h n n.length h.length 0 (by omega)
where
  go (h n : List Char) (nLen hLen i : Nat) (hn : nLen ≥ 1) : Bool :=
    if h_guard : i + nLen > hLen then false
    else if (h.drop i).take nLen == n then true
    else go h n nLen hLen (i + 1) hn
  termination_by hLen - i
  decreasing_by omega

/-- Z3-compatible str.indexof: find first occurrence of needle in haystack
    starting from offset. Returns -1 if not found (SMT-LIB semantics). -/
def strIndexOf (haystack needle : String) (offset : Int) : Int :=
  if offset < 0 then -1
  else
    let h := haystack.toList
    let n := needle.toList
    let hLen := h.length
    let off := offset.toNat
    match h_nLen : n.length with
    | 0 => if off ≤ hLen then offset else -1
    | _ + 1 => go h n n.length hLen off (by omega)
where
  go (h n : List Char) (nLen hLen i : Nat) (hn : nLen ≥ 1) : Int :=
    if h_guard : i + nLen > hLen then -1
    else if (h.drop i).take nLen == n then Int.ofNat i
    else go h n nLen hLen (i + 1) hn
  termination_by hLen - i
  decreasing_by omega

/-- Z3-compatible str.replace: replace first occurrence of `old` with `new_`.
    Uses only Init functions (splitOn, intercalate, ++). -/
def strReplaceFirst (s old new_ : String) : String :=
  match s.splitOn old with
  | []           => s
  | [x]          => x  -- old not found
  | first :: rest => first ++ new_ ++ String.intercalate old rest

/-- Z3-compatible list containment: check if needle is a contiguous sublist. -/
def listContainsSublist [BEq α] (haystack needle : List α) : Bool :=
  match h_nLen : needle.length with
  | 0 => true
  | _ + 1 => go haystack needle needle.length haystack.length 0 (by omega)
where
  go (h n : List α) (nLen hLen i : Nat) (hn : nLen ≥ 1) : Bool :=
    if h_guard : i + nLen > hLen then false
    else if (h.drop i).take nLen == n then true
    else go h n nLen hLen (i + 1) hn
  termination_by hLen - i
  decreasing_by omega

/-- Z3-compatible str.substr (SMT-LIB semantics): extract `length` chars starting at `offset`.
    Uses List operations to avoid `String.Pos` dependency issues. -/
def strSubstr (s : String) (offset length : Int) : String :=
  String.ofList (s.toList.drop offset.toNat |>.take length.toNat)

/-- Z3-compatible int.to.str: returns "" for negative integers (SMT-LIB semantics). -/
def intToStrZ3 (n : Int) : String :=
  if n < 0 then "" else ToString.toString n

/-- IEEE 754 fpIsNegative: true when sign bit is set and not NaN. -/
def fpIsNegative (x : Float) : Bool :=
  x.toBits.toNat ≥ (1 <<< 63) && !x.isNaN

/-- IEEE 754 fpIsPositive: true when sign bit is clear and not NaN. -/
def fpIsPositive (x : Float) : Bool :=
  x.toBits.toNat < (1 <<< 63) && !x.isNaN

/-- Z3-compatible str.to.int: returns -1 for non-numeric strings (SMT-LIB semantics). -/
def strToIntZ3 (s : String) : Int :=
  if s.isEmpty then -1
  else
    match s.toNat? with
    | some n => Int.ofNat n
    | none   => -1

/-! ## Sort compilation -/

partial def compileSort (varMap : Std.HashMap String Lean.Expr) : Z3Sort → MetaM Lean.Expr
  | .prop    => return mkSort .zero
  | .int     => return mkConst ``Int
  | .nat     => return mkConst ``Nat
  | .real    => return mkConst ``Rat
  | .type    => return mkSort (.succ .zero)
  | .string  => return mkConst ``String
  | .bitvec w => return mkApp (mkConst ``BitVec) (mkNatLit w)
  | .fp 11 53 => return mkConst ``Float
  | .fp e s   => throwError s!"Only Float64 (11/53) is supported, got ({e}/{s})"
  | .finDomain n => return mkApp (mkConst ``Fin) (mkNatLit n)
  | .uninterp name =>
    match varMap.get? name with
    | some e => return e
    | none   => throwError s!"compileSort: unknown uninterpreted sort '{name}'"
  | .arrow dom cod => do
    let domExpr ← compileSort varMap dom
    let codExpr ← compileSort varMap cod
    return Expr.forallE `_ domExpr codExpr .default
  | .inductive_ name => do
    let tName := Name.mkSimple name
    match varMap.get? name with
    | some e => return e
    | none =>
      let env ← getEnv
      if env.contains tName then return mkConst tName
      else throwError s!"compileSort: inductive '{name}' not in environment"
  | .char => return mkConst ``Char
  | .seq s => do
    let elemExpr ← compileSort varMap s
    return mkApp (mkConst ``List [.succ .zero]) elemExpr

/-! ## Expression compiler & Regex AST compiler -/

/-- Helper: build a Lean Char expression from a Lean Char value. -/
private def mkCharExpr (c : Char) : Lean.Expr :=
  mkApp (mkConst ``Char.ofNat) (mkNatLit c.toNat)

/-- Convert a Z3Expr representing a regex into a lean-regex `Regex.Data.Expr`. -/
partial def compileRegex (varMap : Std.HashMap String Lean.Expr) : Z3Expr → MetaM Lean.Expr
  | .stringLit val => do
    -- String literal → concat of individual chars
    let chars := val.toList
    if chars.isEmpty then return mkConst ``Regex.Data.Expr.epsilon
    let mut result := mkApp (mkConst ``Regex.Data.Expr.char) (mkCharExpr chars.head!)
    for c in chars.tail! do
      let charExpr := mkApp (mkConst ``Regex.Data.Expr.char) (mkCharExpr c)
      result := mkApp2 (mkConst ``Regex.Data.Expr.concat) result charExpr
    return result
  | .reStar arg => do
    let a ← compileRegex varMap arg
    return mkApp2 (mkConst ``Regex.Data.Expr.star) (mkConst ``true) a
  | .rePlus arg => do
    let a ← compileRegex varMap arg
    let star := mkApp2 (mkConst ``Regex.Data.Expr.star) (mkConst ``true) a
    return mkApp2 (mkConst ``Regex.Data.Expr.concat) a star
  | .reOption arg => do
    let a ← compileRegex varMap arg
    return mkApp2 (mkConst ``Regex.Data.Expr.alternate) a (mkConst ``Regex.Data.Expr.epsilon)
  | .reUnion a b => do
    let a' ← compileRegex varMap a
    let b' ← compileRegex varMap b
    return mkApp2 (mkConst ``Regex.Data.Expr.alternate) a' b'
  | .reConcat a b => do
    let a' ← compileRegex varMap a
    let b' ← compileRegex varMap b
    return mkApp2 (mkConst ``Regex.Data.Expr.concat) a' b'
  | .reRange lo hi => do
    -- Build alternation of all chars in [lo..hi]
    let mut result := mkApp (mkConst ``Regex.Data.Expr.char) (mkCharExpr lo)
    let loNat := lo.toNat
    let hiNat := hi.toNat
    for i in [loNat + 1 : hiNat + 1] do
      let c := Char.ofNat i
      let charExpr := mkApp (mkConst ``Regex.Data.Expr.char) (mkCharExpr c)
      result := mkApp2 (mkConst ``Regex.Data.Expr.alternate) result charExpr
    return result
  | .reComplement _arg =>
    throwError "reComplement is not supported: lean-regex does not support complement"
  | .reLoop arg lo hi => do
    let a ← compileRegex varMap arg
    let mut result := mkConst ``Regex.Data.Expr.epsilon
    for _ in [:lo] do
      result := mkApp2 (mkConst ``Regex.Data.Expr.concat) result a
    let opt := mkApp2 (mkConst ``Regex.Data.Expr.alternate) a (mkConst ``Regex.Data.Expr.epsilon)
    for _ in [:hi - lo] do
      result := mkApp2 (mkConst ``Regex.Data.Expr.concat) result opt
    return result
  | _other => do
    -- For unrecognized nodes, return epsilon as fallback
    return mkConst ``Regex.Data.Expr.epsilon

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
    | .bshl    => do
      let bTy ← Meta.inferType b
      let natTy := mkConst ``Nat
      let b' ← if (← Meta.isDefEq bTy natTy) then pure b
                else Meta.mkAppM ``BitVec.toNat #[b]
      Meta.mkAppM ``HShiftLeft.hShiftLeft #[a, b']
    | .bshr    => do
      let bTy ← Meta.inferType b
      let natTy := mkConst ``Nat
      let b' ← if (← Meta.isDefEq bTy natTy) then pure b
                else Meta.mkAppM ``BitVec.toNat #[b]
      Meta.mkAppM ``HShiftRight.hShiftRight #[a, b']
    | .pow     => do
      -- HPow requires Nat exponent; for negative Int exponents, compute 1/(a^|n|)
      let bTy ← Meta.inferType b
      let natTy := mkConst ``Nat
      let intTy := mkConst ``Int
      if (← Meta.isDefEq bTy natTy) then
        Meta.mkAppM ``HPow.hPow #[a, b]
      else if (← Meta.isDefEq bTy intTy) then
        -- Check sign at type level: use ite (b < 0) (1 / a^(Int.toNat (-b))) (a^(Int.toNat b))
        let zero ← Meta.mkNumeral intTy 0
        let negB ← Meta.mkAppM ``Neg.neg #[b]
        let absB ← Meta.mkAppM ``Int.toNat #[negB]
        let posB ← Meta.mkAppM ``Int.toNat #[b]
        let powPos ← Meta.mkAppM ``HPow.hPow #[a, posB]
        let powNeg ← Meta.mkAppM ``HPow.hPow #[a, absB]
        let one ← Meta.mkNumeral (← Meta.inferType a) 1
        let reciprocal ← Meta.mkAppM ``HDiv.hDiv #[one, powNeg]
        let cond ← Meta.mkAppM ``LT.lt #[b, zero]
        try
          Meta.mkAppOptM ``ite #[none, cond, none, reciprocal, powPos]
        catch _ =>
          let dec ← Meta.mkAppM ``Classical.propDecidable #[cond]
          Meta.mkAppOptM ``ite #[none, cond, some dec, reciprocal, powPos]
      else
        Meta.mkAppM ``HPow.hPow #[a, b]
    | .concat  => Meta.mkAppM ``HAppend.hAppend #[a, b]
    | .rotl    => do
      -- rotateLeft takes Nat; coerce b from BitVec to Nat
      let bTy ← Meta.inferType b
      let natTy := mkConst ``Nat
      let b' ← if (← Meta.isDefEq bTy natTy) then pure b
                else Meta.mkAppM ``BitVec.toNat #[b]
      Meta.mkAppM ``BitVec.rotateLeft #[a, b']
    | .rotr    => do
      let bTy ← Meta.inferType b
      let natTy := mkConst ``Nat
      let b' ← if (← Meta.isDefEq bTy natTy) then pure b
                else Meta.mkAppM ``BitVec.toNat #[b]
      Meta.mkAppM ``BitVec.rotateRight #[a, b']
    | .sdiv    => Meta.mkAppM ``BitVec.sdiv #[a, b]
    | .srem    => Meta.mkAppM ``BitVec.srem #[a, b]
    | .slt     => do
      let call ← Meta.mkAppM ``BitVec.slt #[a, b]
      Meta.mkEq call (mkConst ``true)
    | .sle     => do
      let call ← Meta.mkAppM ``BitVec.sle #[a, b]
      Meta.mkEq call (mkConst ``true)
    | .sgt     => do
      let call ← Meta.mkAppM ``BitVec.slt #[b, a]
      Meta.mkEq call (mkConst ``true)
    | .sge     => do
      let call ← Meta.mkAppM ``BitVec.sle #[b, a]
      Meta.mkEq call (mkConst ``true)
    | .smod    => Meta.mkAppM ``BitVec.smod #[a, b]
    | .ashr    => do
      let bTy ← Meta.inferType b
      let natTy := mkConst ``Nat
      let b' ← if (← Meta.isDefEq bTy natTy) then pure b
                else Meta.mkAppM ``BitVec.toNat #[b]
      Meta.mkAppM ``BitVec.sshiftRight #[a, b']
    | .ediv    => do
      -- Inline SMT-LIB Euclidean division using only Init functions:
      -- smt_emod a b = let r := a % b; if r < 0 then r + |b| else r
      -- smt_ediv a b = (a - smt_emod a b) / b
      let intTy := mkConst ``Int
      let zero ← Meta.mkNumeral intTy 0
      let r ← Meta.mkAppM ``HMod.hMod #[a, b]
      let rLt0 ← Meta.mkAppM ``LT.lt #[r, zero]
      let negB ← Meta.mkAppM ``Neg.neg #[b]
      let bLt0 ← Meta.mkAppM ``LT.lt #[b, zero]
      let absB ← do
        try
          Meta.mkAppOptM ``ite #[none, bLt0, none, negB, b]
        catch _ =>
          let dec ← Meta.mkAppM ``Classical.propDecidable #[bLt0]
          Meta.mkAppOptM ``ite #[none, bLt0, some dec, negB, b]
      let rPlusAbsB ← Meta.mkAppM ``HAdd.hAdd #[r, absB]
      let emod ← do
        try
          Meta.mkAppOptM ``ite #[none, rLt0, none, rPlusAbsB, r]
        catch _ =>
          let dec ← Meta.mkAppM ``Classical.propDecidable #[rLt0]
          Meta.mkAppOptM ``ite #[none, rLt0, some dec, rPlusAbsB, r]
      let diff ← Meta.mkAppM ``HSub.hSub #[a, emod]
      Meta.mkAppM ``HDiv.hDiv #[diff, b]
    | .emod    => do
      -- Inline SMT-LIB Euclidean mod: let r := a % b; if r < 0 then r + |b| else r
      let intTy := mkConst ``Int
      let zero ← Meta.mkNumeral intTy 0
      let r ← Meta.mkAppM ``HMod.hMod #[a, b]
      let rLt0 ← Meta.mkAppM ``LT.lt #[r, zero]
      let negB ← Meta.mkAppM ``Neg.neg #[b]
      let bLt0 ← Meta.mkAppM ``LT.lt #[b, zero]
      let absB ← do
        try
          Meta.mkAppOptM ``ite #[none, bLt0, none, negB, b]
        catch _ =>
          let dec ← Meta.mkAppM ``Classical.propDecidable #[bLt0]
          Meta.mkAppOptM ``ite #[none, bLt0, some dec, negB, b]
      let rPlusAbsB ← Meta.mkAppM ``HAdd.hAdd #[r, absB]
      try
        Meta.mkAppOptM ``ite #[none, rLt0, none, rPlusAbsB, r]
      catch _ =>
        let dec ← Meta.mkAppM ``Classical.propDecidable #[rLt0]
        Meta.mkAppOptM ``ite #[none, rLt0, some dec, rPlusAbsB, r]
  | .unop op arg => do
    let a ← compileExpr varMap arg
    match op with
    | .neg  => Meta.mkAppM ``Neg.neg #[a]
    | .not  => Meta.mkAppM ``Not #[a]
    | .bnot => Meta.mkAppM ``Complement.complement #[a]
    | .bv2int => Meta.mkAppM ``BitVec.toInt #[a]
    | .bv2nat => do
      let nat ← Meta.mkAppM ``BitVec.toNat #[a]
      Meta.mkAppM ``Int.ofNat #[nat]
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
  | .lambda_ name sort body => do
    let sortExpr ← compileSort varMap sort
    Meta.withLocalDecl name.toName .default sortExpr fun fvar => do
      let varMap' := varMap.insert name fvar
      let bodyExpr ← compileExpr varMap' body
      Meta.mkLambdaFVars #[fvar] bodyExpr
  | .extract hi lo arg => do
    let a ← compileExpr varMap arg
    let hiLit := mkNatLit hi
    let loLit := mkNatLit lo
    Meta.mkAppM ``BitVec.extractLsb #[hiLit, loLit, a]
  | .zeroExt bits arg => do
    let a ← compileExpr varMap arg
    let bitsLit := mkNatLit bits
    Meta.mkAppM ``BitVec.zeroExtend #[bitsLit, a]
  | .signExt bits arg => do
    let a ← compileExpr varMap arg
    let bitsLit := mkNatLit bits
    Meta.mkAppM ``BitVec.signExtend #[bitsLit, a]
  | .int2bv width arg => do
    let a ← compileExpr varMap arg
    let widthLit := mkNatLit width
    Meta.mkAppOptM ``BitVec.ofInt #[some widthLit, some a]
  | .toReal arg => do
    let a ← compileExpr varMap arg
    -- Convert Int → Rat via Rat.ofInt (in Lean core)
    Meta.mkAppM ``Rat.ofInt #[a]
  | .toInt arg => do
    let a ← compileExpr varMap arg
    -- Int.floor requires Mathlib's FloorRing; will error if not available
    try
      Meta.mkAppM `Int.floor #[a]
    catch _ =>
      throwError "toInt compilation requires `Int.floor` (available with Mathlib)"
  -- String operations
  | .stringLit val => return mkStrLit val
  | .strLen arg => do
    let a ← compileExpr varMap arg
    let len ← Meta.mkAppM ``String.length #[a]
    -- z3py Length returns Int, Lean String.length returns Nat — cast
    Meta.mkAppM ``Int.ofNat #[len]
  | .strContains haystack needle => do
    let a ← compileExpr varMap haystack
    let b ← compileExpr varMap needle
    let call ← Meta.mkAppM ``LeanPy.Z3.strContainsSubstr #[a, b]
    Meta.mkEq call (mkConst ``true)
  | .strPrefixOf prefix_ s => do
    let a ← compileExpr varMap prefix_
    let b ← compileExpr varMap s
    let call ← Meta.mkAppM ``String.isPrefixOf #[a, b]
    Meta.mkEq call (mkConst ``true)
  | .strSuffixOf suffix_ s => do
    let a ← compileExpr varMap suffix_
    let b ← compileExpr varMap s
    let aList ← Meta.mkAppM ``String.toList #[a]
    let bList ← Meta.mkAppM ``String.toList #[b]
    let call ← Meta.mkAppM ``List.isSuffixOf #[aList, bList]
    Meta.mkEq call (mkConst ``true)
  | .strReplace s old new_ => do
    let a ← compileExpr varMap s
    let b ← compileExpr varMap old
    let c ← compileExpr varMap new_
    Meta.mkAppM ``LeanPy.Z3.strReplaceFirst #[a, b, c]
  | .strConcat lhs rhs => do
    let a ← compileExpr varMap lhs
    let b ← compileExpr varMap rhs
    Meta.mkAppM ``HAppend.hAppend #[a, b]
  | .strSubstr s offset length => do
    let a ← compileExpr varMap s
    let b ← compileExpr varMap offset
    let c ← compileExpr varMap length
    Meta.mkAppM ``LeanPy.Z3.strSubstr #[a, b, c]
  | .strIndexOf s substr offset => do
    let a ← compileExpr varMap s
    let b ← compileExpr varMap substr
    let c ← compileExpr varMap offset
    Meta.mkAppM ``LeanPy.Z3.strIndexOf #[a, b, c]
  | .strToInt arg => do
    let a ← compileExpr varMap arg
    Meta.mkAppM ``LeanPy.Z3.strToIntZ3 #[a]
  | .intToStr arg => do
    let a ← compileExpr varMap arg
    Meta.mkAppM ``LeanPy.Z3.intToStrZ3 #[a]
  -- Regex operations using lean-regex
  | .reStar arg => do
    let a ← compileRegex varMap arg
    return mkApp2 (mkConst ``Regex.Data.Expr.star) (mkConst ``true) a
  | .rePlus arg => do
    let a ← compileRegex varMap arg
    -- plus(r) = concat(r, star(r))
    let star := mkApp2 (mkConst ``Regex.Data.Expr.star) (mkConst ``true) a
    return mkApp2 (mkConst ``Regex.Data.Expr.concat) a star
  | .reOption arg => do
    let a ← compileRegex varMap arg
    -- option(r) = alternate(r, epsilon)
    return mkApp2 (mkConst ``Regex.Data.Expr.alternate) a (mkConst ``Regex.Data.Expr.epsilon)
  | .reUnion a b => do
    let a' ← compileRegex varMap a
    let b' ← compileRegex varMap b
    return mkApp2 (mkConst ``Regex.Data.Expr.alternate) a' b'
  | .reIntersect _a _b => do
    throwError "reIntersect is not supported: lean-regex does not support intersection"
  | .reConcat a b => do
    let a' ← compileRegex varMap a
    let b' ← compileRegex varMap b
    return mkApp2 (mkConst ``Regex.Data.Expr.concat) a' b'
  | .reRange lo hi => do
    -- Build alternation of all chars in [lo..hi]
    let mut result := mkApp (mkConst ``Regex.Data.Expr.char) (mkCharExpr lo)
    let loNat := lo.toNat
    let hiNat := hi.toNat
    for i in [loNat + 1 : hiNat + 1] do
      let c := Char.ofNat i
      let charExpr := mkApp (mkConst ``Regex.Data.Expr.char) (mkCharExpr c)
      result := mkApp2 (mkConst ``Regex.Data.Expr.alternate) result charExpr
    return result
  | .reComplement _arg => do
    throwError "reComplement is not supported: lean-regex does not support complement"
  | .reLoop arg lo hi => do
    let a ← compileRegex varMap arg
    -- Unroll loop as concat of `lo` copies then `hi-lo` optional copies
    let mut result := mkConst ``Regex.Data.Expr.epsilon
    for _ in [:lo] do
      result := mkApp2 (mkConst ``Regex.Data.Expr.concat) result a
    let opt := mkApp2 (mkConst ``Regex.Data.Expr.alternate) a (mkConst ``Regex.Data.Expr.epsilon)
    for _ in [:hi - lo] do
      result := mkApp2 (mkConst ``Regex.Data.Expr.concat) result opt
    return result
  | .inRe s re => do
    let str ← compileExpr varMap s
    let reExpr ← compileRegex varMap re
    -- Build: (Regex.fromExpr reExpr).test str = true
    let regex ← Meta.mkAppM ``Regex.fromExpr #[reExpr]
    let testResult ← Meta.mkAppM ``Regex.test #[regex, str]
    Meta.mkEq testResult (mkConst ``true)
  -- Inductive datatypes
  | .inductiveCtor typeName ctorName args => do
    let cName := Name.mkStr (Name.mkSimple typeName) ctorName
    let mut result := mkConst cName
    for arg in args do
      result := mkApp result (← compileExpr varMap arg)
    return result
  | .inductiveAccessor typeName accessorName arg => do
    let a ← compileExpr varMap arg
    let accName := Name.mkStr (Name.mkSimple typeName) accessorName
    return mkApp (mkConst accName) a
  | .inductiveRecognizer typeName recognizerName arg => do
    let a ← compileExpr varMap arg
    let tName := Name.mkSimple typeName
    let tConst := mkConst tName
    let casesOnName := Name.mkStr tName "casesOn"
    let propExpr := mkSort .zero
    -- Recognizer name is "is_<ctorName>"
    let targetCtorName := (recognizerName.drop 3).toString
    -- Build inline casesOn: @T.casesOn.{1} (fun _ => Prop) a branch0 branch1 ...
    let env ← getEnv
    let ctorNames := match env.find? tName with
      | some (.inductInfo val) => val.ctors
      | _ => []
    let motive := Expr.lam `_ tConst propExpr .default
    let mut branches : Array Lean.Expr := #[]
    for cName in ctorNames do
      let isTarget := cName == Name.mkStr tName targetCtorName
      let val := if isTarget then mkConst ``True else mkConst ``False
      -- Get ctor field types from the ctor type signature
      let some ctorInfo := env.find? cName | throwError s!"unknown ctor '{cName}'"
      let ctorType := ctorInfo.type
      -- Count fields by stripping foralls
      let mut fieldTypes : Array Lean.Expr := #[]
      let mut ty := ctorType
      while ty.isForall do
        fieldTypes := fieldTypes.push ty.bindingDomain!
        ty := ty.bindingBody!
      -- Build lambda abstracting over the ctor's fields
      let mut branch := val
      for i in [:fieldTypes.size] do
        let idx := fieldTypes.size - 1 - i
        let fieldName := Name.mkSimple s!"_f{idx}"
        branch := Expr.lam fieldName fieldTypes[idx]! branch .default
      branches := branches.push branch
    return mkAppN (mkConst casesOnName [.succ .zero]) (#[motive, a] ++ branches)
  -- Char operations
  | .charLit n => return mkApp (mkConst ``Char.ofNat) (mkNatLit n)
  | .charToNat arg => do
    let a ← compileExpr varMap arg
    let nat ← Meta.mkAppM ``Char.toNat #[a]
    Meta.mkAppM ``Int.ofNat #[nat]
  | .charFromBv arg => do
    let a ← compileExpr varMap arg
    let nat ← Meta.mkAppM ``BitVec.toNat #[a]
    return mkApp (mkConst ``Char.ofNat) nat
  | .charIsDigit arg => do
    let a ← compileExpr varMap arg
    let c ← Meta.mkAppM ``Char.isDigit #[a]
    Meta.mkEq c (mkConst ``true)
  -- Sequence operations
  | .seqEmpty es => do
    let elemExpr ← compileSort varMap es
    return mkApp (mkConst ``List.nil [.succ .zero]) elemExpr
  | .seqUnit arg => do
    let a ← compileExpr varMap arg
    let aTy ← Meta.inferType a
    let nil := mkApp (mkConst ``List.nil [.succ .zero]) aTy
    return mkAppN (mkConst ``List.cons [.succ .zero]) #[aTy, a, nil]
  | .seqLen arg => do
    let a ← compileExpr varMap arg
    let len ← Meta.mkAppM ``List.length #[a]
    Meta.mkAppM ``Int.ofNat #[len]
  | .seqConcat lhs rhs => do
    let a ← compileExpr varMap lhs
    let b ← compileExpr varMap rhs
    Meta.mkAppM ``HAppend.hAppend #[a, b]
  | .seqContains haystack needle => do
    let a ← compileExpr varMap haystack
    let b ← compileExpr varMap needle
    let call ← Meta.mkAppM ``LeanPy.Z3.listContainsSublist #[a, b]
    Meta.mkEq call (mkConst ``true)
  | .seqPrefixOf prefix_ s => do
    let a ← compileExpr varMap prefix_
    let b ← compileExpr varMap s
    let call ← Meta.mkAppM ``List.isPrefixOf #[a, b]
    Meta.mkEq call (mkConst ``true)
  | .seqSuffixOf suffix_ s => do
    let a ← compileExpr varMap suffix_
    let b ← compileExpr varMap s
    let call ← Meta.mkAppM ``List.isSuffixOf #[a, b]
    Meta.mkEq call (mkConst ``true)
  | .seqNth s idx => do
    let a ← compileExpr varMap s
    let i ← compileExpr varMap idx
    let iNat ← Meta.mkAppM ``Int.toNat #[i]
    Meta.mkAppM ``List.getD #[a, iNat]
  -- Floating-point
  | .fpLit bits 11 53 => do
    let bitsExpr ← Meta.mkNumeral (mkConst ``UInt64) bits
    return mkApp (mkConst ``Float.ofBits) bitsExpr
  | .fpLit _ e s => throwError s!"Only Float64 fpLit supported, got ({e}/{s})"
  | .fpOp name args => do
    let cs ← args.mapM (compileExpr varMap)
    match name with
    -- Arithmetic (binary)
    | "fpAdd" => Meta.mkAppM ``HAdd.hAdd #[cs[0]!, cs[1]!]
    | "fpSub" => Meta.mkAppM ``HSub.hSub #[cs[0]!, cs[1]!]
    | "fpMul" => Meta.mkAppM ``HMul.hMul #[cs[0]!, cs[1]!]
    | "fpDiv" => Meta.mkAppM ``HDiv.hDiv #[cs[0]!, cs[1]!]
    -- Arithmetic (unary)
    | "fpNeg" => Meta.mkAppM ``Neg.neg #[cs[0]!]
    | "fpAbs" => Meta.mkAppM ``Float.abs #[cs[0]!]
    | "fpSqrt" => Meta.mkAppM ``Float.sqrt #[cs[0]!]
    -- Ternary
    | "fpFMA" => do
        -- a*b + c (no Float.fma in Lean stdlib)
        let ab ← Meta.mkAppM ``HMul.hMul #[cs[0]!, cs[1]!]
        Meta.mkAppM ``HAdd.hAdd #[ab, cs[2]!]
    -- Min/Max
    | "fpMin" => Meta.mkAppM ``Min.min #[cs[0]!, cs[1]!]
    | "fpMax" => Meta.mkAppM ``Max.max #[cs[0]!, cs[1]!]
    -- Rounding
    | "fpRoundToIntegral" => Meta.mkAppM ``Float.round #[cs[0]!]
    -- Comparisons
    | "fpLT"  => Meta.mkAppM ``LT.lt #[cs[0]!, cs[1]!]
    | "fpLEQ" => Meta.mkAppM ``LE.le #[cs[0]!, cs[1]!]
    | "fpGT"  => Meta.mkAppM ``LT.lt #[cs[1]!, cs[0]!]
    | "fpGEQ" => Meta.mkAppM ``LE.le #[cs[1]!, cs[0]!]
    -- FP equality (IEEE: BEq, returns Bool → wrap = true)
    | "fpEQ"  => do
        let call ← Meta.mkAppM ``BEq.beq #[cs[0]!, cs[1]!]
        Meta.mkEq call (mkConst ``true)
    -- Predicates (return Bool → wrap = true)
    | "fpIsNaN" => do
        let c ← Meta.mkAppM ``Float.isNaN #[cs[0]!]
        Meta.mkEq c (mkConst ``true)
    | "fpIsInf" => do
        let c ← Meta.mkAppM ``Float.isInf #[cs[0]!]
        Meta.mkEq c (mkConst ``true)
    | "fpIsZero" => do
        let zeroBits ← Meta.mkNumeral (mkConst ``UInt64) 0
        let zero := mkApp (mkConst ``Float.ofBits) zeroBits
        let c ← Meta.mkAppM ``BEq.beq #[cs[0]!, zero]
        Meta.mkEq c (mkConst ``true)
    | "fpIsNormal" | "fpIsSubnormal" =>
        throwError s!"fpOp '{name}' not yet supported"
    | "fpIsNegative" => do
        let c ← Meta.mkAppM ``LeanPy.Z3.fpIsNegative #[cs[0]!]
        Meta.mkEq c (mkConst ``true)
    | "fpIsPositive" => do
        let c ← Meta.mkAppM ``LeanPy.Z3.fpIsPositive #[cs[0]!]
        Meta.mkEq c (mkConst ``true)
    -- Conversions
    | "fpToIEEEBV" => do
        let bits ← Meta.mkAppM ``Float.toBits #[cs[0]!]
        let nat ← Meta.mkAppM ``UInt64.toNat #[bits]
        return mkApp2 (mkConst ``BitVec.ofNat) (mkNatLit 64) nat
    | "fpToReal" => throwError "fpToReal requires Mathlib (Real type)"
    | _ => throwError s!"Unknown fpOp: {name}"
  -- Finite domain
  | .finDomainLit val size => do
    let finSort := mkApp (mkConst ``Fin) (mkNatLit size)
    Meta.mkNumeral finSort val

/-! ## Inductive type registration -/

/-- Register a z3py-style datatype as a real Lean inductive type.

Builds a `Declaration.inductDecl`, adds it to the environment, then
creates accessor and recognizer definitions using `casesOn`. -/
@[python "z3_add_inductive"]
def z3AddInductive (desc : Z3InductiveDesc) : IO Unit := do
  match (← LeanPy.Kernel.envRef.get) with
  | none => throw (IO.userError "no environment loaded")
  | some env =>
    let ctx ← LeanPy.Kernel.freshCoreContext
    let cs : Core.State := { env }
    let act : CoreM Unit := do
      Meta.MetaM.run' do
        let tName := Name.mkSimple desc.name
        let tConst := mkConst tName
        -- varMap with self-reference for recursive types
        let varMap : Std.HashMap String Lean.Expr :=
          ({} : Std.HashMap String Lean.Expr).insert desc.name tConst

        -- Build constructor types
        let mut ctors : Array Constructor := #[]
        for ctor in desc.ctors do
          let cName := Name.mkStr tName ctor.name
          -- Build ctor type: field1Sort → field2Sort → ... → T
          let mut cType := tConst
          for field in ctor.fields.reverse do
            let fieldSort ← compileSort varMap field.sort
            cType := Expr.forallE field.name.toName fieldSort cType .default
          ctors := ctors.push { name := cName, type := cType }

        -- Create the inductive declaration
        let indType : InductiveType := {
          name := tName
          type := mkSort (.succ .zero)  -- Type
          ctors := ctors.toList
        }
        let decl := Declaration.inductDecl [] 0 [indType] false
        addDecl decl

        -- Generate auxiliary declarations (casesOn, recOn, noConfusion, etc.)
        mkRecOn tName
        mkCasesOn tName
        mkCtorIdx tName
        mkCtorElim tName
        mkNoConfusion tName

        -- Build accessor defs
        let casesOnName := Name.mkStr tName "casesOn"
        for ctorIdx in [:desc.ctors.size] do
          let ctor := desc.ctors[ctorIdx]!
          for fieldIdx in [:ctor.fields.size] do
            let field := ctor.fields[fieldIdx]!
            let accName := Name.mkStr tName field.name
            let fieldSortExpr ← compileSort varMap field.sort
            -- fun (x : T) => @T.casesOn (fun _ => FieldSort) x branch0 branch1 ...
            Meta.withLocalDecl `x .default tConst fun x => do
              let motive := Expr.lam `_ tConst fieldSortExpr .default
              let mut branches : Array Lean.Expr := #[]
              for branchIdx in [:desc.ctors.size] do
                let branchCtor := desc.ctors[branchIdx]!
                -- Build lambda over this ctor's fields
                let mut fieldTypes : Array (Name × Lean.Expr) := #[]
                for f in branchCtor.fields do
                  let ft ← compileSort varMap f.sort
                  fieldTypes := fieldTypes.push (f.name.toName, ft)
                if branchIdx == ctorIdx then
                  -- Target branch: return the target field
                  let branch ← Meta.withLocalDeclsD (fieldTypes.map fun (n, t) => (n, fun _ => pure t)) fun fvars => do
                    Meta.mkLambdaFVars fvars fvars[fieldIdx]!
                  branches := branches.push branch
                else
                  -- Non-target branch: sorryAx (universe 1 for Type, 0 for Prop)
                  let branch ← Meta.withLocalDeclsD (fieldTypes.map fun (n, t) => (n, fun _ => pure t)) fun fvars => do
                    let sorryVal := mkApp2 (mkConst ``sorryAx [.succ .zero]) fieldSortExpr (mkConst ``false)
                    Meta.mkLambdaFVars fvars sorryVal
                  branches := branches.push branch
              let universeLevel := Level.succ .zero
              let result := mkAppN (mkConst casesOnName [universeLevel]) (#[motive, x] ++ branches)
              let body ← Meta.mkLambdaFVars #[x] result
              let accType := Expr.forallE `x tConst fieldSortExpr .default
              let accDecl := Declaration.defnDecl {
                name := accName
                levelParams := []
                type := accType
                value := body
                hints := .abbrev
                safety := .safe
              }
              addDecl accDecl

        -- Build recognizer defs
        let propExpr := mkSort .zero
        for ctorIdx in [:desc.ctors.size] do
          let ctor := desc.ctors[ctorIdx]!
          let recName := Name.mkStr tName s!"is_{ctor.name}"
          Meta.withLocalDecl `x .default tConst fun x => do
            let motive := Expr.lam `_ tConst propExpr .default
            let mut branches : Array Lean.Expr := #[]
            for branchIdx in [:desc.ctors.size] do
              let branchCtor := desc.ctors[branchIdx]!
              let mut fieldTypes : Array (Name × Lean.Expr) := #[]
              for f in branchCtor.fields do
                let ft ← compileSort varMap f.sort
                fieldTypes := fieldTypes.push (f.name.toName, ft)
              let val := if branchIdx == ctorIdx then mkConst ``True else mkConst ``False
              let branch ← Meta.withLocalDeclsD (fieldTypes.map fun (n, t) => (n, fun _ => pure t)) fun fvars => do
                Meta.mkLambdaFVars fvars val
              branches := branches.push branch
            let result := mkAppN (mkConst casesOnName [.succ .zero]) (#[motive, x] ++ branches)
            let body ← Meta.mkLambdaFVars #[x] result
            let recType := Expr.forallE `x tConst propExpr .default
            let recDecl := Declaration.defnDecl {
              name := recName
              levelParams := []
              type := recType
              value := body
              hints := .abbrev
              safety := .safe
            }
            addDecl recDecl

    let (_, cs') ← act.toIO ctx cs
    LeanPy.Kernel.envRef.set (some cs'.env)

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
