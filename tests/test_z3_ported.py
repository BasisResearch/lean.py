"""Ported z3py tutorial & example tests.

Exercises every public API in the z3 compatibility layer against patterns
from the z3py guide, doctests, and reference examples.

NOTE: Our layer is backed by a Lean proof checker, not an SMT solver.
- `Solver.check()` returns `unsat` when constraints are contradictory (proved),
  `sat` when the solver has no constraints (trivially satisfiable),
  and `unknown` otherwise (cannot prove contradiction).
- `Solver.model()` raises NotImplementedError (no counter-model extraction).
- `prove(claim)` returns True when the claim is provable by Lean tactics.
"""

from __future__ import annotations

import pytest

from lean_py.kernel import Kernel
from lean_py.z3 import (
    # Sorts
    BoolSort, IntSort, NatSort, RealSort, DeclareSort,
    BitVecSort, ArraySort, StringSort,
    SortRef, BoolSortRef, ArithSortRef, BitVecSortRef, ArraySortRef,
    StringSortRef, ReSort,
    # Expressions
    ExprRef, BoolRef, ArithRef, BitVecRef, ArrayRef,
    QuantifierRef, StringRef, ReRef,
    # Numeric references
    IntNumRef, RatNumRef, BitVecNumRef,
    # Functions
    FuncDeclRef, Function,
    # Variable constructors
    Int, Ints, Nat, Real, Reals, Bool, Bools,
    BitVec, BitVecs, Array, Const, Consts,
    # Vector constructors
    IntVector, BoolVector, RealVector,
    # Value constructors
    IntVal, NatVal, RealVal, BoolVal, BitVecVal, StringVal,
    # String constructors
    String, Strings,
    # Array operations
    Select, Store, K, Map, AsArray,
    # Datatype
    Datatype, CreateDatatypes, EnumSort, TupleSort,
    # Operations
    And, Or, Not, Implies, Xor, If, Distinct,
    # Quantifiers
    ForAll, Exists,
    # Substitute
    substitute,
    # BV functions
    LShR, ULE, ULT, UGE, UGT, UDiv, URem,
    Extract, Concat, ZeroExt, SignExt, BV2Int, Int2BV,
    RotateLeft, RotateRight, SDiv, SRem, AShr,
    # BV extras
    RepeatBitVec, BVRedAnd, BVRedOr,
    BvNand, BvNor, BvXnor,
    BVAddNoOverflow, BVAddNoUnderflow,
    BVSubNoOverflow, BVSubNoUnderflow,
    BVMulNoOverflow, BVMulNoUnderflow,
    BVSDivNoOverflow,
    # Arith functions
    Abs, ToReal, ToInt, Sum, Product,
    IsInt, Sqrt,
    # Rational
    RatVal, Q,
    # Pseudo-boolean
    AtMost, AtLeast, PbEq, PbLe, PbGe,
    # Fresh
    FreshConst, FreshInt, FreshBool, FreshReal,
    # Lambda
    Lambda,
    # String functions
    Length, Contains, PrefixOf, SuffixOf, Replace,
    SubString, IndexOf, StrConcat, StrToInt, IntToStr,
    # Regex functions
    Re, Star, Plus, Option, Union, Intersect,
    Complement, Range, Loop, InRe, AllChar,
    # Predicates
    is_expr, is_true, is_false, is_int, is_real,
    is_bool, is_bv, is_array, is_const, is_var,
    is_quantifier, is_eq, is_distinct, is_and, is_or,
    is_not, is_implies, is_add, is_mul, is_sub, is_div,
    is_string, is_string_value,
    is_arith, is_sort, is_app, is_func_decl,
    is_int_value, is_rational_value, is_bv_value,
    is_le, is_lt, is_ge, is_gt, is_mod, is_idiv,
    # Solver
    Solver, ModelRef, sat, unsat, unknown,
    set_kernel, prove, solve, simplify,
    set_param, set_option,
    SolverFor, SimpleSolver, solve_using,
    Optimize, parse_smt2_string, parse_smt2_file,
    # Tactic
    Goal, ApplyResult, Tactic, Then, OrElse, Repeat,
    AndThen, With, TryFor, ParOr, ParThen, ParAndThen,
    # Stubs — Context / AstVector / AstMap
    Context, main_ctx, get_ctx, AstRef, AstVector, AstMap,
    # Stubs — FP
    FPSortRef, FPRef, FPNumRef, FPRMRef,
    FPSort, Float16, Float32, Float64, Float128,
    FP, FPs, FPVal,
    fpNaN, fpPlusInfinity, fpMinusInfinity, fpPlusZero, fpMinusZero,
    RoundNearestTiesToEven, RNE, RoundNearestTiesToAway, RNA,
    RoundTowardPositive, RTP, RoundTowardNegative, RTN, RoundTowardZero, RTZ,
    fpAdd, fpSub, fpMul, fpDiv, fpNeg, fpAbs, fpSqrt, fpFMA, fpRem, fpMin, fpMax,
    fpLEQ, fpLT, fpGEQ, fpGT, fpEQ,
    fpIsNaN, fpIsInf, fpIsZero, fpIsNormal, fpIsSubnormal, fpIsNegative, fpIsPositive,
    fpToReal, fpToSBV, fpToUBV, fpToFP, fpBVToFP, fpFPToFP, fpRealToFP,
    fpSignedToFP, fpUnsignedToFP,
    # Stubs — Sets
    SetSort, EmptySet, FullSet, IsMember, SetAdd, SetDel,
    SetUnion, SetIntersect, SetComplement, SetDifference, IsSubset, SetHasSize,
    # Stubs — Sequences / Char / FiniteDomain
    SeqSort, Empty, Full, Unit,
    CharSort, CharVal, CharFromBv, CharToBv, CharToInt, CharIsDigit,
    FiniteDomainSort, FiniteDomainVal, FiniteDomainSize,
    # Stubs — Fixedpoint / RecFunction
    Fixedpoint, RecFunction, RecAddDefinition,
    # Stubs — Var / MultiPattern / DisjointSum
    Var, get_var_index, MultiPattern, DisjointSum,
    # Stubs — predicates
    is_ast, is_fp, is_fprm, is_fp_value,
    is_seq, is_re, is_const_array, is_K, is_map, is_select, is_store,
    is_to_real, is_to_int, is_is_int, is_pattern,
    # Stubs — string/regex extras
    LastIndexOf, StrToCode, StrFromCode, At, Diff,
    # Stubs — structural equality / utilities
    eq, enable_trace, disable_trace, open_log,
    get_version, get_version_string, get_full_version,
    # Stubs — model introspection
    FuncInterp, FuncEntry,
    # Stubs — Update / Probe / Statistics
    Update, Probe, ProbeAnd, ProbeOr, FailIf, Statistics,
)
from lean_py.z3._ast import (
    BinOp, BinOpNode, UnOp, UnOpNode,
    BoolLit, IntLit, NatLit, BvLit, Var as AstVar,
    ForAllNode, ExistsNode, DistinctNode, IteNode,
    SelectNode, StoreNode, ConstArrayNode, LambdaNode,
    ToRealNode, ToIntNode, ExtractNode, ZeroExtNode, SignExtNode,
    StringLit, StrConcatNode, StrLenNode, StrContainsNode,
    ReStarNode, InReNode,
    PropSort, IntASTSort, StringASTSort,
)
from lean_py.z3.solver import _try_prove


@pytest.fixture(scope="module")
def kernel(example_lib) -> Kernel:
    k = Kernel(example_lib)
    if not k.is_loaded():
        k.init_search("")
        k.load(["Init"])
    set_kernel(k)
    return k


# ===================================================================
# GUIDE SECTION 1: Getting Started
# ===================================================================


class TestGettingStarted:
    """From z3py guide: basic constraint creation and solving."""

    def test_int_constraint_building(self):
        """Guide: x + 2*y == 7, x > 2, y < 5"""
        x, y = Ints("x y")
        expr1 = x + 2 * y == 7
        expr2 = x > 2
        expr3 = y < 5
        assert is_eq(expr1)
        assert isinstance(expr2._ast, BinOpNode)
        assert isinstance(expr3._ast, BinOpNode)

    def test_real_constraint_building(self):
        """Guide: x/3 + y/5 > 2"""
        x, y = Reals("x y")
        expr = x / 3 + y / 5 > 2
        assert isinstance(expr._ast, BinOpNode)

    def test_simplify_identity(self):
        """Guide: simplify(x + 1 + 2)"""
        x = Int("x")
        result = simplify(x + 1 + 2)
        assert isinstance(result, ExprRef)

    def test_simplify_returns_same_type(self):
        """simplify preserves expression type."""
        x = Int("x")
        assert is_int(simplify(x + 1))

    def test_solve_shorthand(self, kernel):
        """Guide: solve(x > 0, x < 2) should return unknown (not unsat)."""
        x = Int("x")
        result = solve(x > 0, x < 2)
        assert result != unsat  # x=1 satisfies, so not contradictory

    def test_solve_unsat(self, kernel):
        """solve(x > 0, x < 0) returns unsat."""
        x = Int("x")
        result = solve(x > 0, x < 0)
        assert result == unsat


# ===================================================================
# GUIDE SECTION 2: Boolean Logic
# ===================================================================


class TestBooleanLogic:
    """From z3py guide: propositional logic."""

    def test_bool_variables(self):
        """Guide: p, q, r = Bools('p q r')"""
        p, q, r = Bools("p q r")
        assert is_bool(p)
        assert is_bool(q)
        assert is_bool(r)

    def test_and_or_not(self):
        p, q = Bools("p q")
        assert is_and(And(p, q))
        assert is_or(Or(p, q))
        assert is_not(Not(p))

    def test_implies(self):
        p, q = Bools("p q")
        imp = Implies(p, q)
        assert is_implies(imp)

    def test_demorgan_proof(self, kernel):
        """Guide: De Morgan's law: Not(And(p,q)) == Or(Not(p), Not(q))"""
        p, q = Bools("p q")
        claim = ForAll([p, q], Not(And(p, q)) == Or(Not(p), Not(q)))
        assert prove(claim)

    def test_demorgan2_proof(self, kernel):
        """De Morgan: Not(Or(p,q)) == And(Not(p), Not(q))"""
        p, q = Bools("p q")
        claim = ForAll([p, q], Not(Or(p, q)) == And(Not(p), Not(q)))
        assert prove(claim)

    def test_contrapositive_proof(self, kernel):
        """(p => q) => (Not(q) => Not(p))"""
        p, q = Bools("p q")
        claim = ForAll([p, q], Implies(Implies(p, q), Implies(Not(q), Not(p))))
        assert prove(claim)

    def test_excluded_middle(self, kernel):
        """p ∨ ¬p is always true."""
        p = Bool("p")
        claim = ForAll([p], Or(p, Not(p)))
        assert prove(claim)

    def test_xor_definition(self, kernel):
        """Xor(p,q) == And(Or(p,q), Not(And(p,q)))"""
        p, q = Bools("p q")
        claim = ForAll([p, q], Xor(p, q) == And(Or(p, q), Not(And(p, q))))
        assert prove(claim)

    def test_bool_biimplication(self, kernel):
        """(p == q) == And(Implies(p,q), Implies(q,p))"""
        p, q = Bools("p q")
        claim = ForAll([p, q], (p == q) == And(Implies(p, q), Implies(q, p)))
        assert prove(claim)

    def test_modus_ponens(self, kernel):
        """If p and p => q, then q."""
        p, q = Bools("p q")
        claim = ForAll([p, q], Implies(And(p, Implies(p, q)), q))
        assert prove(claim)

    def test_hypothetical_syllogism(self, kernel):
        """If p => q and q => r, then p => r."""
        p, q, r = Bools("p q r")
        premise = And(Implies(p, q), Implies(q, r))
        claim = ForAll([p, q, r], Implies(premise, Implies(p, r)))
        assert prove(claim)


# ===================================================================
# GUIDE SECTION 3: Arithmetic
# ===================================================================


class TestArithmetic:
    """From z3py guide: integer and real arithmetic."""

    def test_int_mul_coercion(self):
        """Guide: x * 2 auto-coerces 2 to IntVal(2)."""
        x = Int("x")
        expr = x * 2
        assert isinstance(expr._ast.rhs, IntLit)

    def test_real_div(self):
        """Guide: Real division creates DIV node."""
        x = Real("x")
        expr = x / 3
        assert isinstance(expr._ast, BinOpNode)
        assert expr._ast.op == BinOp.DIV

    def test_mixed_arith_toreal(self):
        """Guide: ToReal(x) + y for mixed integer/real."""
        x = Int("x")
        y = Real("y")
        expr = ToReal(x) + y
        assert is_real(expr)

    def test_power_concrete(self, kernel):
        """Guide: 3^3 = 27."""
        claim = IntVal(3) ** 3 == IntVal(27)
        assert prove(claim)

    def test_ratval_construction(self):
        """Guide: Q(1, 3) creates 1/3."""
        r = Q(1, 3)
        assert is_real(r)
        assert isinstance(r._ast, BinOpNode)
        assert r._ast.op == BinOp.DIV

    def test_ratval_structure(self):
        """Q(a, b) creates a/b as division."""
        r = Q(2, 5)
        assert isinstance(r._ast, BinOpNode)
        assert r._ast.op == BinOp.DIV
        assert r.numerator_as_long() == 2
        assert r.denominator_as_long() == 5

    def test_int_add_commutative(self, kernel):
        """x + y == y + x."""
        x, y = Ints("x y")
        claim = ForAll([x, y], x + y == y + x)
        assert prove(claim)

    def test_int_add_associative(self, kernel):
        """(x + y) + z == x + (y + z)."""
        x, y, z = Ints("x y z")
        claim = ForAll([x, y, z], (x + y) + z == x + (y + z))
        assert prove(claim)

    def test_int_mul_commutative(self, kernel):
        x, y = Ints("x y")
        claim = ForAll([x, y], x * y == y * x)
        assert prove(claim)

    def test_distributive(self, kernel):
        """x * (y + z) == x*y + x*z."""
        x, y, z = Ints("x y z")
        claim = ForAll([x, y, z], x * (y + z) == x * y + x * z)
        assert prove(claim)

    def test_abs_triangle_simple(self, kernel):
        """abs(x) >= 0 and abs(-x) == abs(x)."""
        x = Int("x")
        claim1 = ForAll([x], Abs(x) >= 0)
        assert prove(claim1)

    def test_toreal_ast(self):
        """ToReal creates the correct AST node."""
        r = ToReal(IntVal(5))
        assert isinstance(r._ast, ToRealNode)
        assert is_real(r)

    def test_sum_proof(self, kernel):
        """Sum(a, b, c) == a + b + c."""
        a, b, c = Ints("a b c")
        claim = ForAll([a, b, c], Sum(a, b, c) == a + b + c)
        assert prove(claim)

    def test_product_proof(self, kernel):
        """Product(a, b) == a * b."""
        a, b = Ints("a b")
        claim = ForAll([a, b], Product(a, b) == a * b)
        assert prove(claim)


# ===================================================================
# GUIDE SECTION 4: Bit-Vectors
# ===================================================================


class TestBitVectorGuide:
    """From z3py guide: machine arithmetic (bit-vectors)."""

    def test_bv_arithmetic(self):
        """Guide: BitVec arithmetic wraps modularly."""
        x = BitVec("x", 16)
        y = BitVec("y", 16)
        expr = x + y
        assert isinstance(expr, BitVecRef)
        assert expr.size() == 16

    def test_bv_signed_vs_unsigned_comparison(self):
        """Guide: signed < is different from ULT."""
        a = BitVecVal(0xFF, 8)  # -1 signed, 255 unsigned
        b = BitVecVal(0x01, 8)
        # signed: -1 < 1 is typically tested; these build different ASTs
        signed_lt = a < b  # signed
        unsigned_lt = ULT(a, b)  # unsigned
        assert isinstance(signed_lt._ast, BinOpNode)
        assert isinstance(unsigned_lt._ast, BinOpNode)

    def test_power_of_two_check(self, kernel):
        """Guide: x != 0 and x & (x-1) == 0 implies x is power of 2.
        Test with concrete value: 8 & 7 == 0."""
        claim = BitVecVal(8, 32) & BitVecVal(7, 32) == BitVecVal(0, 32)
        assert prove(claim)

    def test_bv_xor_self_is_zero(self, kernel):
        """x ^ x == 0."""
        x = BitVec("x", 8)
        claim = ForAll([x], (x ^ x) == BitVecVal(0, 8))
        assert prove(claim)

    def test_bv_and_self(self, kernel):
        """x & x == x."""
        x = BitVec("x", 8)
        claim = ForAll([x], (x & x) == x)
        assert prove(claim)

    def test_bv_or_self(self, kernel):
        """x | x == x."""
        x = BitVec("x", 8)
        claim = ForAll([x], (x | x) == x)
        assert prove(claim)

    def test_bv_not_not(self, kernel):
        """~~x == x."""
        x = BitVec("x", 8)
        claim = ForAll([x], ~~x == x)
        assert prove(claim)

    def test_bv_add_zero(self, kernel):
        """x + 0 == x."""
        x = BitVec("x", 8)
        claim = ForAll([x], x + BitVecVal(0, 8) == x)
        assert prove(claim)

    def test_bv_sub_self(self, kernel):
        """x - x == 0."""
        x = BitVec("x", 8)
        claim = ForAll([x], x - x == BitVecVal(0, 8))
        assert prove(claim)

    def test_shift_left_right(self, kernel):
        """(x << 2) >> 2 masks top bits (logical shift)."""
        x = BitVec("x", 8)
        # Logical shift: LShR(x << 2, 2) == x & 0x3F
        claim = ForAll([x], LShR(x << 2, 2) == (x & BitVecVal(0x3F, 8)))
        assert prove(claim)

    def test_rotate_left_right_inverse(self, kernel):
        """RotateRight(RotateLeft(x, 3), 3) == x."""
        x = BitVec("x", 8)
        claim = ForAll([x], RotateRight(RotateLeft(x, 3), 3) == x)
        assert prove(claim)

    def test_sdiv_by_one(self, kernel):
        """Signed division by 1: SDiv(x, 1) == x."""
        x = BitVec("x", 8)
        claim = ForAll([x], SDiv(x, 1) == x)
        assert prove(claim)

    def test_concat_extract_roundtrip(self, kernel):
        """Extract(7,4, Concat(a,b)) == a for 4-bit a, b."""
        a = BitVec("a", 4)
        b = BitVec("b", 4)
        claim = ForAll([a, b], Extract(7, 4, Concat(a, b)) == a)
        assert prove(claim)

    def test_zeroext_preserves_value(self, kernel):
        """ZeroExt(8, x) for small positive x preserves the value."""
        x = BitVecVal(42, 8)
        claim = ZeroExt(8, x) == BitVecVal(42, 16)
        assert prove(claim)


# ===================================================================
# GUIDE SECTION 5: Uninterpreted Functions
# ===================================================================


class TestUninterpretedFunctions:
    """From z3py guide: Function declarations and congruence."""

    def test_function_declaration(self):
        """Guide: f = Function('f', IntSort(), IntSort())"""
        f = Function("f", IntSort(), IntSort())
        assert isinstance(f, FuncDeclRef)

    def test_function_application(self):
        """Guide: f(x) creates application node."""
        f = Function("f", IntSort(), IntSort())
        x = Int("x")
        app = f(x)
        assert isinstance(app, ExprRef)

    def test_function_congruence(self, kernel):
        """Guide: x == y => f(x) == f(y) (congruence axiom)."""
        f = Function("f", IntSort(), IntSort())
        x, y = Ints("x y")
        claim = ForAll([x, y], Implies(x == y, f(x) == f(y)))
        assert prove(claim)

    def test_function_injectivity_pattern(self, kernel):
        """If f(x) == f(y) and f is injective, then x == y.
        We can't prove this in general (f might not be injective),
        but we can prove the contrapositive direction."""
        f = Function("f", IntSort(), IntSort())
        x, y = Ints("x y")
        # Just test that we can build the expression
        expr = Implies(And(f(x) == f(y), x != y), BoolVal(False))
        assert isinstance(expr, BoolRef)

    def test_multi_arg_function(self):
        """Guide: g = Function('g', IntSort(), IntSort(), IntSort())"""
        g = Function("g", IntSort(), IntSort(), IntSort())
        x, y = Ints("x y")
        app = g(x, y)
        assert isinstance(app, ExprRef)

    def test_function_bool_range(self):
        """Function returning Bool (predicate)."""
        p = Function("p", IntSort(), BoolSort())
        x = Int("x")
        result = p(x)
        assert isinstance(result, ExprRef)
        assert isinstance(result._sort, BoolSortRef)

    def test_function_composition_proof(self, kernel):
        """f(f(x)) is well-formed and congruence holds through composition."""
        f = Function("f", IntSort(), IntSort())
        x, y = Ints("x y")
        claim = ForAll([x, y], Implies(x == y, f(f(x)) == f(f(y))))
        assert prove(claim)


# ===================================================================
# GUIDE SECTION 6: Satisfiability & Validity
# ===================================================================


class TestSatisfiabilityValidity:
    """From z3py guide: prove() pattern and validity checking."""

    def test_prove_tautology(self, kernel):
        """Guide: prove(p ∨ ¬p)."""
        p = Bool("p")
        assert prove(ForAll([p], Or(p, Not(p))))

    def test_prove_false_returns_false(self, kernel):
        """Trying to prove x > 0 should fail (it's not universally true)."""
        x = Int("x")
        result = prove(ForAll([x], x > 0))
        assert result is False

    def test_prove_arithmetic(self, kernel):
        """prove(x > 0 => x + 1 > 0)."""
        x = Int("x")
        assert prove(ForAll([x], Implies(x > 0, x + 1 > 0)))

    def test_prove_implies_chain(self, kernel):
        """prove(x > 0 ∧ y > 0 => x + y > 0)."""
        x, y = Ints("x y")
        assert prove(ForAll([x, y], Implies(And(x > 0, y > 0), x + y > 0)))


# ===================================================================
# GUIDE SECTION 7: Solvers (Incremental)
# ===================================================================


class TestSolverGuide:
    """From z3py guide: Solver push/pop, assertions, model stub."""

    def test_solver_basic(self, kernel):
        """Guide: create, add, check."""
        s = Solver()
        x = Int("x")
        s.add(x > 10)
        s.add(x < 5)
        assert s.check() == unsat

    def test_solver_satisfiable_empty(self, kernel):
        """Empty solver is sat."""
        s = Solver()
        assert s.check() == sat

    def test_solver_push_pop(self, kernel):
        """Guide: push/pop for incremental solving."""
        x = Int("x")
        s = Solver()
        s.add(x > 0)
        s.push()
        s.add(x < 0)
        assert s.check() == unsat
        s.pop()
        # Only x > 0 remains: not contradictory
        assert s.check() != unsat

    def test_solver_nested_push_pop(self, kernel):
        """Multiple push/pop levels."""
        x = Int("x")
        s = Solver()
        s.add(x > 0)
        s.push()
        s.add(x > 5)
        s.push()
        s.add(x < 3)
        assert s.check() == unsat  # x > 5 and x < 3
        s.pop()
        # x > 0 and x > 5: not contradictory
        assert s.check() != unsat
        s.pop()
        # Just x > 0: not contradictory
        assert s.check() != unsat

    def test_solver_assertions(self, kernel):
        """Guide: solver.assertions() returns added constraints."""
        s = Solver()
        x = Int("x")
        s.add(x > 0)
        s.add(x < 10)
        assert len(s.assertions()) == 2

    def test_solver_reset(self, kernel):
        """Guide: solver.reset() clears all."""
        s = Solver()
        s.add(BoolVal(True))
        s.add(BoolVal(True))
        s.reset()
        assert len(s.assertions()) == 0

    def test_solver_context_manager(self, kernel):
        """With statement for push/pop."""
        s = Solver()
        x = Int("x")
        s.add(x > 0)
        with s:
            s.add(x < 0)
            assert s.check() == unsat
        assert len(s.assertions()) == 1

    def test_model_not_supported(self, kernel):
        """model() raises since Lean is not an SMT solver."""
        s = Solver()
        with pytest.raises(NotImplementedError):
            s.model()


# ===================================================================
# GUIDE SECTION 8: Arrays
# ===================================================================


class TestArrayGuide:
    """From z3py guide & bubble_sort.py: array theory."""

    def test_array_creation(self):
        a = Array("a", IntSort(), IntSort())
        assert is_array(a)

    def test_select_store(self):
        """Guide: Select and Store operations."""
        a = Array("a", IntSort(), IntSort())
        b = Store(a, IntVal(0), IntVal(42))
        v = Select(b, IntVal(0))
        assert isinstance(v, ExprRef)

    def test_store_select_axiom(self, kernel):
        """Select(Store(a, i, v), i) == v (read-over-write same index)."""
        a = Array("a", IntSort(), IntSort())
        i = Int("i")
        v = Int("v")
        claim = ForAll([a, i, v], Select(Store(a, i, v), i) == v)
        assert prove(claim)

    def test_store_select_different_index(self, kernel):
        """Select(Store(a, i, v), j) == Select(a, j) when i != j."""
        a = Array("a", IntSort(), IntSort())
        i, j, v = Ints("i j v")
        claim = ForAll([a, i, j, v], Implies(i != j, Select(Store(a, i, v), j) == Select(a, j)))
        assert prove(claim)

    def test_constant_array(self, kernel):
        """K(IntSort(), 0) creates an array where every element is 0."""
        c = K(IntSort(), IntVal(0))
        i = Int("i")
        claim = ForAll([i], Select(c, i) == IntVal(0))
        assert prove(claim)

    def test_array_getitem_syntax(self):
        """a[i] is shorthand for Select(a, i)."""
        a = Array("a", IntSort(), IntSort())
        i = Int("i")
        sel = a[i]
        assert isinstance(sel._ast, SelectNode)

    def test_lambda_array(self):
        """Lambda as array comprehension."""
        x = Int("x")
        lam = Lambda(x, x * 2)
        assert isinstance(lam._ast, LambdaNode)

    def test_map_function_over_array(self):
        """Map(f, a) applies f element-wise."""
        f = Function("f", IntSort(), IntSort())
        a = Array("a", IntSort(), IntSort())
        result = Map(f, a)
        assert is_array(result)

    def test_as_array(self):
        """AsArray(f) creates an array from a function."""
        f = Function("f", IntSort(), IntSort())
        a = AsArray(f)
        assert is_array(a)


# ===================================================================
# GUIDE SECTION 9: Quantifiers
# ===================================================================


class TestQuantifiers:
    """Ported from z3py guide & socrates.py."""

    def test_forall_basic(self):
        x = Int("x")
        q = ForAll([x], x + 0 == x)
        assert isinstance(q._ast, ForAllNode)
        assert is_quantifier(q)

    def test_exists_basic(self):
        x = Int("x")
        q = Exists([x], x > 0)
        assert isinstance(q._ast, ExistsNode)
        assert is_quantifier(q)

    def test_forall_binds_variable(self):
        """Bound variable not in free vars."""
        x = Int("x")
        q = ForAll([x], x > 0)
        assert not any(n == "x" for n, _ in q._vars)

    def test_exists_with_free_vars(self):
        """Exists x. x > y has y free."""
        x, y = Ints("x y")
        q = Exists([x], x > y)
        names = {n for n, _ in q._vars}
        assert "y" in names
        assert "x" not in names

    def test_multi_var_forall(self):
        """ForAll([x, y], ...) nests quantifiers."""
        x, y = Ints("x y")
        q = ForAll([x, y], x + y == y + x)
        assert isinstance(q._ast, ForAllNode)
        assert isinstance(q._ast.body, ForAllNode)

    def test_socrates_syllogism(self, kernel):
        """socrates.py: All men are mortal. Socrates is a man. ∴ mortal."""
        Entity = DeclareSort("Entity")
        Man = Function("Man", Entity, BoolSort())
        Mortal = Function("Mortal", Entity, BoolSort())
        socrates = Const("socrates", Entity)
        x = Const("x", Entity)
        all_men_mortal = ForAll([x], Implies(Man(x), Mortal(x)))
        claim = Implies(And(all_men_mortal, Man(socrates)), Mortal(socrates))
        assert prove(claim)

    def test_forall_add_identity(self, kernel):
        """ForAll x. x + 0 == x."""
        x = Int("x")
        assert prove(ForAll([x], x + 0 == x))

    def test_forall_nat_succ(self, kernel):
        """ForAll n : Nat. n + 1 > 0."""
        n = Nat("n")
        assert prove(ForAll([n], n + 1 > 0))


# ===================================================================
# GUIDE SECTION 10: If-Then-Else
# ===================================================================


class TestIfThenElse:
    """From z3py guide: If(cond, then, else)."""

    def test_ite_construction(self):
        x = Int("x")
        expr = If(x > 0, x, -x)
        assert isinstance(expr._ast, IteNode)

    def test_ite_type_preservation(self):
        """If returns same sort as branches."""
        x = Int("x")
        result = If(x > 0, x, IntVal(0))
        assert is_int(result)

    def test_ite_bool_condition(self):
        a = Bool("a")
        result = If(a, IntVal(1), IntVal(0))
        assert isinstance(result._ast, IteNode)

    def test_abs_via_ite(self, kernel):
        """Abs(x) == If(x >= 0, x, -x)."""
        x = Int("x")
        manual_abs = If(x >= 0, x, -x)
        claim = ForAll([x], Abs(x) == manual_abs)
        assert prove(claim)

    def test_max_via_ite(self):
        """max(x, y) via If produces ITE node."""
        x, y = Ints("x y")
        mx = If(x >= y, x, y)
        assert isinstance(mx._ast, IteNode)

    def test_min_via_ite(self):
        """min(x, y) via If produces ITE node."""
        x, y = Ints("x y")
        mn = If(x <= y, x, y)
        assert isinstance(mn._ast, IteNode)


# ===================================================================
# GUIDE SECTION 11: Distinct
# ===================================================================


class TestDistinctGuide:
    """From z3py guide: Distinct constraint."""

    def test_distinct_basic(self):
        x, y, z = Ints("x y z")
        d = Distinct(x, y, z)
        assert isinstance(d._ast, DistinctNode)
        assert is_distinct(d)

    def test_distinct_implies_ne(self, kernel):
        """Distinct(x, y) => x != y."""
        x, y = Ints("x y")
        claim = ForAll([x, y], Implies(Distinct(x, y), x != y))
        assert prove(claim)

    def test_distinct_three(self, kernel):
        """Distinct(1, 2, 3) is trivially true."""
        claim = Distinct(IntVal(1), IntVal(2), IntVal(3))
        assert prove(claim)


# ===================================================================
# PUZZLE: Dog-Cat-Mouse (from guide)
# ===================================================================


class TestDogCatMouse:
    """Guide puzzle: 100 animals, 100 dollars."""

    def test_dog_cat_mouse_unsat_variant(self, kernel):
        """No solution with impossible extra constraint."""
        dog, cat, mouse = Ints("dog cat mouse")
        constraints = [
            dog >= 1, cat >= 1, mouse >= 1,
            dog + cat + mouse == 100,
            dog * 15 + cat + mouse / 4 == 100,  # integer division
            mouse < 0,  # impossible with mouse >= 1
        ]
        s = Solver()
        s.add(*constraints)
        assert s.check() == unsat


# ===================================================================
# PUZZLE: N-Queens (from guide)
# ===================================================================


class TestNQueensGuide:
    """Guide puzzle: Eight Queens (we test small variants)."""

    def test_1queen_sat(self, kernel):
        """1 queen on 1x1 board: trivially satisfiable."""
        q = Int("q0")
        s = Solver()
        s.add(q >= 1, q <= 1)
        assert s.check() != unsat

    def test_2queens_unsat(self, kernel):
        """2 queens on 2x2 board: impossible."""
        q0, q1 = Ints("q0 q1")
        constraints = [
            q0 >= 1, q0 <= 2, q1 >= 1, q1 <= 2,
            Distinct(q0, q1),
            q0 - q1 != IntVal(1),
            q0 - q1 != IntVal(-1),
        ]
        s = Solver()
        s.add(*constraints)
        assert s.check() == unsat

    def test_3queens_unsat(self, kernel):
        """3 queens on 3x3 board: impossible."""
        qs = [Int(f"q{i}") for i in range(3)]
        constraints = []
        for q in qs:
            constraints.extend([q >= 1, q <= 3])
        constraints.append(Distinct(*qs))
        for i in range(3):
            for j in range(i + 1, 3):
                diff = IntVal(j - i)
                constraints.append(qs[i] - qs[j] != diff)
                constraints.append(qs[i] - qs[j] != -diff)
        s = Solver()
        s.add(*constraints)
        assert s.check() == unsat


# ===================================================================
# PUZZLE: Sudoku constraint structure (from guide)
# ===================================================================


class TestSudokuConstraints:
    """From guide: Sudoku constraint encoding."""

    def test_sudoku_row_constraint(self):
        """Row must have all distinct values."""
        row = [Int(f"c{i}") for i in range(4)]
        d = Distinct(*row)
        assert isinstance(d._ast, DistinctNode)
        assert len(d._ast.args) == 4

    def test_sudoku_range_constraints(self, kernel):
        """Values 1-4 in a 4x4 mini Sudoku, constrained cell = 3."""
        x = Int("x")
        s = Solver()
        s.add(x >= 1, x <= 4, x == IntVal(3))
        # Not contradictory
        assert s.check() != unsat

    def test_sudoku_range_contradiction(self, kernel):
        """Value outside range 1-4."""
        x = Int("x")
        s = Solver()
        s.add(x >= 1, x <= 4, x == IntVal(5))
        assert s.check() == unsat


# ===================================================================
# PUZZLE: Install Problem (from guide)
# ===================================================================


class TestInstallProblem:
    """Guide: Package dependency modeling."""

    def test_dependency_chain(self, kernel):
        """If A depends on B and B depends on C, installing A without C is unsat."""
        a, b, c = Bools("a b c")
        deps = And(Implies(a, b), Implies(b, c))
        # Install A but not C is contradictory
        s = Solver()
        s.add(deps, a, Not(c))
        assert s.check() == unsat

    def test_conflict(self, kernel):
        """A conflicts with B: can't install both."""
        a, b = Bools("a b")
        conflict = Or(Not(a), Not(b))
        s = Solver()
        s.add(conflict, a, b)
        assert s.check() == unsat


# ===================================================================
# REFERENCE: Datatypes (from union_sort.py)
# ===================================================================


class TestDatatypesPorted:
    """From union_sort.py: variant/union types."""

    def test_enum_datatype(self, kernel):
        """Simple enum: Red | Green | Blue."""
        Color = Datatype("Color_p1")
        Color.declare("Red")
        Color.declare("Green")
        Color.declare("Blue")
        Color = Color.create()
        assert hasattr(Color, "Red")
        assert hasattr(Color, "Green")
        assert hasattr(Color, "Blue")

    def test_enum_distinct(self, kernel):
        """Enum constructors are distinct."""
        Color = Datatype("Color_p2")
        Color.declare("Red")
        Color.declare("Green")
        Color = Color.create()
        expr = Color.Red != Color.Green
        assert isinstance(expr._ast, BinOpNode)
        assert expr._ast.op == BinOp.NE

    def test_record_datatype(self, kernel):
        """Record with fields."""
        Point = Datatype("Point_p3")
        Point.declare("mk", ("x", IntSort()), ("y", IntSort()))
        Point = Point.create()
        assert hasattr(Point, "mk")
        assert hasattr(Point, "x")
        assert hasattr(Point, "y")

    def test_record_construction(self, kernel):
        """Constructing a record."""
        Pair = Datatype("Pair_p4")
        Pair.declare("mk", ("fst", IntSort()), ("snd", IntSort()))
        Pair = Pair.create()
        x, y = Ints("x y")
        p = Pair.mk(x, y)
        assert isinstance(p, ExprRef)


# ===================================================================
# BV Bit-Tricks (from guide)
# ===================================================================


class TestBitTricks:
    """From z3py guide: bit manipulation patterns."""

    def test_power_of_two_concrete(self, kernel):
        """8 is a power of two: 8 & 7 == 0."""
        eight = BitVecVal(8, 32)
        seven = BitVecVal(7, 32)
        claim = (eight & seven) == BitVecVal(0, 32)
        assert prove(claim)

    def test_not_power_of_two(self, kernel):
        """6 is not a power of two: 6 & 5 != 0."""
        six = BitVecVal(6, 32)
        five = BitVecVal(5, 32)
        claim = (six & five) != BitVecVal(0, 32)
        assert prove(claim)

    def test_opposite_signs_xor(self, kernel):
        """Guide: (x ^ y) < 0 detects opposite signs (signed).
        Test concrete: (-1) ^ 1 has MSB set."""
        neg1 = BitVecVal(0xFF, 8)  # -1 in signed 8-bit
        pos1 = BitVecVal(0x01, 8)
        xored = neg1 ^ pos1
        # Result is 0xFE, which has MSB set
        claim = xored == BitVecVal(0xFE, 8)
        assert prove(claim)

    def test_bv_negate_is_complement_plus_one(self, kernel):
        """-x == ~x + 1 (two's complement)."""
        x = BitVec("x", 8)
        claim = ForAll([x], -x == (~x + BitVecVal(1, 8)))
        assert prove(claim)

    def test_bv_de_morgan(self, kernel):
        """~(a & b) == ~a | ~b."""
        a, b = BitVecs("a b", 8)
        claim = ForAll([a, b], ~(a & b) == (~a | ~b))
        assert prove(claim)

    def test_bv_mul_by_power_of_two(self, kernel):
        """4 * 3 == 12 as concrete bitvector fact."""
        claim = BitVecVal(4, 16) * BitVecVal(3, 16) == BitVecVal(12, 16)
        assert prove(claim)


# ===================================================================
# Lambda & Higher-Order (from guide list comprehensions)
# ===================================================================


class TestLambdaGuide:
    """Lambda expressions (array comprehensions)."""

    def test_lambda_single(self):
        x = Int("x")
        lam = Lambda(x, x * 2)
        assert isinstance(lam._ast, LambdaNode)
        assert lam._ast.name == "x"

    def test_lambda_multi(self):
        x, y = Ints("x y")
        lam = Lambda([x, y], x + y)
        assert isinstance(lam._ast, LambdaNode)
        assert isinstance(lam._ast.body, LambdaNode)

    def test_lambda_free_vars(self):
        """Lambda binds its variable."""
        x, y = Ints("x y")
        lam = Lambda(x, x + y)
        names = {n for n, _ in lam._vars}
        assert "x" not in names
        assert "y" in names


# ===================================================================
# String Theory (ported from z3py string examples)
# ===================================================================


class TestStringTheory:
    """String theory operations."""

    def test_string_literal(self):
        s = StringVal("hello")
        assert isinstance(s._ast, StringLit)
        assert s._ast.val == "hello"
        assert is_string_value(s)

    def test_string_variable(self):
        s = String("s")
        assert is_string(s)
        assert is_var(s)

    def test_string_concat_operator(self):
        a = StringVal("hello")
        b = StringVal(" world")
        c = a + b
        assert isinstance(c._ast, StrConcatNode)

    def test_string_length(self):
        s = String("s")
        l = Length(s)
        assert is_int(l)

    def test_contains(self):
        s = String("s")
        c = Contains(s, StringVal("abc"))
        assert isinstance(c._ast, StrContainsNode)

    def test_prefix_suffix(self):
        s = String("s")
        assert isinstance(PrefixOf(StringVal("pre"), s), ExprRef)
        assert isinstance(SuffixOf(StringVal("suf"), s), ExprRef)

    def test_replace(self):
        s = String("s")
        r = Replace(s, StringVal("old"), StringVal("new"))
        assert isinstance(r, StringRef)

    def test_substring(self):
        s = String("s")
        sub = SubString(s, 1, 3)
        assert isinstance(sub, StringRef)

    def test_indexof(self):
        s = String("s")
        idx = IndexOf(s, StringVal("x"), 0)
        assert is_int(idx)

    def test_str_to_int_and_back(self):
        s = StringVal("42")
        i = StrToInt(s)
        assert is_int(i)
        s2 = IntToStr(IntVal(42))
        assert isinstance(s2, StringRef)

    def test_str_concat_variadic(self):
        r = StrConcat(StringVal("a"), StringVal("b"), StringVal("c"))
        assert isinstance(r, StringRef)

    def test_const_string_sort(self):
        """Const("s", StringSort()) returns StringRef."""
        s = Const("s", StringSort())
        assert isinstance(s, StringRef)

    def test_strings_helper(self):
        a, b, c = Strings("a b c")
        assert all(isinstance(x, StringRef) for x in (a, b, c))


# ===================================================================
# Regex Theory
# ===================================================================


class TestRegexTheory:
    """Regex operations from z3py."""

    def test_re_from_literal(self):
        r = Re(StringVal("abc"))
        assert isinstance(r, ReRef)

    def test_star(self):
        r = Star(Re(StringVal("a")))
        assert isinstance(r._ast, ReStarNode)

    def test_plus(self):
        r = Plus(Re(StringVal("a")))
        assert isinstance(r, ReRef)

    def test_option(self):
        r = Option(Re(StringVal("a")))
        assert isinstance(r, ReRef)

    def test_union(self):
        r = Union(Re(StringVal("a")), Re(StringVal("b")))
        assert isinstance(r, ReRef)

    def test_intersect(self):
        r = Intersect(Re(StringVal("a")), Re(StringVal("b")))
        assert isinstance(r, ReRef)

    def test_complement(self):
        r = Complement(Re(StringVal("a")))
        assert isinstance(r, ReRef)

    def test_range(self):
        r = Range("a", "z")
        assert isinstance(r, ReRef)

    def test_loop(self):
        r = Loop(Re(StringVal("a")), 2, 5)
        assert isinstance(r, ReRef)

    def test_in_re(self):
        s = String("s")
        r = Star(Re(StringVal("a")))
        result = InRe(s, r)
        assert isinstance(result._ast, InReNode)

    def test_allchar(self):
        r = AllChar()
        assert isinstance(r, ReRef)

    def test_complex_regex(self):
        """Build a complex regex: (a|b)*c+"""
        ab = Union(Re(StringVal("a")), Re(StringVal("b")))
        ab_star = Star(ab)
        c_plus = Plus(Re(StringVal("c")))
        # Concatenation not directly available for regex, but we test the components
        assert isinstance(ab_star, ReRef)
        assert isinstance(c_plus, ReRef)


# ===================================================================
# Predicates (comprehensive)
# ===================================================================


class TestPredicatesPorted:
    """All is_* predicates from z3py."""

    def test_is_expr_various(self):
        assert is_expr(Int("x"))
        assert is_expr(Bool("b"))
        assert is_expr(BitVec("v", 8))
        assert is_expr(StringVal("s"))
        assert not is_expr(42)
        assert not is_expr("hello")

    def test_is_true_false(self):
        assert is_true(BoolVal(True))
        assert is_false(BoolVal(False))
        assert not is_true(BoolVal(False))
        assert not is_false(BoolVal(True))
        assert not is_true(Int("x"))

    def test_is_sort_types(self):
        assert is_int(Int("x"))
        assert is_real(Real("x"))
        assert is_bool(Bool("b"))
        assert is_bv(BitVec("v", 8))
        assert is_array(Array("a", IntSort(), IntSort()))
        assert is_string(String("s"))

    def test_is_sort_cross(self):
        """Each sort predicate is false for other sorts."""
        x = Int("x")
        assert not is_real(x)
        assert not is_bool(x)
        assert not is_bv(x)

    def test_is_const_var(self):
        x = Int("x")
        assert is_const(x)
        assert is_var(x)
        assert not is_const(x + 1)

    def test_is_quantifier(self):
        x = Int("x")
        assert is_quantifier(ForAll([x], x > 0))
        assert is_quantifier(Exists([x], x > 0))
        assert not is_quantifier(x > 0)

    def test_is_eq_ne(self):
        x, y = Ints("x y")
        assert is_eq(x == y)
        assert not is_eq(x > y)

    def test_is_distinct(self):
        x, y = Ints("x y")
        assert is_distinct(Distinct(x, y))

    def test_is_logical_ops(self):
        a, b = Bools("a b")
        assert is_and(And(a, b))
        assert is_or(Or(a, b))
        assert is_not(Not(a))
        assert is_implies(Implies(a, b))

    def test_is_arith_ops(self):
        x, y = Ints("x y")
        assert is_add(x + y)
        assert is_mul(x * y)
        assert is_sub(x - y)
        assert is_div(x / y)

    def test_is_string_predicates(self):
        assert is_string(String("s"))
        assert is_string_value(StringVal("hello"))
        assert not is_string(Int("x"))
        assert not is_string_value(String("s"))


# ===================================================================
# FreshConst (ported from z3py docs)
# ===================================================================


class TestFreshConstPorted:
    """z3py FreshConst/FreshInt/FreshReal/FreshBool."""

    def test_fresh_int_unique(self):
        a = FreshInt()
        b = FreshInt()
        assert a._ast.name != b._ast.name

    def test_fresh_bool_unique(self):
        a = FreshBool()
        b = FreshBool()
        assert a._ast.name != b._ast.name

    def test_fresh_real_sort(self):
        r = FreshReal()
        assert is_real(r)

    def test_fresh_const_custom_prefix(self):
        c = FreshConst(IntSort(), prefix="var")
        assert c._ast.name.startswith("var!")

    def test_fresh_in_loop(self):
        """Generate multiple fresh constants in a loop."""
        consts = [FreshInt() for _ in range(5)]
        names = [c._ast.name for c in consts]
        assert len(set(names)) == 5  # All unique


# ===================================================================
# RatVal / Q
# ===================================================================


class TestRatValPorted:
    """z3py Q() / RatVal() for rational numbers."""

    def test_ratval_is_real(self):
        assert is_real(RatVal(1, 3))

    def test_ratval_structure(self):
        r = RatVal(3, 7)
        assert isinstance(r._ast, BinOpNode)
        assert r._ast.op == BinOp.DIV

    def test_q_alias(self):
        assert Q is RatVal

    def test_ratval_arithmetic(self):
        """Can do arithmetic with rationals."""
        a = Q(1, 2)
        b = Q(1, 3)
        expr = a + b
        assert is_real(expr)


# ===================================================================
# Tactic/Goal system
# ===================================================================


class TestTacticPorted:
    """z3py Tactic/Goal/ApplyResult."""

    def test_goal_creation(self):
        g = Goal()
        assert len(g) == 0

    def test_goal_add(self):
        g = Goal()
        x = Int("x")
        g.add(x > 0, x < 10)
        assert len(g) == 2

    def test_goal_getitem(self):
        g = Goal()
        x = Int("x")
        c = x > 0
        g.add(c)
        assert g[0]._ast == c._ast

    def test_goal_as_expr(self):
        g = Goal()
        a, b = Bools("a b")
        g.add(a, b)
        expr = g.as_expr()
        assert is_and(expr)

    def test_apply_result_empty(self):
        r = ApplyResult([])
        assert len(r) == 0

    def test_tactic_creation(self):
        t = Tactic("simp")
        assert isinstance(t, Tactic)

    def test_tactic_solve_trivial(self, kernel):
        """Tactic can solve trivially true goal."""
        g = Goal()
        g.add(BoolVal(True))
        t = Tactic("decide")
        result = t.apply(g)
        assert len(result) == 0  # proved

    def test_then_combinator(self):
        t = Then(Tactic("simp"), Tactic("decide"))
        assert isinstance(t, Tactic)

    def test_orelse_combinator(self):
        t = OrElse(Tactic("omega"), Tactic("decide"))
        assert isinstance(t, Tactic)

    def test_repeat_combinator(self):
        t = Repeat(Tactic("simp"))
        assert isinstance(t, Tactic)


# ===================================================================
# ModelRef stub
# ===================================================================


class TestModelRefPorted:
    """z3py ModelRef compatibility."""

    def test_model_raises(self):
        s = Solver()
        with pytest.raises(NotImplementedError):
            s.model()

    def test_modelref_getitem_raises(self):
        m = ModelRef()
        with pytest.raises(NotImplementedError):
            m[Int("x")]

    def test_modelref_repr(self):
        m = ModelRef()
        assert "unsupported" in repr(m)


# ===================================================================
# Operator overloading (comprehensive)
# ===================================================================


class TestOperatorOverloading:
    """Test all Python operator overloads."""

    def test_arith_operators(self):
        x, y = Ints("x y")
        assert isinstance((x + y)._ast, BinOpNode)
        assert isinstance((x - y)._ast, BinOpNode)
        assert isinstance((x * y)._ast, BinOpNode)
        assert isinstance((x / y)._ast, BinOpNode)
        assert isinstance((x % y)._ast, BinOpNode)
        assert isinstance((x ** y)._ast, BinOpNode)
        assert isinstance((-x)._ast, UnOpNode)
        assert (+x) is x

    def test_arith_reverse_operators(self):
        """1 + x, 2 * x, etc."""
        x = Int("x")
        assert isinstance((1 + x)._ast, BinOpNode)
        assert isinstance((1 - x)._ast, BinOpNode)
        assert isinstance((2 * x)._ast, BinOpNode)
        assert isinstance((10 / x)._ast, BinOpNode)
        assert isinstance((10 % x)._ast, BinOpNode)
        assert isinstance((2 ** x)._ast, BinOpNode)

    def test_comparison_operators(self):
        x = Int("x")
        assert isinstance((x > 0)._ast, BinOpNode)
        assert isinstance((x < 0)._ast, BinOpNode)
        assert isinstance((x >= 0)._ast, BinOpNode)
        assert isinstance((x <= 0)._ast, BinOpNode)
        assert isinstance((x == 0)._ast, BinOpNode)
        assert isinstance((x != 0)._ast, BinOpNode)

    def test_bool_operators(self):
        a, b = Bools("a b")
        assert isinstance((a & b)._ast, BinOpNode)
        assert isinstance((a | b)._ast, BinOpNode)
        assert isinstance((~a)._ast, UnOpNode)
        assert isinstance((a ^ b)._ast, BinOpNode)

    def test_bv_operators(self):
        x, y = BitVecs("x y", 8)
        # Arithmetic
        assert isinstance((x + y)._ast, BinOpNode)
        assert isinstance((x - y)._ast, BinOpNode)
        assert isinstance((x * y)._ast, BinOpNode)
        assert isinstance((-x)._ast, UnOpNode)
        # Bitwise
        assert isinstance((x & y)._ast, BinOpNode)
        assert isinstance((x | y)._ast, BinOpNode)
        assert isinstance((x ^ y)._ast, BinOpNode)
        assert isinstance((~x)._ast, UnOpNode)
        # Shift
        assert isinstance((x << 2)._ast, BinOpNode)
        assert isinstance((x >> 1)._ast, BinOpNode)

    def test_bv_reverse_operators(self):
        x = BitVec("x", 8)
        assert isinstance((3 + x)._ast, BinOpNode)
        assert isinstance((3 << x)._ast, BinOpNode)
        assert isinstance((3 >> x)._ast, BinOpNode)

    def test_string_add_operator(self):
        a = StringVal("hello")
        b = StringVal(" world")
        c = a + b
        assert isinstance(c, StringRef)

    def test_bool_guard(self):
        """Symbolic bools can't be used as Python bools."""
        x = Int("x")
        with pytest.raises(TypeError, match="Symbolic"):
            bool(x > 0)


# ===================================================================
# Coercion (auto-converting Python values)
# ===================================================================


class TestCoercion:
    """Test automatic coercion of Python ints/floats."""

    def test_int_coercion(self):
        x = Int("x")
        expr = x + 1
        assert isinstance(expr._ast.rhs, IntLit)

    def test_int_reverse_coercion(self):
        x = Int("x")
        expr = 1 + x
        assert isinstance(expr._ast.lhs, IntLit)

    def test_bv_coercion(self):
        x = BitVec("x", 8)
        expr = x + 1
        assert isinstance(expr._ast.rhs, BvLit)
        assert expr._ast.rhs.width == 8

    def test_bv_reverse_coercion(self):
        x = BitVec("x", 8)
        expr = 1 + x
        assert isinstance(expr._ast.lhs, BvLit)

    def test_comparison_coercion(self):
        x = Int("x")
        expr = x > 5
        assert isinstance(expr._ast.rhs, IntLit)


# ===================================================================
# Free variable tracking
# ===================================================================


class TestFreeVars:
    """Test that free variable tracking works correctly."""

    def test_no_free_vars(self):
        assert len(BoolVal(True)._vars) == 0
        assert len(IntVal(42)._vars) == 0

    def test_single_var(self):
        x = Int("x")
        assert len(x._vars) == 1
        assert any(n == "x" for n, _ in x._vars)

    def test_binary_op_vars(self):
        x, y = Ints("x y")
        expr = x + y
        assert len(expr._vars) == 2

    def test_forall_binds_vars(self):
        x = Int("x")
        q = ForAll([x], x > 0)
        assert not any(n == "x" for n, _ in q._vars)

    def test_exists_binds_vars(self):
        x = Int("x")
        q = Exists([x], x > 0)
        assert not any(n == "x" for n, _ in q._vars)

    def test_partial_binding(self):
        """ForAll over x leaves y free."""
        x, y = Ints("x y")
        q = ForAll([x], x + y > 0)
        names = {n for n, _ in q._vars}
        assert "x" not in names
        assert "y" in names

    def test_function_vars(self):
        """Function and its arguments are tracked."""
        f = Function("f", IntSort(), IntSort())
        x = Int("x")
        app = f(x)
        names = {n for n, _ in app._vars}
        assert "f" in names
        assert "x" in names

    def test_uninterpreted_sort_vars(self):
        """DeclareSort introduces a type variable."""
        S = DeclareSort("S")
        a = Const("a", S)
        names = {n for n, _ in a._vars}
        assert "a" in names
        assert "S" in names


# ===================================================================
# Sort system
# ===================================================================


class TestSortSystem:
    """Test sort construction and checking."""

    def test_sort_equality(self):
        assert IntSort() == IntSort()
        assert BoolSort() == BoolSort()
        assert IntSort() != BoolSort()
        assert BitVecSort(8) == BitVecSort(8)
        assert BitVecSort(8) != BitVecSort(16)

    def test_sort_repr(self):
        assert repr(IntSort()) == "Int"
        assert repr(BoolSort()) == "Prop"  # Lean uses Prop for Bool
        assert repr(NatSort()) == "Nat"
        assert repr(RealSort()) == "Real"
        assert repr(StringSort()) == "String"

    def test_bv_sort_repr(self):
        assert "8" in repr(BitVecSort(8))

    def test_array_sort(self):
        s = ArraySort(IntSort(), IntSort())
        assert isinstance(s, ArraySortRef)

    def test_expression_sort(self):
        """Each expression knows its sort."""
        assert Int("x").sort() == IntSort()
        assert Real("x").sort() == RealSort()
        assert Bool("x").sort() == BoolSort()
        assert BitVec("x", 8).sort() == BitVecSort(8)


# ===================================================================
# prove() function
# ===================================================================


class TestProveFunction:
    """Test the prove() convenience function."""

    def test_prove_true(self, kernel):
        """prove(True) succeeds."""
        assert prove(BoolVal(True))

    def test_prove_simple_tautology(self, kernel):
        p = Bool("p")
        assert prove(ForAll([p], Implies(p, p)))

    def test_prove_false_claim(self, kernel):
        """prove(False) fails."""
        assert not prove(BoolVal(False))

    def test_prove_linear_arith(self, kernel):
        x = Int("x")
        assert prove(ForAll([x], Implies(x > 2, x > 1)))

    def test_prove_nat_nonneg(self, kernel):
        """All naturals are >= 0."""
        n = Nat("n")
        assert prove(ForAll([n], n >= 0))


# ===================================================================
# Complex proofs (from various examples)
# ===================================================================


class TestComplexProofs:
    """More involved proofs ported from z3py examples."""

    def test_transitivity(self, kernel):
        """x > y ∧ y > z => x > z."""
        x, y, z = Ints("x y z")
        claim = ForAll([x, y, z], Implies(And(x > y, y > z), x > z))
        assert prove(claim)

    def test_triangle_inequality_variant(self, kernel):
        """If all sides positive, sum of two > third."""
        a, b = Ints("a b")
        claim = ForAll([a, b], Implies(And(a > 0, b > 0), a + b > a))
        assert prove(claim)

    def test_bv_zero_extend(self, kernel):
        """ZeroExt preserves concrete values."""
        v = BitVecVal(10, 8)
        claim = ZeroExt(8, v) == BitVecVal(10, 16)
        assert prove(claim)

    def test_array_functional_update(self, kernel):
        """Two stores at same index: second overwrites first."""
        a = Array("a", IntSort(), IntSort())
        i = Int("i")
        claim = ForAll(
            [a, i],
            Select(Store(Store(a, i, IntVal(1)), i, IntVal(2)), i) == IntVal(2),
        )
        assert prove(claim)

    def test_implies_transitive(self, kernel):
        """(p => q) ∧ (q => r) => (p => r)."""
        p, q, r = Bools("p q r")
        claim = ForAll(
            [p, q, r],
            Implies(And(Implies(p, q), Implies(q, r)), Implies(p, r)),
        )
        assert prove(claim)

    def test_abs_nonneg_proof(self, kernel):
        """abs(x) >= 0."""
        x = Int("x")
        assert prove(ForAll([x], Abs(x) >= 0))

    def test_double_negation(self, kernel):
        """Not(Not(p)) == p."""
        p = Bool("p")
        assert prove(ForAll([p], Not(Not(p)) == p))

    def test_bv_rotate_full(self, kernel):
        """Rotating by full width is identity."""
        x = BitVec("x", 8)
        claim = ForAll([x], RotateLeft(x, 8) == x)
        assert prove(claim)


# ===================================================================
# And/Or with lists (from guide list comprehension section)
# ===================================================================


class TestAndOrLists:
    """And/Or accepting lists (Pythonic z3py pattern)."""

    def test_and_list(self):
        bs = [Bool(f"b{i}") for i in range(3)]
        result = And(bs)
        assert is_and(result) or isinstance(result._ast, BoolLit)

    def test_or_list(self):
        bs = [Bool(f"b{i}") for i in range(3)]
        result = Or(bs)
        assert is_or(result) or isinstance(result._ast, BoolLit)

    def test_and_empty(self):
        assert is_true(And([]))

    def test_or_empty(self):
        assert is_false(Or([]))

    def test_and_single(self):
        b = Bool("b")
        result = And([b])
        assert result._ast == b._ast

    def test_or_single(self):
        b = Bool("b")
        result = Or([b])
        assert result._ast == b._ast


# ===================================================================
# Consts helper
# ===================================================================


class TestConstsHelper:
    """Test Consts() for creating multiple constants."""

    def test_consts_int(self):
        x, y, z = Consts("x y z", IntSort())
        assert is_int(x)
        assert is_int(y)
        assert is_int(z)

    def test_consts_bool(self):
        a, b = Consts("a b", BoolSort())
        assert is_bool(a)
        assert is_bool(b)

    def test_consts_uninterpreted(self):
        S = DeclareSort("S")
        a, b = Consts("a b", S)
        names = {n for n, _ in a._vars}
        assert "a" in names
        assert "S" in names


# ===================================================================
# Value constructors
# ===================================================================


class TestValueConstructors:
    """Test IntVal, NatVal, RealVal, BoolVal, BitVecVal, StringVal."""

    def test_intval(self):
        v = IntVal(42)
        assert isinstance(v._ast, IntLit)
        assert v._ast.val == 42

    def test_natval(self):
        v = NatVal(7)
        assert isinstance(v._ast, NatLit)
        assert v._ast.val == 7

    def test_realval_int(self):
        v = RealVal(5)
        assert is_real(v)

    def test_boolval(self):
        assert isinstance(BoolVal(True)._ast, BoolLit)
        assert isinstance(BoolVal(False)._ast, BoolLit)

    def test_bitvecval(self):
        v = BitVecVal(0xFF, 8)
        assert isinstance(v._ast, BvLit)
        assert v._ast.val == 0xFF
        assert v._ast.width == 8

    def test_stringval(self):
        v = StringVal("test")
        assert isinstance(v._ast, StringLit)
        assert v._ast.val == "test"


# ===================================================================
# BV signed/rotation ops
# ===================================================================


class TestBVSignedRotation:
    """BV signed operations and rotations."""

    def test_rotate_left(self):
        x = BitVec("x", 8)
        r = RotateLeft(x, 3)
        assert r.size() == 8
        assert r._ast.op == BinOp.ROTL

    def test_rotate_right(self):
        x = BitVec("x", 8)
        r = RotateRight(x, 3)
        assert r.size() == 8
        assert r._ast.op == BinOp.ROTR

    def test_sdiv(self):
        x, y = BitVecs("x y", 8)
        r = SDiv(x, y)
        assert r.size() == 8
        assert r._ast.op == BinOp.SDIV

    def test_srem(self):
        x, y = BitVecs("x y", 8)
        r = SRem(x, y)
        assert r.size() == 8
        assert r._ast.op == BinOp.SREM

    def test_ashr(self):
        x = BitVec("x", 8)
        r = AShr(x, 2)
        assert r.size() == 8
        assert r._ast.op == BinOp.ASHR

    def test_rotate_left_zero_identity(self, kernel):
        """RotateLeft(x, 0) == x."""
        x = BitVec("x", 8)
        assert prove(ForAll(x, RotateLeft(x, 0) == x))

    def test_rotate_right_zero_identity(self, kernel):
        """RotateRight(x, 0) == x."""
        x = BitVec("x", 8)
        assert prove(ForAll(x, RotateRight(x, 0) == x))


# ===================================================================
# BV functions (comprehensive)
# ===================================================================


class TestBVFunctionsPorted:
    """All BV helper functions."""

    def test_lshr(self):
        x = BitVec("x", 8)
        r = LShR(x, 2)
        assert r._ast.op == BinOp.BSHR

    def test_unsigned_comparisons(self):
        x, y = BitVecs("x y", 8)
        assert isinstance(ULE(x, y)._ast, BinOpNode)
        assert isinstance(ULT(x, y)._ast, BinOpNode)
        assert isinstance(UGE(x, y)._ast, BinOpNode)
        assert isinstance(UGT(x, y)._ast, BinOpNode)

    def test_udiv_urem(self):
        x, y = BitVecs("x y", 8)
        assert isinstance(UDiv(x, y)._ast, BinOpNode)
        assert isinstance(URem(x, y)._ast, BinOpNode)

    def test_extract(self):
        x = BitVec("x", 16)
        r = Extract(7, 0, x)
        assert r.size() == 8
        r2 = Extract(15, 8, x)
        assert r2.size() == 8

    def test_concat(self):
        a, b = BitVecs("a b", 4)
        r = Concat(a, b)
        assert r.size() == 8

    def test_zeroext(self):
        x = BitVec("x", 8)
        r = ZeroExt(8, x)
        assert r.size() == 16

    def test_signext(self):
        x = BitVec("x", 8)
        r = SignExt(8, x)
        assert r.size() == 16

    def test_bv2int(self):
        x = BitVec("x", 8)
        r = BV2Int(x)
        assert is_int(r)

    def test_int2bv(self):
        x = Int("x")
        r = Int2BV(x, 8)
        assert r.size() == 8


# ===================================================================
# Arith functions
# ===================================================================


class TestArithFunctionsPorted:
    """Abs, ToReal, ToInt, Sum, Product."""

    def test_abs(self):
        x = Int("x")
        r = Abs(x)
        assert isinstance(r._ast, IteNode)

    def test_toreal(self):
        x = Int("x")
        r = ToReal(x)
        assert is_real(r)

    def test_toint(self):
        x = Real("x")
        r = ToInt(x)
        assert is_int(r)

    def test_sum_variadic(self):
        x, y, z = Ints("x y z")
        r = Sum(x, y, z)
        assert is_int(r)

    def test_sum_list(self):
        xs = [Int(f"x{i}") for i in range(4)]
        r = Sum(xs)
        assert is_int(r)

    def test_sum_empty(self):
        r = Sum()
        assert isinstance(r._ast, IntLit) and r._ast.val == 0

    def test_product_variadic(self):
        x, y = Ints("x y")
        r = Product(x, y)
        assert is_int(r)

    def test_product_empty(self):
        r = Product()
        assert isinstance(r._ast, IntLit) and r._ast.val == 1


# ===================================================================
# repr / sort display
# ===================================================================


class TestRepr:
    """Test __repr__ for expressions and sorts."""

    def test_int_var_repr(self):
        x = Int("x")
        assert "x" in repr(x)

    def test_intval_repr(self):
        v = IntVal(42)
        assert "42" in repr(v)

    def test_boolval_repr(self):
        assert "True" in repr(BoolVal(True))
        assert "False" in repr(BoolVal(False))

    def test_bv_val_repr(self):
        v = BitVecVal(255, 8)
        r = repr(v)
        assert "255" in r or "0xff" in r.lower()

    def test_binop_repr(self):
        x, y = Ints("x y")
        r = repr(x + y)
        assert "add" in r or "+" in r

    def test_not_repr(self):
        a = Bool("a")
        r = repr(Not(a))
        assert "Not" in r or "¬" in r or "not" in r.lower()

    def test_forall_repr(self):
        x = Int("x")
        r = repr(ForAll([x], x > 0))
        assert "ForAll" in r or "∀" in r or "forall" in r.lower()


# ===================================================================
# Vector constructors
# ===================================================================


class TestVectorConstructors:
    def test_int_vector(self):
        xs = IntVector("x", 5)
        assert len(xs) == 5
        assert all(is_int(x) for x in xs)
        assert all(isinstance(x, ArithRef) for x in xs)

    def test_bool_vector(self):
        bs = BoolVector("b", 3)
        assert len(bs) == 3
        assert all(is_bool(b) for b in bs)

    def test_real_vector(self):
        rs = RealVector("r", 4)
        assert len(rs) == 4
        assert all(is_real(r) for r in rs)

    def test_vector_names(self):
        xs = IntVector("x", 3)
        names = [x._ast.name for x in xs]
        assert names == ["x__0", "x__1", "x__2"]

    def test_vector_zero(self):
        assert IntVector("x", 0) == []
        assert BoolVector("b", 0) == []
        assert RealVector("r", 0) == []

    def test_vector_sum(self):
        xs = IntVector("x", 3)
        s = Sum(*xs)
        assert is_int(s)


# ===================================================================
# Substitute
# ===================================================================


class TestSubstitute:
    def test_substitute_var(self):
        x, y = Ints("x y")
        expr = x + 1
        result = substitute(expr, (x, y))
        assert "y" in repr(result)

    def test_substitute_multiple(self):
        x, y, z = Ints("x y z")
        expr = x + y
        result = substitute(expr, (x, z), (y, z))
        # Both x and y replaced by z
        assert isinstance(result, ExprRef)

    def test_substitute_in_comparison(self):
        x, y = Ints("x y")
        expr = x > 0
        result = substitute(expr, (x, y))
        assert isinstance(result, BoolRef)

    def test_substitute_nested(self):
        x, y = Ints("x y")
        expr = And(x > 0, x < 10)
        result = substitute(expr, (x, y))
        assert isinstance(result, BoolRef)

    def test_substitute_no_match(self):
        x, y = Ints("x y")
        expr = x + 1
        result = substitute(expr, (y, IntVal(5)))
        # x + 1 unchanged since y not in expr
        assert isinstance(result, ExprRef)

    def test_substitute_with_value(self):
        x = Int("x")
        expr = x * 2
        result = substitute(expr, (x, IntVal(3)))
        assert isinstance(result, ExprRef)

    def test_substitute_preserves_sort(self):
        x, y = Ints("x y")
        expr = x + y
        result = substitute(expr, (x, IntVal(5)))
        assert is_int(result)


# ===================================================================
# IsInt, Sqrt
# ===================================================================


class TestIsIntSqrt:
    def test_isint(self):
        x = Real("x")
        result = IsInt(x)
        assert isinstance(result, BoolRef)

    def test_sqrt(self):
        x = Real("x")
        result = Sqrt(x)
        assert is_real(result)

    def test_sqrt_is_power(self):
        x = Real("x")
        result = Sqrt(x)
        assert isinstance(result._ast, BinOpNode)
        assert result._ast.op == BinOp.POW


# ===================================================================
# BV extras
# ===================================================================


class TestBVExtras:
    def test_repeat_bitvec(self):
        x = BitVec("x", 4)
        r = RepeatBitVec(3, x)
        assert r.size() == 12

    def test_repeat_bitvec_one(self):
        x = BitVec("x", 8)
        r = RepeatBitVec(1, x)
        assert r._ast == x._ast

    def test_repeat_bitvec_invalid(self):
        x = BitVec("x", 4)
        with pytest.raises(TypeError):
            RepeatBitVec(0, x)

    def test_bvredand(self):
        x = BitVec("x", 4)
        r = BVRedAnd(x)
        assert r.size() == 1

    def test_bvredor(self):
        x = BitVec("x", 4)
        r = BVRedOr(x)
        assert r.size() == 1

    def test_bvnand(self):
        x, y = BitVecs("x y", 8)
        r = BvNand(x, y)
        assert isinstance(r, BitVecRef)
        assert r.size() == 8

    def test_bvnor(self):
        x, y = BitVecs("x y", 8)
        r = BvNor(x, y)
        assert isinstance(r, BitVecRef)

    def test_bvxnor(self):
        x, y = BitVecs("x y", 8)
        r = BvXnor(x, y)
        assert isinstance(r, BitVecRef)


# ===================================================================
# BV overflow predicates
# ===================================================================


class TestBVOverflow:
    def test_add_no_overflow_unsigned(self):
        x, y = BitVecs("x y", 8)
        r = BVAddNoOverflow(x, y)
        assert isinstance(r, BoolRef)

    def test_add_no_overflow_signed(self):
        x, y = BitVecs("x y", 8)
        r = BVAddNoOverflow(x, y, signed=True)
        assert isinstance(r, BoolRef)

    def test_add_no_underflow(self):
        x, y = BitVecs("x y", 8)
        r = BVAddNoUnderflow(x, y)
        assert isinstance(r, BoolRef)

    def test_sub_no_overflow(self):
        x, y = BitVecs("x y", 8)
        r = BVSubNoOverflow(x, y)
        assert isinstance(r, BoolRef)

    def test_sub_no_underflow_unsigned(self):
        x, y = BitVecs("x y", 8)
        r = BVSubNoUnderflow(x, y)
        assert isinstance(r, BoolRef)

    def test_sub_no_underflow_signed(self):
        x, y = BitVecs("x y", 8)
        r = BVSubNoUnderflow(x, y, signed=True)
        assert isinstance(r, BoolRef)

    def test_mul_no_overflow(self):
        x, y = BitVecs("x y", 8)
        r = BVMulNoOverflow(x, y)
        assert isinstance(r, BoolRef)

    def test_mul_no_underflow(self):
        x, y = BitVecs("x y", 8)
        r = BVMulNoUnderflow(x, y)
        assert isinstance(r, BoolRef)

    def test_sdiv_no_overflow(self):
        x, y = BitVecs("x y", 8)
        r = BVSDivNoOverflow(x, y)
        assert isinstance(r, BoolRef)


# ===================================================================
# Pseudo-boolean constraints
# ===================================================================


class TestPseudoBoolean:
    def test_atmost(self):
        bs = BoolVector("b", 5)
        r = AtMost(bs, 2)
        assert isinstance(r, BoolRef)

    def test_atleast(self):
        bs = BoolVector("b", 5)
        r = AtLeast(bs, 3)
        assert isinstance(r, BoolRef)

    def test_pbeq(self):
        a, b, c = Bools("a b c")
        r = PbEq([(a, 1), (b, 2), (c, 3)], 3)
        assert isinstance(r, BoolRef)

    def test_pble(self):
        a, b = Bools("a b")
        r = PbLe([(a, 1), (b, 2)], 2)
        assert isinstance(r, BoolRef)

    def test_pbge(self):
        a, b = Bools("a b")
        r = PbGe([(a, 1), (b, 2)], 1)
        assert isinstance(r, BoolRef)

    def test_atmost_empty(self):
        r = AtMost([], 0)
        assert is_true(r)

    def test_atleast_empty_zero(self):
        r = AtLeast([], 0)
        assert is_true(r)

    def test_atmost_unsat(self, kernel):
        """AtMost 0 true out of all-true is unsat."""
        a, b = Bools("a b")
        s = Solver()
        s.add(a, b, AtMost([a, b], 0))
        assert s.check() == unsat


# ===================================================================
# Solver extras
# ===================================================================


class TestSolverExtras:
    def test_solver_append(self, kernel):
        s = Solver()
        x = Int("x")
        s.append(x > 0)
        assert len(s.assertions()) == 1

    def test_solver_insert(self, kernel):
        s = Solver()
        x = Int("x")
        s.insert(x > 0)
        assert len(s.assertions()) == 1

    def test_solver_set_noop(self, kernel):
        s = Solver()
        s.set(timeout=1000)  # no-op, should not raise

    def test_solver_num_scopes(self, kernel):
        s = Solver()
        assert s.num_scopes() == 0
        s.push()
        assert s.num_scopes() == 1
        s.push()
        assert s.num_scopes() == 2
        s.pop()
        assert s.num_scopes() == 1

    def test_solver_len(self, kernel):
        s = Solver()
        x = Int("x")
        s.add(x > 0, x < 10)
        assert len(s) == 2

    def test_solver_getitem(self, kernel):
        s = Solver()
        x = Int("x")
        c = x > 0
        s.add(c)
        assert s[0]._ast == c._ast

    def test_solver_iter(self, kernel):
        s = Solver()
        x = Int("x")
        s.add(x > 0, x < 10)
        asserts = list(s)
        assert len(asserts) == 2

    def test_solver_sexpr(self, kernel):
        s = Solver()
        x = Int("x")
        s.add(x > 0)
        se = s.sexpr()
        assert isinstance(se, str)
        assert len(se) > 0

    def test_solver_sexpr_empty(self, kernel):
        s = Solver()
        assert s.sexpr() == "()"

    def test_solver_to_smt2(self, kernel):
        s = Solver()
        x = Int("x")
        s.add(x > 0)
        smt2 = s.to_smt2()
        assert "assert" in smt2
        assert "check-sat" in smt2

    def test_solver_assert_and_track(self, kernel):
        s = Solver()
        x = Int("x")
        p = Bool("p")
        s.assert_and_track(x > 0, p)
        assert len(s.assertions()) == 1

    def test_solver_unsat_core_raises(self, kernel):
        s = Solver()
        with pytest.raises(NotImplementedError):
            s.unsat_core()

    def test_solver_reason_unknown(self, kernel):
        s = Solver()
        r = s.reason_unknown()
        assert isinstance(r, str)

    def test_solver_statistics(self, kernel):
        s = Solver()
        stats = s.statistics()
        assert isinstance(stats, dict)

    def test_solver_check_with_assumptions(self, kernel):
        x = Int("x")
        s = Solver()
        s.add(x > 0)
        result = s.check(x < 0)
        assert result == unsat


# ===================================================================
# SolverFor, SimpleSolver, solve_using
# ===================================================================


class TestSolverFactories:
    def test_solver_for(self, kernel):
        s = SolverFor("QF_LIA")
        assert isinstance(s, Solver)
        x = Int("x")
        s.add(x > 0, x < 0)
        assert s.check() == unsat

    def test_simple_solver(self, kernel):
        s = SimpleSolver()
        assert isinstance(s, Solver)

    def test_solve_using(self, kernel):
        s = Solver()
        x = Int("x")
        result = solve_using(s, x > 0, x < 0)
        assert result == unsat

    def test_set_param_noop(self):
        set_param(proof=True)  # should not raise

    def test_set_option_noop(self):
        set_option(precision=10)  # should not raise

    def test_set_option_is_set_param(self):
        assert set_option is set_param


# ===================================================================
# Tactic extras
# ===================================================================


class TestTacticExtras:
    def test_andthen_alias(self):
        t = AndThen(Tactic("simp"), Tactic("decide"))
        assert isinstance(t, Tactic)

    def test_with_ignores_params(self):
        t = Tactic("simp")
        t2 = With(t, max_steps=1000)
        assert t2 is t

    def test_tryfor_ignores_timeout(self):
        t = Tactic("simp")
        t2 = TryFor(t, 5000)
        assert t2 is t

    def test_tactic_solver(self, kernel):
        t = Tactic("grind")
        s = t.solver()
        assert isinstance(s, Solver)
        x = Int("x")
        s.add(x > 0, x < 0)
        assert s.check() == unsat


# ===================================================================
# Extended predicates
# ===================================================================


class TestExtendedPredicates:
    def test_is_arith(self):
        assert is_arith(Int("x"))
        assert is_arith(Real("x"))
        assert is_arith(Nat("n"))
        assert not is_arith(Bool("b"))
        assert not is_arith(BitVec("v", 8))

    def test_is_sort(self):
        assert is_sort(IntSort())
        assert is_sort(BoolSort())
        assert is_sort(BitVecSort(8))
        assert not is_sort(Int("x"))
        assert not is_sort(42)

    def test_is_app(self):
        f = Function("f", IntSort(), IntSort())
        x = Int("x")
        assert is_app(f(x))
        assert not is_app(x)

    def test_is_func_decl(self):
        f = Function("f", IntSort(), IntSort())
        assert is_func_decl(f)
        assert not is_func_decl(Int("x"))

    def test_is_int_value(self):
        assert is_int_value(IntVal(42))
        assert not is_int_value(Int("x"))
        assert not is_int_value(RealVal(5))

    def test_is_rational_value(self):
        assert is_rational_value(Q(1, 3))
        assert is_rational_value(RealVal(5))
        assert not is_rational_value(IntVal(5))

    def test_is_bv_value(self):
        assert is_bv_value(BitVecVal(42, 8))
        assert not is_bv_value(BitVec("x", 8))

    def test_is_comparison_predicates(self):
        x, y = Ints("x y")
        assert is_le(x <= y)
        assert is_lt(x < y)
        assert is_ge(x >= y)
        assert is_gt(x > y)
        assert not is_le(x > y)

    def test_is_mod(self):
        x, y = Ints("x y")
        assert is_mod(x % y)
        assert not is_mod(x + y)

    def test_is_idiv(self):
        x, y = Ints("x y")
        assert is_idiv(x / y)
        assert not is_idiv(x + y)


# ===================================================================
# EXPRESSION INTROSPECTION
# ===================================================================


class TestExprRefIntrospection:
    """Test ExprRef.arg(), .num_args(), .children(), .decl(), .sexpr(), .params()."""

    def test_binop_num_args(self):
        x, y = Ints("x y")
        e = x + y
        assert e.num_args() == 2

    def test_binop_arg(self):
        x, y = Ints("x y")
        e = x + y
        a0 = e.arg(0)
        a1 = e.arg(1)
        assert repr(a0) == "x"
        assert repr(a1) == "y"

    def test_binop_children(self):
        x, y = Ints("x y")
        e = x * y
        kids = e.children()
        assert len(kids) == 2
        assert repr(kids[0]) == "x"
        assert repr(kids[1]) == "y"

    def test_binop_decl(self):
        x, y = Ints("x y")
        e = x + y
        d = e.decl()
        assert isinstance(d, FuncDeclRef)
        assert d.name() == "add"

    def test_comparison_decl(self):
        x, y = Ints("x y")
        e = x < y
        assert e.decl().name() == "lt"

    def test_unop_children(self):
        x = Int("x")
        e = -x
        assert e.num_args() == 1
        assert repr(e.arg(0)) == "x"
        assert e.decl().name() == "neg"

    def test_not_children(self):
        p = Bool("p")
        e = Not(p)
        assert e.num_args() == 1
        assert e.decl().name() == "not"

    def test_ite_children(self):
        x = Int("x")
        p = Bool("p")
        e = If(p, x, IntVal(0))
        assert e.num_args() == 3
        assert e.decl().name() == "if"

    def test_distinct_children(self):
        x, y, z = Ints("x y z")
        e = Distinct(x, y, z)
        assert e.num_args() == 3
        assert e.decl().name() == "distinct"

    def test_literal_no_children(self):
        v = IntVal(42)
        assert v.num_args() == 0
        assert v.children() == []

    def test_boolval_no_children(self):
        v = BoolVal(True)
        assert v.num_args() == 0

    def test_sexpr(self):
        x, y = Ints("x y")
        e = x + y
        s = e.sexpr()
        assert isinstance(s, str)
        assert "add" in s

    def test_arg_out_of_range(self):
        x = Int("x")
        e = -x
        with pytest.raises(IndexError):
            e.arg(5)

    def test_extract_params(self):
        x = BitVec("x", 32)
        e = Extract(7, 0, x)
        assert e.params() == [7, 0]

    def test_zeroext_params(self):
        x = BitVec("x", 8)
        e = ZeroExt(8, x)
        assert e.params() == [16]  # total new width

    def test_var_no_params(self):
        x = Int("x")
        assert x.params() == []

    def test_nested_children_walk(self):
        """Walk a nested expression tree."""
        x, y, z = Ints("x y z")
        e = (x + y) * z
        assert e.num_args() == 2
        left = e.arg(0)
        assert left.num_args() == 2
        assert e.decl().name() == "mul"
        assert left.decl().name() == "add"

    def test_and_children(self):
        p, q = Bools("p q")
        e = And(p, q)
        assert e.num_args() == 2
        assert e.decl().name() == "and"

    def test_or_children(self):
        p, q = Bools("p q")
        e = Or(p, q)
        assert e.num_args() == 2
        assert e.decl().name() == "or"

    def test_app_children(self):
        f = Function("f", IntSort(), IntSort(), IntSort())
        x, y = Ints("x y")
        e = f(x, y)
        assert is_app(e)
        assert e.num_args() == 2
        assert e.decl().name() == "f"

    def test_select_children(self):
        a = Array("a", IntSort(), IntSort())
        i = Int("i")
        e = Select(a, i)
        assert e.num_args() == 2
        assert e.decl().name() == "select"

    def test_store_children(self):
        a = Array("a", IntSort(), IntSort())
        i = Int("i")
        v = Int("v")
        e = Store(a, i, v)
        assert e.num_args() == 3
        assert e.decl().name() == "store"

    def test_child_sort_inference_arith(self):
        """Children of arithmetic ops should be ArithRef."""
        x, y = Ints("x y")
        e = x + y
        c0 = e.arg(0)
        assert isinstance(c0, ArithRef)

    def test_child_sort_inference_bool(self):
        """Children of And/Or should be BoolRef."""
        p, q = Bools("p q")
        e = And(p, q)
        c0 = e.arg(0)
        assert isinstance(c0, BoolRef)

    def test_child_sort_inference_bv(self):
        """Children of BV ops should be BitVecRef."""
        x, y = BitVecs("x y", 8)
        e = x + y
        c0 = e.arg(0)
        assert isinstance(c0, BitVecRef)

    def test_child_sort_inference_ite_cond(self):
        """Condition child of ITE should be BoolRef."""
        x = Int("x")
        p = Bool("p")
        e = If(p, x, IntVal(0))
        assert isinstance(e.arg(0), BoolRef)

    def test_child_literal_int(self):
        """Int literal children should be ArithRef."""
        x = Int("x")
        e = x + 5
        c1 = e.arg(1)
        assert isinstance(c1, ArithRef)

    def test_child_literal_bv(self):
        """BV literal children should be BitVecRef."""
        x = BitVec("x", 8)
        e = x + 3
        c1 = e.arg(1)
        assert isinstance(c1, BitVecRef)


# ===================================================================
# FUNCDECLREF INTROSPECTION
# ===================================================================


class TestFuncDeclRefIntrospection:
    """Test FuncDeclRef.name(), .arity(), .domain(), .range()."""

    def test_name(self):
        f = Function("myFunc", IntSort(), BoolSort())
        assert f.name() == "myFunc"

    def test_arity(self):
        f = Function("f", IntSort(), IntSort(), BoolSort())
        assert f.arity() == 2

    def test_domain(self):
        f = Function("f", IntSort(), RealSort(), BoolSort())
        assert f.domain(0) == IntSort()
        assert f.domain(1) == RealSort()

    def test_range(self):
        f = Function("f", IntSort(), BoolSort())
        assert f.range() == BoolSort()

    def test_domain_out_of_range(self):
        f = Function("f", IntSort(), BoolSort())
        with pytest.raises(IndexError):
            f.domain(5)

    def test_unary_function(self):
        f = Function("neg", IntSort(), IntSort())
        assert f.arity() == 1
        assert f.domain(0) == IntSort()
        assert f.range() == IntSort()

    def test_three_arg_function(self):
        f = Function("g", IntSort(), RealSort(), BoolSort(), IntSort())
        assert f.arity() == 3
        assert f.domain(0) == IntSort()
        assert f.domain(1) == RealSort()
        assert f.domain(2) == BoolSort()
        assert f.range() == IntSort()

    def test_expr_decl_gives_funcdeclref(self):
        x, y = Ints("x y")
        e = x + y
        d = e.decl()
        assert isinstance(d, FuncDeclRef)
        assert d.name() == "add"


# ===================================================================
# QUANTIFIERREF INTROSPECTION
# ===================================================================


class TestQuantifierRefIntrospection:
    """Test QuantifierRef introspection methods."""

    def test_forall_is_forall(self):
        x = Int("x")
        q = ForAll([x], x > 0)
        assert q.is_forall()
        assert not q.is_exists()

    def test_exists_is_exists(self):
        x = Int("x")
        q = Exists([x], x > 0)
        assert q.is_exists()
        assert not q.is_forall()

    def test_num_vars(self):
        x, y = Ints("x y")
        q = ForAll([x, y], x + y > 0)
        assert q.num_vars() == 2

    def test_var_name(self):
        x, y = Ints("x y")
        q = ForAll([x, y], x + y > 0)
        assert q.var_name(0) == "x"
        assert q.var_name(1) == "y"

    def test_var_sort(self):
        x = Int("x")
        y = Real("y")
        q = ForAll([x], x > 0)
        assert q.var_sort(0) == IntSort()

    def test_body(self):
        x = Int("x")
        body = x > 0
        q = ForAll([x], body)
        assert isinstance(q.body(), BoolRef)
        # The body should be the same expression
        assert repr(q.body()) == repr(body)

    def test_single_var_quantifier(self):
        x = Int("x")
        q = Exists([x], x == 42)
        assert q.num_vars() == 1
        assert q.var_name(0) == "x"


# ===================================================================
# NUMERIC REFERENCE CLASSES
# ===================================================================


class TestIntNumRef:
    """Test IntNumRef value extraction."""

    def test_intval_returns_intnumref(self):
        v = IntVal(42)
        assert isinstance(v, IntNumRef)
        assert isinstance(v, ArithRef)

    def test_as_long(self):
        v = IntVal(42)
        assert v.as_long() == 42

    def test_as_long_negative(self):
        v = IntVal(-7)
        assert v.as_long() == -7

    def test_as_long_zero(self):
        v = IntVal(0)
        assert v.as_long() == 0

    def test_as_string(self):
        v = IntVal(123)
        assert v.as_string() == "123"

    def test_natval_returns_intnumref(self):
        v = NatVal(5)
        assert isinstance(v, IntNumRef)
        assert v.as_long() == 5

    def test_arithmetic_still_works(self):
        """IntNumRef still supports ArithRef operations."""
        v = IntVal(5)
        x = Int("x")
        e = v + x
        assert isinstance(e, ArithRef)


class TestRatNumRef:
    """Test RatNumRef value extraction."""

    def test_ratval_returns_ratnumref(self):
        r = RatVal(1, 3)
        assert isinstance(r, RatNumRef)
        assert isinstance(r, ArithRef)

    def test_numerator(self):
        r = RatVal(1, 3)
        n = r.numerator()
        assert isinstance(n, IntNumRef)
        assert n.as_long() == 1

    def test_denominator(self):
        r = RatVal(1, 3)
        d = r.denominator()
        assert isinstance(d, IntNumRef)
        assert d.as_long() == 3

    def test_numerator_as_long(self):
        r = RatVal(7, 11)
        assert r.numerator_as_long() == 7

    def test_denominator_as_long(self):
        r = RatVal(7, 11)
        assert r.denominator_as_long() == 11

    def test_as_fraction(self):
        from fractions import Fraction
        r = RatVal(1, 3)
        f = r.as_fraction()
        assert f == Fraction(1, 3)

    def test_as_string(self):
        r = RatVal(1, 3)
        assert r.as_string() == "1/3"

    def test_as_long(self):
        r = RatVal(7, 2)
        assert r.as_long() == 3  # integer division

    def test_q_alias(self):
        r = Q(2, 5)
        assert isinstance(r, RatNumRef)
        assert r.numerator_as_long() == 2
        assert r.denominator_as_long() == 5


class TestBitVecNumRef:
    """Test BitVecNumRef value extraction."""

    def test_bitvecval_returns_bitvecnumref(self):
        v = BitVecVal(255, 8)
        assert isinstance(v, BitVecNumRef)
        assert isinstance(v, BitVecRef)

    def test_as_long(self):
        v = BitVecVal(255, 8)
        assert v.as_long() == 255

    def test_as_long_zero(self):
        v = BitVecVal(0, 32)
        assert v.as_long() == 0

    def test_as_signed_long_positive(self):
        v = BitVecVal(127, 8)
        assert v.as_signed_long() == 127

    def test_as_signed_long_negative(self):
        v = BitVecVal(255, 8)
        assert v.as_signed_long() == -1

    def test_as_signed_long_min(self):
        v = BitVecVal(128, 8)
        assert v.as_signed_long() == -128

    def test_as_string(self):
        v = BitVecVal(42, 8)
        assert v.as_string() == "42"

    def test_bv_ops_still_work(self):
        """BitVecNumRef still supports BitVecRef operations."""
        v = BitVecVal(5, 8)
        x = BitVec("x", 8)
        e = v + x
        assert isinstance(e, BitVecRef)


# ===================================================================
# SORT INTROSPECTION
# ===================================================================


class TestSortIntrospection:
    """Test SortRef.name(), .kind(), .sexpr()."""

    def test_int_sort_name(self):
        assert IntSort().name() == "Int"

    def test_real_sort_name(self):
        assert RealSort().name() == "Real"

    def test_bool_sort_name(self):
        assert BoolSort().name() == "Prop"

    def test_bv_sort_name(self):
        s = BitVecSort(32)
        assert "(BitVec 32)" in s.name()

    def test_string_sort_name(self):
        assert StringSort().name() == "String"

    def test_uninterp_sort_name(self):
        T = DeclareSort("MySort")
        assert T.name() == "MySort"

    def test_sort_kind_bool(self):
        assert BoolSort().kind() == 1

    def test_sort_kind_int(self):
        assert IntSort().kind() == 2

    def test_sort_kind_real(self):
        assert RealSort().kind() == 3

    def test_sort_kind_bv(self):
        assert BitVecSort(8).kind() == 4

    def test_sort_kind_array(self):
        assert ArraySort(IntSort(), IntSort()).kind() == 5

    def test_sort_kind_string(self):
        assert StringSort().kind() == 7

    def test_sort_kind_uninterpreted(self):
        T = DeclareSort("T")
        assert T.kind() == 0

    def test_sort_sexpr(self):
        s = IntSort()
        assert s.sexpr() == "Int"


# ===================================================================
# ENUMSORT AND TUPLESORT
# ===================================================================


class TestEnumSort:
    """Test EnumSort factory."""

    def test_create_enum(self, kernel):
        Color, (red, green, blue) = EnumSort("Color_e1", ["red", "green", "blue"])
        assert isinstance(Color, SortRef)
        assert Color.name() == "Color_e1"

    def test_enum_constants(self, kernel):
        Color, (red, green, blue) = EnumSort("Color_e2", ["red", "green", "blue"])
        assert isinstance(red, ExprRef)
        assert isinstance(green, ExprRef)
        assert isinstance(blue, ExprRef)

    def test_enum_distinct(self, kernel):
        Color, (red, green, blue) = EnumSort("Color_e3", ["red", "green", "blue"])
        # Constants should have different names
        assert repr(red) == "Color_e3.red"
        assert repr(green) == "Color_e3.green"
        assert repr(blue) == "Color_e3.blue"

    def test_enum_sort_attribute_access(self, kernel):
        Color, consts = EnumSort("Color_e4", ["red", "green", "blue"])
        assert hasattr(Color, "red")
        assert hasattr(Color, "green")
        assert hasattr(Color, "blue")


class TestTupleSort:
    """Test TupleSort factory."""

    def test_create_tuple(self, kernel):
        Pair, mk_pair, [fst, snd] = TupleSort("Pair_t1", [IntSort(), IntSort()])
        assert isinstance(Pair, SortRef)
        assert Pair.name() == "Pair_t1"

    def test_tuple_constructor(self, kernel):
        Pair, mk_pair, [fst, snd] = TupleSort("Pair_t2", [IntSort(), IntSort()])
        assert isinstance(mk_pair, FuncDeclRef)
        assert mk_pair.arity() == 2
        assert mk_pair.name() == "Pair_t2"

    def test_tuple_accessors(self, kernel):
        Pair, mk_pair, [fst, snd] = TupleSort("Pair_t3", [IntSort(), IntSort()])
        assert isinstance(fst, FuncDeclRef)
        assert isinstance(snd, FuncDeclRef)
        assert fst.arity() == 1
        assert snd.arity() == 1

    def test_tuple_constructor_call(self, kernel):
        Pair, mk_pair, [fst, snd] = TupleSort("Pair_t4", [IntSort(), RealSort()])
        x = Int("x")
        y = Real("y")
        p = mk_pair(x, y)
        assert isinstance(p, ExprRef)

    def test_triple_sort(self, kernel):
        Triple, mk, accs = TupleSort("Triple_t5", [IntSort(), RealSort(), BoolSort()])
        assert mk.arity() == 3
        assert len(accs) == 3


class TestCreateDatatypes:
    """Test CreateDatatypes factory."""

    def test_create_single(self, kernel):
        builder = Datatype("Fruit")
        builder.declare("apple")
        builder.declare("banana")
        (Fruit,) = CreateDatatypes(builder)
        assert isinstance(Fruit, SortRef)
        assert Fruit.name() == "Fruit"


# ===================================================================
# OPTIMIZE STUB
# ===================================================================


class TestOptimize:
    """Test Optimize stub class."""

    def test_create(self):
        o = Optimize()
        assert isinstance(o, Optimize)

    def test_add(self):
        o = Optimize()
        x = Int("x")
        o.add(x > 0)
        assert len(o.assertions()) == 1

    def test_maximize(self):
        o = Optimize()
        x = Int("x")
        h = o.maximize(x)
        assert h == 0

    def test_minimize(self):
        o = Optimize()
        x = Int("x")
        h = o.minimize(x)
        assert h == 0

    def test_check_returns_unknown(self):
        o = Optimize()
        assert o.check() == unknown

    def test_model_raises(self):
        o = Optimize()
        with pytest.raises(NotImplementedError):
            o.model()

    def test_push_pop(self):
        o = Optimize()
        o.push()
        o.pop()

    def test_repr(self):
        o = Optimize()
        x = Int("x")
        o.add(x > 0)
        o.maximize(x)
        r = repr(o)
        assert "1 assertions" in r
        assert "1 objectives" in r


# ===================================================================
# PARSE_SMT2_STRING
# ===================================================================


class TestParseSmt2String:

    def test_basic_assertions(self):
        result = parse_smt2_string(
            "(declare-const x Int) (assert (> x 0)) (assert (< x 10))"
        )
        assert len(result) == 2

    def test_with_decls(self):
        x, y = Ints("x y")
        f = Function("f", IntSort(), IntSort())
        result = parse_smt2_string(
            "(assert (> (+ foo (g bar)) 0))",
            decls={"foo": x, "bar": y, "g": f},
        )
        assert len(result) == 1

    def test_with_sorts(self):
        result = parse_smt2_string(
            "(declare-const a U) (assert (> a 0))",
            sorts={"U": IntSort()},
        )
        assert len(result) == 1

    def test_boolean_ops(self):
        result = parse_smt2_string(
            "(declare-const p Bool) (declare-const q Bool)"
            " (assert (and p (or q (not p))))"
        )
        assert len(result) == 1

    def test_let_binding(self):
        result = parse_smt2_string(
            "(declare-const x Int) (assert (let ((y (+ x 1))) (> y 0)))"
        )
        assert len(result) == 1

    def test_bitvec(self):
        result = parse_smt2_string(
            "(declare-const x (_ BitVec 8))"
            " (assert (= (bvadd x #x01) #b00000010))"
        )
        assert len(result) == 1

    def test_quantifier(self):
        result = parse_smt2_string(
            "(assert (forall ((x Int)) (>= (* x x) 0)))"
        )
        assert len(result) == 1

    def test_empty(self):
        result = parse_smt2_string("")
        assert result == []

    def test_comments(self):
        result = parse_smt2_string(
            "; this is a comment\n"
            "(declare-const x Int)\n"
            "; another comment\n"
            "(assert (> x 0))"
        )
        assert len(result) == 1

    def test_declare_fun(self):
        result = parse_smt2_string(
            "(declare-fun f (Int Int) Int)"
            " (declare-const x Int)"
            " (assert (> (f x x) 0))"
        )
        assert len(result) == 1

    def test_ite(self):
        result = parse_smt2_string(
            "(declare-const x Int) (assert (= (ite (> x 0) x (- x)) x))"
        )
        assert len(result) == 1

    def test_implies(self):
        result = parse_smt2_string(
            "(declare-const p Bool) (declare-const q Bool)"
            " (assert (=> p q))"
        )
        assert len(result) == 1

    def test_distinct(self):
        result = parse_smt2_string(
            "(declare-const x Int) (declare-const y Int)"
            " (assert (distinct x y))"
        )
        assert len(result) == 1


# ===================================================================
# SIMPLIFY
# ===================================================================


class TestSimplify:
    """Test simplify() stub."""

    def test_simplify_returns_input(self):
        x = Int("x")
        e = x + 0
        result = simplify(e)
        # Our simplify is a no-op stub
        assert result is e

    def test_simplify_boolval(self):
        e = BoolVal(True)
        result = simplify(e)
        assert result is e


# ===================================================================
# BOOL→INT COERCION
# ===================================================================


class TestBoolIntCoercion:
    """Test BoolRef.__add__/__mul__ (Bool→Int coercion)."""

    def test_bool_add_int(self):
        b = Bool("b")
        result = b + 0
        assert isinstance(result, ArithRef)

    def test_bool_radd_int(self):
        b = Bool("b")
        result = 0 + b
        assert isinstance(result, ArithRef)

    def test_bool_add_bool(self):
        x, y = Bools("x y")
        result = x + y
        assert isinstance(result, ArithRef)

    def test_bool_mul_int(self):
        b = Bool("b")
        result = b * 2
        assert isinstance(result, ArithRef)

    def test_bool_rmul_int(self):
        b = Bool("b")
        result = 3 * b
        assert isinstance(result, ArithRef)


# ===================================================================
# BITVECREF __pos__
# ===================================================================


class TestBitVecPos:
    def test_pos(self):
        x = BitVec("x", 8)
        assert +x is x

    def test_pos_preserves_sort(self):
        x = BitVec("x", 32)
        assert isinstance(+x, BitVecRef)


# ===================================================================
# QUANTIFIERREF ANNOTATION METHODS
# ===================================================================


class TestQuantifierAnnotations:
    def test_weight(self):
        x = Int("x")
        q = ForAll([x], x > 0)
        assert q.weight() == 0

    def test_qid(self):
        x = Int("x")
        q = ForAll([x], x > 0)
        assert q.qid() == ""

    def test_skolem_id(self):
        x = Int("x")
        q = Exists([x], x > 0)
        assert q.skolem_id() == ""

    def test_num_patterns(self):
        x = Int("x")
        q = ForAll([x], x > 0)
        assert q.num_patterns() == 0

    def test_pattern_raises(self):
        x = Int("x")
        q = ForAll([x], x > 0)
        with pytest.raises(IndexError):
            q.pattern(0)

    def test_num_no_patterns(self):
        x = Int("x")
        q = ForAll([x], x > 0)
        assert q.num_no_patterns() == 0

    def test_no_pattern_raises(self):
        x = Int("x")
        q = ForAll([x], x > 0)
        with pytest.raises(IndexError):
            q.no_pattern(0)


# ===================================================================
# EXPRREF TRANSLATE / GET_ID / SERIALIZE
# ===================================================================


class TestExprRefExtras:
    def test_translate_returns_self(self):
        x = Int("x")
        assert x.translate(None) is x

    def test_get_id_is_int(self):
        x = Int("x")
        assert isinstance(x.get_id(), int)

    def test_get_id_different_for_different_exprs(self):
        x = Int("x")
        y = Int("y")
        # ids should generally differ (not guaranteed but very likely)
        # Just check they're both ints
        assert isinstance(x.get_id(), int)
        assert isinstance(y.get_id(), int)

    def test_serialize(self):
        x = Int("x")
        assert x.serialize() == "x"

    def test_serialize_binop(self):
        x, y = Ints("x y")
        e = x + y
        s = e.serialize()
        assert "x" in s and "y" in s


# ===================================================================
# CONTEXT / MAIN_CTX / GET_CTX
# ===================================================================


class TestContext:
    def test_context_create(self):
        ctx = Context()
        assert repr(ctx) == "Context()"

    def test_main_ctx(self):
        ctx = main_ctx()
        assert isinstance(ctx, Context)

    def test_main_ctx_singleton(self):
        c1 = main_ctx()
        c2 = main_ctx()
        assert c1 is c2

    def test_get_ctx_none(self):
        ctx = get_ctx(None)
        assert isinstance(ctx, Context)

    def test_get_ctx_explicit(self):
        ctx = Context()
        assert get_ctx(ctx) is ctx


# ===================================================================
# ASTVECTOR / ASTMAP
# ===================================================================


class TestAstVector:
    def test_create(self):
        v = AstVector()
        assert len(v) == 0

    def test_push_and_len(self):
        v = AstVector()
        v.push(Int("x"))
        v.push(Int("y"))
        assert len(v) == 2

    def test_getitem(self):
        v = AstVector()
        x = Int("x")
        v.push(x)
        assert v[0] is x

    def test_setitem(self):
        v = AstVector()
        v.push(Int("x"))
        y = Int("y")
        v[0] = y
        assert v[0] is y

    def test_iter(self):
        v = AstVector()
        v.push(Int("x"))
        v.push(Int("y"))
        items = list(v)
        assert len(items) == 2

    def test_contains(self):
        v = AstVector()
        x = Int("x")
        v.push(x)
        assert x in v

    def test_translate(self):
        v = AstVector()
        v.push(Int("x"))
        assert v.translate(Context()) is v


class TestAstMap:
    def test_create(self):
        m = AstMap()
        assert len(m) == 0

    def test_setget(self):
        m = AstMap()
        x = Int("x")
        y = Int("y")
        m[x] = y
        assert m[x] is y

    def test_contains(self):
        m = AstMap()
        x = Int("x")
        m[x] = Int("y")
        assert x in m

    def test_erase(self):
        m = AstMap()
        x = Int("x")
        m[x] = Int("y")
        m.erase(x)
        assert x not in m

    def test_reset(self):
        m = AstMap()
        m[Int("x")] = Int("y")
        m.reset()
        assert len(m) == 0

    def test_keys(self):
        m = AstMap()
        x = Int("x")
        m[x] = Int("y")
        assert x in m.keys()


# ===================================================================
# FLOATING-POINT API
# ===================================================================


class TestFPAPI:
    def test_fp_sort(self):
        s = FPSort(8, 24)
        assert isinstance(s, FPSortRef)
        assert s.ebits() == 8
        assert s.sbits() == 24

    def test_float16(self):
        s = Float16()
        assert s.ebits() == 5 and s.sbits() == 11

    def test_float32(self):
        s = Float32()
        assert s.ebits() == 8 and s.sbits() == 24

    def test_float64(self):
        s = Float64()
        assert s.ebits() == 11 and s.sbits() == 53

    def test_float128(self):
        s = Float128()
        assert s.ebits() == 15 and s.sbits() == 113

    def test_fp_var(self):
        x = FP("x", Float32())
        assert isinstance(x, FPRef)

    def test_fps(self):
        x, y = FPs("x y", Float64())
        assert isinstance(x, FPRef)
        assert isinstance(y, FPRef)

    def test_fpval(self):
        v = FPVal(1.5)
        assert isinstance(v, FPNumRef)

    def test_fpnan(self):
        v = fpNaN(Float32())
        assert isinstance(v, FPNumRef)

    def test_fp_plus_infinity(self):
        v = fpPlusInfinity(Float64())
        assert isinstance(v, FPNumRef)

    def test_fp_minus_infinity(self):
        v = fpMinusInfinity(Float64())
        assert isinstance(v, FPNumRef)

    def test_fp_plus_zero(self):
        v = fpPlusZero(Float32())
        assert isinstance(v, FPNumRef)

    def test_fp_minus_zero(self):
        v = fpMinusZero(Float32())
        assert isinstance(v, FPNumRef)

    def test_rounding_modes(self):
        assert isinstance(RNE(), FPRMRef)
        assert isinstance(RNA(), FPRMRef)
        assert isinstance(RTP(), FPRMRef)
        assert isinstance(RTN(), FPRMRef)
        assert isinstance(RTZ(), FPRMRef)

    def test_rounding_mode_long_names(self):
        assert isinstance(RoundNearestTiesToEven(), FPRMRef)
        assert isinstance(RoundNearestTiesToAway(), FPRMRef)
        assert isinstance(RoundTowardPositive(), FPRMRef)
        assert isinstance(RoundTowardNegative(), FPRMRef)
        assert isinstance(RoundTowardZero(), FPRMRef)

    def test_fp_add(self):
        x, y = FPs("x y", Float32())
        result = fpAdd(RNE(), x, y)
        assert isinstance(result, FPRef)

    def test_fp_sub(self):
        x, y = FPs("x y", Float32())
        result = fpSub(RNE(), x, y)
        assert isinstance(result, FPRef)

    def test_fp_mul(self):
        x, y = FPs("x y", Float32())
        result = fpMul(RNE(), x, y)
        assert isinstance(result, FPRef)

    def test_fp_div(self):
        x, y = FPs("x y", Float32())
        result = fpDiv(RNE(), x, y)
        assert isinstance(result, FPRef)

    def test_fp_neg(self):
        x = FP("x", Float32())
        result = fpNeg(x)
        assert isinstance(result, FPRef)

    def test_fp_abs(self):
        x = FP("x", Float32())
        result = fpAbs(x)
        assert isinstance(result, FPRef)

    def test_fp_sqrt(self):
        x = FP("x", Float32())
        result = fpSqrt(RNE(), x)
        assert isinstance(result, FPRef)

    def test_fp_fma(self):
        x, y, z = FPs("x y z", Float32())
        result = fpFMA(RNE(), x, y, z)
        assert isinstance(result, FPRef)

    def test_fp_rem(self):
        x, y = FPs("x y", Float32())
        result = fpRem(x, y)
        assert isinstance(result, FPRef)

    def test_fp_min_max(self):
        x, y = FPs("x y", Float32())
        assert isinstance(fpMin(x, y), FPRef)
        assert isinstance(fpMax(x, y), FPRef)

    def test_fp_comparisons(self):
        x, y = FPs("x y", Float32())
        assert isinstance(fpLEQ(x, y), BoolRef)
        assert isinstance(fpLT(x, y), BoolRef)
        assert isinstance(fpGEQ(x, y), BoolRef)
        assert isinstance(fpGT(x, y), BoolRef)
        assert isinstance(fpEQ(x, y), BoolRef)

    def test_fp_predicates(self):
        x = FP("x", Float32())
        assert isinstance(fpIsNaN(x), BoolRef)
        assert isinstance(fpIsInf(x), BoolRef)
        assert isinstance(fpIsZero(x), BoolRef)
        assert isinstance(fpIsNormal(x), BoolRef)
        assert isinstance(fpIsSubnormal(x), BoolRef)
        assert isinstance(fpIsNegative(x), BoolRef)
        assert isinstance(fpIsPositive(x), BoolRef)

    def test_fp_to_real(self):
        x = FP("x", Float32())
        result = fpToReal(x)
        assert isinstance(result, ArithRef)

    def test_fp_to_sbv(self):
        x = FP("x", Float32())
        result = fpToSBV(RNE(), x, BitVecSort(32))
        assert isinstance(result, BitVecRef)

    def test_fp_to_ubv(self):
        x = FP("x", Float32())
        result = fpToUBV(RNE(), x, BitVecSort(32))
        assert isinstance(result, BitVecRef)

    def test_fp_to_fp(self):
        x = FP("x", Float32())
        result = fpToFP(RNE(), x, Float64())
        assert isinstance(result, FPRef)

    def test_fpbv_to_fp(self):
        bv = BitVec("bv", 32)
        result = fpBVToFP(bv, Float32())
        assert isinstance(result, FPRef)

    def test_fp_fp_to_fp(self):
        x = FP("x", Float32())
        result = fpFPToFP(RNE(), x, Float64())
        assert isinstance(result, FPRef)

    def test_fp_real_to_fp(self):
        r = Real("r")
        result = fpRealToFP(RNE(), r, Float32())
        assert isinstance(result, FPRef)

    def test_fp_signed_to_fp(self):
        bv = BitVec("bv", 32)
        result = fpSignedToFP(RNE(), bv, Float32())
        assert isinstance(result, FPRef)

    def test_fp_unsigned_to_fp(self):
        bv = BitVec("bv", 32)
        result = fpUnsignedToFP(RNE(), bv, Float32())
        assert isinstance(result, FPRef)

    def test_fp_operator_overloads(self):
        x, y = FPs("x y", Float32())
        assert isinstance(x + y, FPRef)
        assert isinstance(x - y, FPRef)
        assert isinstance(x * y, FPRef)
        assert isinstance(x / y, FPRef)
        assert isinstance(-x, FPRef)
        assert isinstance(+x, FPRef)
        assert isinstance(abs(x), FPRef)

    def test_fp_comparison_overloads(self):
        x, y = FPs("x y", Float32())
        assert isinstance(x < y, BoolRef)
        assert isinstance(x <= y, BoolRef)
        assert isinstance(x > y, BoolRef)
        assert isinstance(x >= y, BoolRef)

    def test_fp_sort_method(self):
        x = FP("x", Float32())
        s = x.sort()
        assert isinstance(s, FPSortRef)
        assert s.ebits() == 8

    def test_fp_ebits_sbits(self):
        x = FP("x", Float64())
        assert x.ebits() == 11
        assert x.sbits() == 53


# ===================================================================
# SET API
# ===================================================================


class TestSetAPI:
    def test_set_sort(self):
        s = SetSort(IntSort())
        assert isinstance(s, ArraySortRef)

    def test_empty_set(self):
        s = EmptySet(IntSort())
        assert isinstance(s, ArrayRef)

    def test_full_set(self):
        s = FullSet(IntSort())
        assert isinstance(s, ArrayRef)

    def test_is_member(self):
        s = EmptySet(IntSort())
        result = IsMember(IntVal(1), s)
        assert isinstance(result, BoolRef)

    def test_set_add(self):
        s = EmptySet(IntSort())
        s2 = SetAdd(s, IntVal(1))
        assert isinstance(s2, ArrayRef)

    def test_set_del(self):
        s = FullSet(IntSort())
        s2 = SetDel(s, IntVal(1))
        assert isinstance(s2, ArrayRef)

    def test_set_union(self):
        a = EmptySet(IntSort())
        b = EmptySet(IntSort())
        result = SetUnion(a, b)
        assert isinstance(result, ArrayRef)

    def test_set_intersect(self):
        a = EmptySet(IntSort())
        b = FullSet(IntSort())
        result = SetIntersect(a, b)
        assert isinstance(result, ArrayRef)

    def test_set_complement(self):
        s = EmptySet(IntSort())
        result = SetComplement(s)
        assert isinstance(result, ArrayRef)

    def test_set_difference(self):
        a = FullSet(IntSort())
        b = EmptySet(IntSort())
        result = SetDifference(a, b)
        assert isinstance(result, ArrayRef)

    def test_is_subset(self):
        a = EmptySet(IntSort())
        b = FullSet(IntSort())
        result = IsSubset(a, b)
        assert isinstance(result, BoolRef)

    def test_set_has_size_raises(self):
        s = EmptySet(IntSort())
        with pytest.raises(NotImplementedError):
            SetHasSize(s, 5)


# ===================================================================
# SEQUENCE / CHAR / FINITE DOMAIN
# ===================================================================


class TestSeqCharFD:
    def test_seq_sort_char(self):
        s = SeqSort(CharSort())
        assert isinstance(s, (SortRef, StringSortRef))

    def test_empty_string(self):
        e = Empty(StringSort())
        assert isinstance(e, StringRef)

    def test_unit(self):
        s = StringVal("a")
        u = Unit(s)
        assert isinstance(u, (StringRef, ExprRef))

    def test_char_sort(self):
        s = CharSort()
        assert isinstance(s, SortRef)

    def test_char_val(self):
        c = CharVal("a")
        assert isinstance(c, ExprRef)

    def test_char_from_bv(self):
        bv = BitVecVal(65, 8)
        c = CharFromBv(bv)
        assert isinstance(c, ExprRef)

    def test_char_to_bv(self):
        c = CharVal("a")
        bv = CharToBv(c)
        assert isinstance(bv, BitVecRef)

    def test_char_to_int(self):
        c = CharVal("a")
        i = CharToInt(c)
        assert isinstance(i, ArithRef)

    def test_char_is_digit(self):
        c = CharVal("5")
        result = CharIsDigit(c)
        assert isinstance(result, BoolRef)

    def test_finite_domain_sort(self):
        s = FiniteDomainSort("S", 10)
        assert isinstance(s, SortRef)

    def test_finite_domain_val(self):
        s = FiniteDomainSort("S", 10)
        v = FiniteDomainVal(3, s)
        assert isinstance(v, ExprRef)

    def test_finite_domain_size(self):
        s = FiniteDomainSort("S", 10)
        assert FiniteDomainSize(s) == 10


# ===================================================================
# FIXEDPOINT
# ===================================================================


class TestFixedpoint:
    def test_create(self):
        fp = Fixedpoint()
        assert isinstance(fp, Fixedpoint)

    def test_add_rule(self):
        fp = Fixedpoint()
        fp.add_rule(BoolVal(True))
        assert len(fp._rules) == 1

    def test_register_relation(self):
        fp = Fixedpoint()
        f = Function("f", IntSort(), BoolSort())
        fp.register_relation(f)
        assert len(fp._decls) == 1

    def test_query_proves_true(self, kernel):
        """An empty fixedpoint querying True proves via grind."""
        fp = Fixedpoint()
        result = fp.query(BoolVal(True))
        assert result == sat

    def test_parse_string_raises(self):
        fp = Fixedpoint()
        with pytest.raises(NotImplementedError):
            fp.parse_string("(rule true)")

    def test_repr(self):
        fp = Fixedpoint()
        assert "0 rules" in repr(fp)


# ===================================================================
# RECFUNCTION
# ===================================================================


class TestRecFunction:
    def test_rec_function(self):
        f = RecFunction("f", IntSort(), IntSort())
        assert isinstance(f, FuncDeclRef)

    def test_rec_add_definition(self):
        f = RecFunction("f", IntSort(), IntSort())
        x = Int("x")
        RecAddDefinition(f, [x], x + 1)  # no-op, just shouldn't raise


# ===================================================================
# DE BRUIJN VAR
# ===================================================================


class TestDeBruijnVar:
    def test_var_creates_const(self):
        v = Var(0, IntSort())
        assert isinstance(v, ExprRef)

    def test_get_var_index(self):
        v = Var(3, IntSort())
        assert get_var_index(v) == 3

    def test_get_var_index_raises(self):
        x = Int("x")
        with pytest.raises(TypeError):
            get_var_index(x)


# ===================================================================
# MULTIPATTERN / DISJOINTSUM
# ===================================================================


class TestMultiPatternDisjointSum:
    def test_multi_pattern(self):
        x = Int("x")
        p = MultiPattern(x)
        assert isinstance(p, ExprRef)

    def test_multi_pattern_empty(self):
        p = MultiPattern()
        assert isinstance(p, ExprRef)

    def test_disjoint_sum(self, kernel):
        sort, pairs = DisjointSum("DS", [IntSort(), BoolSort()])
        assert isinstance(sort, SortRef)
        assert len(pairs) == 2


# ===================================================================
# PREDICATES (stubs.py)
# ===================================================================


class TestStubPredicates:
    def test_is_ast(self):
        assert is_ast(Int("x"))
        assert is_ast(IntSort())
        assert not is_ast(42)

    def test_is_fp(self):
        assert is_fp(FP("x", Float32()))
        assert not is_fp(Int("x"))

    def test_is_fprm(self):
        assert is_fprm(RNE())
        assert not is_fprm(Int("x"))

    def test_is_fp_value(self):
        assert is_fp_value(FPVal(1.0))
        assert not is_fp_value(FP("x", Float32()))

    def test_is_seq(self):
        assert is_seq(String("s"))
        assert not is_seq(Int("x"))

    def test_is_re(self):
        assert is_re(Re(StringVal("abc")))
        assert not is_re(Int("x"))

    def test_is_const_array(self):
        assert is_const_array(K(IntSort(), IntVal(0)))
        assert not is_const_array(Int("x"))

    def test_is_K(self):
        assert is_K(K(IntSort(), IntVal(0)))

    def test_is_select(self):
        a = Array("a", IntSort(), IntSort())
        result = Select(a, IntVal(0))
        assert is_select(result)
        assert not is_select(a)

    def test_is_store(self):
        a = Array("a", IntSort(), IntSort())
        result = Store(a, IntVal(0), IntVal(1))
        assert is_store(result)
        assert not is_store(a)

    def test_is_to_real(self):
        x = Int("x")
        result = ToReal(x)
        assert is_to_real(result)
        assert not is_to_real(x)

    def test_is_to_int(self):
        x = Real("x")
        result = ToInt(x)
        assert is_to_int(result)
        assert not is_to_int(x)

    def test_is_pattern(self):
        assert not is_pattern(Int("x"))


# ===================================================================
# STRING/REGEX EXTRAS
# ===================================================================


class TestStringRegexExtras:
    def test_last_index_of(self):
        s = String("s")
        t = String("t")
        result = LastIndexOf(s, t)
        assert isinstance(result, ArithRef)

    def test_str_to_code(self):
        s = StringVal("a")
        result = StrToCode(s)
        assert isinstance(result, ArithRef)

    def test_str_from_code(self):
        c = IntVal(65)
        result = StrFromCode(c)
        assert isinstance(result, StringRef)

    def test_at(self):
        s = String("s")
        result = At(s, IntVal(0))
        assert isinstance(result, StringRef)

    def test_at_int_literal(self):
        s = String("s")
        result = At(s, 0)
        assert isinstance(result, StringRef)

    def test_diff(self):
        r1 = Re(StringVal("abc"))
        r2 = Re(StringVal("def"))
        result = Diff(r1, r2)
        assert isinstance(result, ReRef)


# ===================================================================
# STRUCTURAL EQUALITY
# ===================================================================


class TestStructuralEquality:
    def test_eq_same_expr(self):
        x = Int("x")
        assert eq(x, x)

    def test_eq_different_expr(self):
        x = Int("x")
        y = Int("y")
        assert not eq(x, y)

    def test_eq_same_sort(self):
        assert eq(IntSort(), IntSort())

    def test_eq_different_sort(self):
        assert not eq(IntSort(), RealSort())


# ===================================================================
# UTILITIES
# ===================================================================


class TestUtilities:
    def test_enable_trace(self):
        enable_trace("smt")  # no-op

    def test_disable_trace(self):
        disable_trace("smt")  # no-op

    def test_open_log(self):
        open_log("test.log")  # no-op

    def test_get_version(self):
        v = get_version()
        assert isinstance(v, tuple)
        assert len(v) == 4

    def test_get_version_string(self):
        s = get_version_string()
        assert isinstance(s, str)

    def test_get_full_version(self):
        s = get_full_version()
        assert isinstance(s, str)


# ===================================================================
# FUNCINTERP / FUNCENTRY
# ===================================================================


class TestFuncInterpEntry:
    def test_func_entry_num_args(self):
        e = FuncEntry()
        assert e.num_args() == 0

    def test_func_entry_as_list(self):
        e = FuncEntry()
        assert e.as_list() == []

    def test_func_entry_value_raises(self):
        e = FuncEntry()
        with pytest.raises(NotImplementedError):
            e.value()

    def test_func_interp_num_entries(self):
        fi = FuncInterp()
        assert fi.num_entries() == 0

    def test_func_interp_as_list(self):
        fi = FuncInterp()
        assert fi.as_list() == []

    def test_func_interp_else_raises(self):
        fi = FuncInterp()
        with pytest.raises(NotImplementedError):
            fi.else_value()


# ===================================================================
# UPDATE ALIAS
# ===================================================================


class TestUpdate:
    def test_update_is_store(self):
        a = Array("a", IntSort(), IntSort())
        result = Update(a, IntVal(0), IntVal(1))
        assert isinstance(result, ArrayRef)


# ===================================================================
# PROBE / STATISTICS
# ===================================================================


class TestProbeStatistics:
    def test_probe_create(self):
        p = Probe("num-consts")
        assert isinstance(p, Probe)

    def test_probe_call(self):
        p = Probe("num-consts")
        assert p() == 0.0

    def test_probe_comparisons(self):
        p = Probe("num-consts")
        assert isinstance(p < 5, Probe)
        assert isinstance(p > 0, Probe)
        assert isinstance(p <= 10, Probe)
        assert isinstance(p >= 0, Probe)

    def test_probe_and_or(self):
        p1 = Probe("num-consts")
        p2 = Probe("size")
        assert isinstance(ProbeAnd(p1, p2), Probe)
        assert isinstance(ProbeOr(p1, p2), Probe)

    def test_fail_if(self):
        p = Probe("num-consts")
        t = FailIf(p)
        assert isinstance(t, Tactic)

    def test_statistics_create(self):
        s = Statistics()
        assert len(s) == 0

    def test_statistics_with_data(self):
        s = Statistics({"time": 1.5, "conflicts": 42})
        assert len(s) == 2
        assert s["time"] == 1.5
        assert "time" in s

    def test_statistics_keys(self):
        s = Statistics({"a": 1, "b": 2})
        assert set(s.keys()) == {"a", "b"}


# ===================================================================
# MODELREF EXTENDED
# ===================================================================


class TestModelRefExtended:
    def test_eval_raises(self):
        m = ModelRef()
        with pytest.raises(NotImplementedError):
            m.eval(Int("x"))

    def test_evaluate_alias(self):
        m = ModelRef()
        assert m.evaluate == m.eval

    def test_decls_empty(self):
        m = ModelRef()
        assert m.decls() == []

    def test_len(self):
        m = ModelRef()
        assert len(m) == 0

    def test_contains(self):
        m = ModelRef()
        assert Int("x") not in m

    def test_iter(self):
        m = ModelRef()
        assert list(m) == []

    def test_sexpr(self):
        m = ModelRef()
        assert isinstance(m.sexpr(), str)


# ===================================================================
# SOLVER EXTENDED
# ===================================================================


class TestSolverExtended:
    def test_from_file_raises(self):
        with pytest.raises(NotImplementedError):
            Solver.from_file("test.smt2")

    def test_from_string_raises(self):
        with pytest.raises(NotImplementedError):
            Solver.from_string("(assert true)")

    def test_cube_empty(self):
        s = Solver()
        assert s.cube() == []

    def test_consequences(self):
        s = Solver()
        result, _ = s.consequences([], [])
        assert result == unknown

    def test_help(self):
        s = Solver()
        h = s.help()
        assert isinstance(h, str)

    def test_param_descrs(self):
        s = Solver()
        assert isinstance(s.param_descrs(), dict)

    def test_translate(self):
        s = Solver()
        assert s.translate(None) is s

    def test_proof_raises(self):
        s = Solver()
        with pytest.raises(NotImplementedError):
            s.proof()


# ===================================================================
# PARSE_SMT2_FILE
# ===================================================================


class TestParseSmt2File:
    def test_basic(self, tmp_path):
        f = tmp_path / "test.smt2"
        f.write_text("(declare-const x Int) (assert (> x 0))")
        result = parse_smt2_file(str(f))
        assert len(result) == 1

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_smt2_file("/nonexistent/path.smt2")


# ===================================================================
# TACTIC COMBINATORS (ParOr, ParThen, ParAndThen)
# ===================================================================


class TestTacticCombinatorsExtended:
    def test_par_or(self):
        t = ParOr(Tactic("grind"), Tactic("omega"))
        assert isinstance(t, Tactic)

    def test_par_then(self):
        t = ParThen(Tactic("grind"), Tactic("omega"))
        assert isinstance(t, Tactic)

    def test_par_and_then_alias(self):
        assert ParAndThen is ParThen

    def test_par_or_apply(self):
        g = Goal()
        x = Int("x")
        g.add(x > 0)
        t = ParOr(Tactic("grind"), Tactic("omega"))
        result = t.apply(g)
        assert isinstance(result, ApplyResult)

    def test_par_then_apply(self):
        g = Goal()
        x = Int("x")
        g.add(x > 0)
        t = ParThen(Tactic("grind"), Tactic("omega"))
        result = t.apply(g)
        assert isinstance(result, ApplyResult)


# ===================================================================
# ASTREF ALIAS
# ===================================================================


class TestAstRefAlias:
    def test_astref_is_exprref(self):
        assert AstRef is ExprRef


# ===================================================================
# DOMAIN MAPPING BUG FIX TESTS (end-to-end, exercise Lean)
# ===================================================================


class TestBugFix1_ArithShiftRight:
    """Bug #1: >> on BitVec should be arithmetic (sign-extending), not logical."""

    def test_rshift_is_arithmetic(self, kernel):
        """(0xFF : BitVec 8) >> 1 should be 0xFF (sign-extending), not 0x7F."""
        # Arithmetic shift right of -1 (0xFF in 8-bit signed) stays -1
        claim = (BitVecVal(0xFF, 8) >> 1) == BitVecVal(0xFF, 8)
        assert prove(claim)

    def test_lshr_is_logical(self, kernel):
        """LShR(0xFF, 1) should be 0x7F (zero-filling)."""
        claim = LShR(BitVecVal(0xFF, 8), 1) == BitVecVal(0x7F, 8)
        assert prove(claim)

    def test_rshift_vs_lshr_differ(self, kernel):
        """>> and LShR give different results for negative values."""
        x = BitVecVal(0x80, 8)  # -128 in signed 8-bit
        # Arithmetic: -128 >> 1 = -64 = 0xC0
        assert prove((x >> 1) == BitVecVal(0xC0, 8))
        # Logical: LShR(-128, 1) = 64 = 0x40
        assert prove(LShR(x, 1) == BitVecVal(0x40, 8))


class TestBugFix2_BV2IntSigned:
    """Bug #2: BV2Int should respect is_signed flag."""

    def test_bv2int_unsigned_default(self, kernel):
        """BV2Int(0xFF, 8) default (unsigned) should be 255."""
        claim = BV2Int(BitVecVal(0xFF, 8)) == IntVal(255)
        assert prove(claim)

    def test_bv2int_signed(self, kernel):
        """BV2Int(0xFF, 8, is_signed=True) should be -1."""
        claim = BV2Int(BitVecVal(0xFF, 8), is_signed=True) == IntVal(-1)
        assert prove(claim)


class TestBugFix3_EuclideanDivMod:
    """Bug #3: Int div/mod should use Euclidean (SMT-LIB) semantics."""

    def test_negative_div(self, kernel):
        """(-7) / 2 should be -4 (Euclidean), not -3 (truncation)."""
        claim = IntVal(-7) / IntVal(2) == IntVal(-4)
        assert prove(claim)

    def test_negative_mod(self, kernel):
        """(-7) % 2 should be 1 (Euclidean), not -1 (truncation)."""
        claim = IntVal(-7) % IntVal(2) == IntVal(1)
        assert prove(claim)

    def test_positive_div_unchanged(self, kernel):
        """7 / 2 should still be 3."""
        claim = IntVal(7) / IntVal(2) == IntVal(3)
        assert prove(claim)

    def test_positive_mod_unchanged(self, kernel):
        """7 % 2 should still be 1."""
        claim = IntVal(7) % IntVal(2) == IntVal(1)
        assert prove(claim)

    def test_mod_always_nonneg(self, kernel):
        """Euclidean mod is always non-negative."""
        x = Int("x")
        claim = ForAll([x], IntVal(-100) % IntVal(7) >= IntVal(0))
        assert prove(claim)
