"""z3py compatibility layer tests.

Uses the existing TestLib fixture to avoid managed-project builds in CI.
Exercises the expression AST, solver, prove(), and convenience functions.
"""

from __future__ import annotations

import pytest

from lean_py.kernel import Kernel
from lean_py.z3 import (
    Abs,
    AllChar,
    And,
    Array,
    ArraySort,
    AShr,
    AsArray,
    BV2Int,
    BitVec,
    BitVecRef,
    BitVecSort,
    BitVecVal,
    BitVecs,
    Bool,
    BoolSort,
    BoolVal,
    Complement,
    Concat,
    Const,
    Consts,
    Contains,
    Datatype,
    DeclareSort,
    Distinct,
    Exists,
    ExprRef,
    Extract,
    ForAll,
    FreshBool,
    FreshConst,
    FreshInt,
    FreshReal,
    Function,
    Goal,
    ApplyResult,
    If,
    Implies,
    InRe,
    IndexOf,
    Intersect,
    Int,
    Int2BV,
    IntSort,
    IntToStr,
    IntVal,
    Ints,
    K,
    LShR,
    Lambda,
    Length,
    Loop,
    Map,
    ModelRef,
    Nat,
    NatSort,
    NatVal,
    Not,
    Option,
    Or,
    Plus,
    PrefixOf,
    Product,
    Q,
    Range,
    RatVal,
    Re,
    Real,
    RealSort,
    Replace,
    RotateLeft,
    RotateRight,
    SDiv,
    SRem,
    Select,
    SignExt,
    Solver,
    Star,
    Store,
    StrConcat,
    StrToInt,
    String,
    StringRef,
    StringSort,
    StringSortRef,
    StringVal,
    Strings,
    SubString,
    SuffixOf,
    Sum,
    Tactic,
    Then,
    OrElse,
    Repeat,
    ToInt,
    ToReal,
    UDiv,
    UGE,
    UGT,
    ULE,
    ULT,
    URem,
    Union,
    Xor,
    ZeroExt,
    is_add,
    is_and,
    is_array,
    is_bool,
    is_bv,
    is_const,
    is_distinct,
    is_div,
    is_eq,
    is_expr,
    is_false,
    is_implies,
    is_int,
    is_mul,
    is_not,
    is_or,
    is_quantifier,
    is_real,
    is_string,
    is_string_value,
    is_sub,
    is_true,
    is_var,
    sat,
    set_kernel,
    simplify,
    unknown,
    unsat,
    Float64,
    FPVal,
    FPNumRef,
    FPRef,
    fpAdd,
    fpMul,
    fpNeg,
    fpLT,
    fpEQ,
    fpNaN,
    fpPlusInfinity,
    RNE,
    RealVal,
    Reals,
    BVAddNoOverflow,
    BVMulNoOverflow,
    fpIsPositive,
    fpIsNegative,
    CharSort,
    CharSortRef,
    CharVal,
    CharRef,
    CharFromBv,
    CharToBv,
    CharToInt,
    CharIsDigit,
    SeqSort,
    SeqSortRef,
    SeqRef,
    Empty,
    Unit,
    SetSort,
    EmptySet,
    FullSet,
    SetAdd,
    SetDel,
    IsMember,
    SetUnion,
    SetIntersect,
    SetComplement,
    SetDifference,
    IsSubset,
    ArrayRef,
)
from lean_py.z3._ast import (
    BinOp,
    BinOpNode,
    BoolLit,
    BvLit,
    ConstArrayNode,
    DistinctNode,
    ExistsNode,
    ExtractNode,
    ForAllNode,
    FpLitNode,
    InReNode,
    IntASTSort,
    IntLit,
    IteNode,
    LambdaNode,
    NatLit,
    PropSort,
    ReStarNode,
    SelectNode,
    SignExtNode,
    StoreNode,
    StrConcatNode,
    StrContainsNode,
    StrLenNode,
    StringASTSort,
    StringLit,
    ToRealNode,
    ToIntNode,
    UnOp,
    UnOpNode,
    Var,
    ZeroExtNode,
    InductiveCtorNode,
)
from lean_py.z3.solver import _try_prove


@pytest.fixture(scope="module")
def kernel(example_lib) -> Kernel:
    k = Kernel(example_lib)
    import subprocess
    from pathlib import Path
    sp = subprocess.check_output(
        ["lake", "env", "printenv", "LEAN_PATH"],
        cwd=str(Path(__file__).parent / "lean"),
    ).decode().strip()
    k.init_search(sp)
    k.load(["Init", "LeanPy.Z3"])
    set_kernel(k)
    return k


# ------------------------------------------------------------------
# Expression building (pure, no kernel needed)
# ------------------------------------------------------------------


class TestExprBuilding:
    def test_int_var(self):
        x = Int("x")
        assert isinstance(x._ast, Var) and x._ast.name == "x"
        assert x.sort() == IntSort()
        assert any(n == "x" for n, _ in x._vars)

    def test_arith_ops(self):
        x, y = Ints("x y")
        add = x + y
        assert isinstance(add._ast, BinOpNode) and add._ast.op == BinOp.ADD
        sub = x - y
        assert isinstance(sub._ast, BinOpNode) and sub._ast.op == BinOp.SUB
        mul = x * y
        assert isinstance(mul._ast, BinOpNode) and mul._ast.op == BinOp.MUL
        neg = -x
        assert isinstance(neg._ast, UnOpNode) and neg._ast.op == UnOp.NEG

    def test_comparison(self):
        x = Int("x")
        gt = x > 5
        assert isinstance(gt._ast, BinOpNode) and gt._ast.op == BinOp.GT
        lt = x < 5
        assert isinstance(lt._ast, BinOpNode) and lt._ast.op == BinOp.LT
        ge = x >= 5
        assert isinstance(ge._ast, BinOpNode) and ge._ast.op == BinOp.GE
        le = x <= 5
        assert isinstance(le._ast, BinOpNode) and le._ast.op == BinOp.LE

    def test_eq_ne(self):
        x, y = Ints("x y")
        eq = x == y
        assert isinstance(eq._ast, BinOpNode) and eq._ast.op == BinOp.EQ
        ne = x != y
        assert isinstance(ne._ast, BinOpNode) and ne._ast.op == BinOp.NE

    def test_bool_ops(self):
        a, b = Bool("a"), Bool("b")
        conj = And(a, b)
        assert isinstance(conj._ast, BinOpNode) and conj._ast.op == BinOp.AND
        disj = Or(a, b)
        assert isinstance(disj._ast, BinOpNode) and disj._ast.op == BinOp.OR
        neg = Not(a)
        assert isinstance(neg._ast, UnOpNode) and neg._ast.op == UnOp.NOT
        imp = Implies(a, b)
        assert isinstance(imp._ast, BinOpNode) and imp._ast.op == BinOp.IMPLIES
        xr = Xor(a, b)
        assert isinstance(xr._ast, BinOpNode) and xr._ast.op == BinOp.XOR

    def test_bool_operators(self):
        a, b = Bool("a"), Bool("b")
        assert isinstance((a & b)._ast, BinOpNode) and (a & b)._ast.op == BinOp.AND
        assert isinstance((a | b)._ast, BinOpNode) and (a | b)._ast.op == BinOp.OR
        assert isinstance((~a)._ast, UnOpNode) and (~a)._ast.op == UnOp.NOT

    def test_forall(self):
        x = Int("x")
        expr = ForAll([x], x + 0 == x)
        assert isinstance(expr._ast, ForAllNode)
        assert expr._ast.name == "x"
        # x should be bound, not free
        assert not any(n == "x" for n, _ in expr._vars)

    def test_exists(self):
        x = Int("x")
        expr = Exists([x], x > 0)
        assert isinstance(expr._ast, ExistsNode)

    def test_distinct(self):
        x, y, z = Ints("x y z")
        d = Distinct(x, y, z)
        assert isinstance(d._ast, DistinctNode)
        assert len(d._ast.args) == 3

    def test_if_then_else(self):
        x = Int("x")
        expr = If(x > 0, x, -x)
        assert isinstance(expr._ast, IteNode)

    def test_int_coercion(self):
        x = Int("x")
        add = x + 1
        assert isinstance(add._ast, BinOpNode) and add._ast.op == BinOp.ADD
        assert isinstance(add._ast.rhs, IntLit) and add._ast.rhs.val == 1
        radd = 1 + x
        assert isinstance(radd._ast, BinOpNode) and radd._ast.op == BinOp.ADD
        assert isinstance(radd._ast.lhs, IntLit) and radd._ast.lhs.val == 1

    def test_function_decl(self):
        S = DeclareSort("S")
        f = Function("f", IntSort(), S)
        x = Int("x")
        app = f(x)
        # f and S should be free vars
        assert any(n == "f" for n, _ in app._vars)
        var_names = {n for n, _ in app._vars}
        assert "S" in var_names

    def test_nat_var(self):
        n = Nat("n")
        assert n.sort() == NatSort()
        assert any(name == "n" for name, _ in n._vars)

    def test_val_constructors(self):
        assert isinstance(IntVal(42)._ast, IntLit) and IntVal(42)._ast.val == 42
        assert isinstance(NatVal(7)._ast, NatLit) and NatVal(7)._ast.val == 7
        assert isinstance(BoolVal(True)._ast, BoolLit) and BoolVal(True)._ast.val is True
        assert isinstance(BoolVal(False)._ast, BoolLit) and BoolVal(False)._ast.val is False


class TestCompilation:
    """Tests that AST is properly structured for compilation."""

    def test_no_vars(self):
        bv = BoolVal(True)
        assert isinstance(bv._ast, BoolLit)
        assert len(bv._vars) == 0

    def test_single_var(self):
        x = Int("x")
        expr = x > 0
        assert len(expr._vars) == 1

    def test_multiple_vars(self):
        x, y = Ints("x y")
        expr = And(x > 0, y > 0)
        assert len(expr._vars) == 2

    def test_uninterpreted_sort_tracked(self):
        S = DeclareSort("S")
        f = Function("f", S, BoolSort())
        a = Const("a", S)
        app = f(a)
        var_names = {n for n, _ in app._vars}
        assert "S" in var_names
        assert "a" in var_names
        assert "f" in var_names


# ------------------------------------------------------------------
# Proving (requires kernel)
# ------------------------------------------------------------------


class TestProve:
    def test_arith_simple(self, kernel):
        x = Int("x")
        result = _try_prove(Implies(x > 0, x + 1 > 0))
        assert result is True

    def test_linear_combo(self, kernel):
        x, y = Ints("x y")
        claim = Implies(And(x > 0, y > 0), x + y > 0)
        assert _try_prove(claim)

    def test_nat_identity(self, kernel):
        n = Nat("n")
        claim = ForAll([n], n + 0 == n)
        assert _try_prove(claim)

    def test_bool_tautology(self, kernel):
        p = Bool("p")
        claim = Implies(p, p)
        assert _try_prove(claim)

    def test_double_negation(self, kernel):
        p = Bool("p")
        claim = Implies(Not(Not(p)), p)
        assert _try_prove(claim)

    def test_nat_arith(self, kernel):
        n = Nat("n")
        claim = ForAll([n], Implies(n > 0, n + 1 > 1))
        assert _try_prove(claim)


# ------------------------------------------------------------------
# Solver
# ------------------------------------------------------------------


class TestSolver:
    def test_unsat_contradiction(self, kernel):
        x = Int("x")
        s = Solver()
        s.add(x > 0, x < 0)
        assert s.check() == unsat

    def test_unsat_equality(self, kernel):
        x = Int("x")
        s = Solver()
        s.add(x == IntVal(1), x == IntVal(2))
        assert s.check() == unsat

    def test_push_pop(self, kernel):
        x = Int("x")
        s = Solver()
        s.add(x > 0)
        s.push()
        s.add(x < 0)
        assert s.check() == unsat
        s.pop()
        # After pop, only x > 0 remains -- not contradictory
        assert s.check() == unknown

    def test_context_manager(self, kernel):
        x = Int("x")
        s = Solver()
        s.add(x > 0)
        with s:
            s.add(x < 0)
            assert s.check() == unsat
        # After context exit, back to just x > 0
        assert len(s.assertions()) == 1

    def test_reset(self, kernel):
        s = Solver()
        s.add(BoolVal(True))
        s.reset()
        assert len(s.assertions()) == 0


# ------------------------------------------------------------------
# Syllogism with uninterpreted sorts/functions
# ------------------------------------------------------------------


class TestSyllogism:
    def test_socrates(self, kernel):
        """All men are mortal. Socrates is a man. Therefore Socrates is mortal."""
        Entity = DeclareSort("Entity")
        Man = Function("Man", Entity, BoolSort())
        Mortal = Function("Mortal", Entity, BoolSort())
        socrates = Const("socrates", Entity)
        x = Const("x", Entity)

        all_men_mortal = ForAll([x], Implies(Man(x), Mortal(x)))
        socrates_is_man = Man(socrates)
        conclusion = Mortal(socrates)

        claim = Implies(And(all_men_mortal, socrates_is_man), conclusion)
        assert _try_prove(claim)


# ------------------------------------------------------------------
# N-Queens (small)
# ------------------------------------------------------------------


class TestNQueens:
    def test_2queens_unsat(self, kernel):
        """2 queens on a 2x2 board is impossible."""
        q0, q1 = Int("q0"), Int("q1")

        constraints = []
        for q in (q0, q1):
            constraints.append(q >= IntVal(1))
            constraints.append(q <= IntVal(2))

        constraints.append(Distinct(q0, q1))
        constraints.append(q0 - q1 != IntVal(1))
        constraints.append(q0 - q1 != IntVal(-1))

        s = Solver()
        s.add(*constraints)
        assert s.check() == unsat


# ------------------------------------------------------------------
# Bit-vectors
# ------------------------------------------------------------------


class TestBitVec:
    def test_bitvec_var(self):
        x = BitVec("x", 8)
        assert isinstance(x._ast, Var) and x._ast.name == "x"
        assert x.sort() == BitVecSort(8)

    def test_bitvec_val(self):
        v = BitVecVal(42, 8)
        assert isinstance(v._ast, BvLit) and v._ast.val == 42 and v._ast.width == 8

    def test_bitvec_arithmetic(self):
        x, y = BitVecs("x y", 8)
        assert isinstance((x + y)._ast, BinOpNode) and (x + y)._ast.op == BinOp.ADD
        assert isinstance((x - y)._ast, BinOpNode) and (x - y)._ast.op == BinOp.SUB
        assert isinstance((x * y)._ast, BinOpNode) and (x * y)._ast.op == BinOp.MUL
        assert isinstance((-x)._ast, UnOpNode) and (-x)._ast.op == UnOp.NEG

    def test_bitvec_bitwise(self):
        x, y = BitVecs("x y", 8)
        assert isinstance((x & y)._ast, BinOpNode) and (x & y)._ast.op == BinOp.BAND
        assert isinstance((x | y)._ast, BinOpNode) and (x | y)._ast.op == BinOp.BOR
        assert isinstance((x ^ y)._ast, BinOpNode) and (x ^ y)._ast.op == BinOp.BXOR
        assert isinstance((~x)._ast, UnOpNode) and (~x)._ast.op == UnOp.BNOT

    def test_bitvec_shift(self):
        x = BitVec("x", 8)
        assert isinstance((x << 2)._ast, BinOpNode) and (x << 2)._ast.op == BinOp.BSHL
        # >> is arithmetic shift right (z3 convention), BSHR is logical (used by LShR)
        assert isinstance((x >> 1)._ast, BinOpNode) and (x >> 1)._ast.op == BinOp.ASHR

    def test_bitvec_comparison(self):
        x = BitVec("x", 8)
        assert isinstance((x > 5)._ast, BinOpNode) and (x > 5)._ast.op == BinOp.SGT
        eq = x == BitVecVal(0, 8)
        assert isinstance(eq._ast, BinOpNode) and eq._ast.op == BinOp.EQ

    def test_bitvec_coercion(self):
        x = BitVec("x", 8)
        add = x + 1
        assert isinstance(add._ast, BinOpNode) and isinstance(add._ast.rhs, BvLit)
        radd = 1 + x
        assert isinstance(radd._ast, BinOpNode) and isinstance(radd._ast.lhs, BvLit)

    def test_bitvec_or_idempotent(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(ForAll([x], (x | x) == x))

    def test_bitvec_and_self(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(ForAll([x], (x & x) == x))


# ------------------------------------------------------------------
# Arrays (SMT theory)
# ------------------------------------------------------------------


class TestArray:
    def test_array_sort(self):
        s = ArraySort(IntSort(), IntSort())
        assert "\u2192" in repr(s)

    def test_array_var(self):
        a = Array("a", IntSort(), IntSort())
        assert isinstance(a._ast, Var) and a._ast.name == "a"

    def test_select(self):
        a = Array("a", IntSort(), IntSort())
        i = Int("i")
        sel = Select(a, i)
        assert isinstance(sel._ast, SelectNode)

    def test_store(self):
        a = Array("a", IntSort(), IntSort())
        i = Int("i")
        v = Int("v")
        s = Store(a, i, v)
        assert isinstance(s._ast, StoreNode)

    def test_constant_array(self):
        c = K(IntSort(), IntVal(0))
        assert isinstance(c._ast, ConstArrayNode)

    def test_select_store_same_index(self, kernel):
        """Store then Select at the same index gives the written value."""
        a = Array("a", IntSort(), IntSort())
        v = Int("v")
        written = Store(a, IntVal(3), v)
        read_back = Select(written, IntVal(3))
        claim = ForAll([a, v], read_back == v)
        assert _try_prove(claim)

    def test_constant_array_read(self, kernel):
        """Reading from a constant array gives the constant value."""
        i = Int("i")
        c = K(IntSort(), IntVal(42))
        claim = ForAll([i], Select(c, i) == IntVal(42))
        assert _try_prove(claim)


# ------------------------------------------------------------------
# Datatypes
# ------------------------------------------------------------------


class TestDatatype:
    def test_declare_enum(self, kernel):
        Color = Datatype("Color_c1")
        Color.declare("red")
        Color.declare("green")
        Color.declare("blue")
        Color = Color.create()

        assert hasattr(Color, "red")
        assert hasattr(Color, "green")
        assert hasattr(Color, "blue")

    def test_declare_with_fields(self, kernel):
        Pair = Datatype("Pair_c2")
        Pair.declare("mk", ("fst", IntSort()), ("snd", IntSort()))
        Pair = Pair.create()

        assert hasattr(Pair, "mk")
        assert hasattr(Pair, "fst")
        assert hasattr(Pair, "snd")

    def test_enum_expression_building(self, kernel):
        """Enum constructors produce well-formed expressions."""
        Color = Datatype("Color_c3")
        Color.declare("red")
        Color.declare("green")
        Color.declare("blue")
        Color = Color.create()

        expr = Color.red != Color.green
        assert isinstance(expr._ast, BinOpNode) and expr._ast.op == BinOp.NE

    def test_constructor_application(self, kernel):
        Pair = Datatype("Pair_c4")
        Pair.declare("mk", ("fst", IntSort()), ("snd", IntSort()))
        Pair = Pair.create()

        x, y = Ints("x y")
        p = Pair.mk(x, y)
        assert isinstance(p._ast, InductiveCtorNode)


class TestDatatypeStructural:
    """Test that inductive datatypes enable structural proofs."""

    def test_enum_disjointness(self, kernel):
        Color = Datatype('Color_s1')
        Color.declare('red'); Color.declare('green'); Color.declare('blue')
        Color = Color.create()
        assert _try_prove(Color.red != Color.green)

    def test_enum_exhaustiveness(self, kernel):
        Color = Datatype('Color_s2')
        Color.declare('red'); Color.declare('green'); Color.declare('blue')
        Color = Color.create()
        x = Const('x', Color)
        g = Goal()
        g.add(Or(x == Color.red, x == Color.green, x == Color.blue))
        t = Tactic("intro x; cases x <;> simp")
        r = t.apply(g)
        assert len(r) == 0

    def test_constructor_injectivity(self, kernel):
        Pair = Datatype('IntPair_s3')
        Pair.declare('mk_pair', ('fst', IntSort()), ('snd', IntSort()))
        Pair = Pair.create()
        x, y = Ints('x y')
        assert _try_prove(Implies(Pair.mk_pair(x, y) == Pair.mk_pair(IntVal(1), IntVal(2)), And(x == IntVal(1), y == IntVal(2))))

    def test_accessor_projection(self, kernel):
        Pair = Datatype('IntPair_s4')
        Pair.declare('mk', ('fst', IntSort()), ('snd', IntSort()))
        Pair = Pair.create()
        assert _try_prove(Pair.fst(Pair.mk(IntVal(1), IntVal(2))) == IntVal(1))

    def test_recursive_datatype(self, kernel):
        Tree = Datatype('Tree_s5')
        Tree.declare('leaf', ('val', IntSort()))
        Tree.declare('node', ('left', Tree), ('right', Tree))
        Tree = Tree.create()
        t1 = Tree.leaf(IntVal(1))
        t2 = Tree.node(Tree.leaf(IntVal(1)), Tree.leaf(IntVal(2)))
        assert _try_prove(t1 != t2)

    def test_recognizer(self, kernel):
        Color = Datatype('Color_s6')
        Color.declare('red'); Color.declare('green'); Color.declare('blue')
        Color = Color.create()
        assert _try_prove(Color.is_red(Color.red))
        assert _try_prove(Not(Color.is_red(Color.green)))


# ------------------------------------------------------------------
# Bug fixes
# ------------------------------------------------------------------


class TestBugFixes:
    def test_pow_not_mul(self):
        """__pow__ should use POW, not MUL."""
        x = Int("x")
        p = x ** 2
        assert isinstance(p._ast, BinOpNode) and p._ast.op == BinOp.POW

    def test_bool_guard(self):
        """Symbolic expressions should not be castable to bool."""
        x = Int("x")
        with pytest.raises(TypeError, match="Symbolic expressions"):
            bool(x > 0)

    def test_simplify_returns_expr(self):
        """simplify() should return an ExprRef, not a string."""
        x = Int("x")
        result = simplify(x + 1)
        assert isinstance(result, ExprRef)

    def test_solver_empty_sat(self):
        """Empty solver should return sat."""
        s = Solver()
        assert s.check() == sat


# ------------------------------------------------------------------
# Missing operators
# ------------------------------------------------------------------


class TestMissingOperators:
    def test_arith_rtruediv(self):
        x = Int("x")
        r = 10 / x
        # Int uses Euclidean division (SMT-LIB semantics)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.EDIV

    def test_arith_rmod(self):
        x = Int("x")
        r = 10 % x
        # Int uses Euclidean mod (SMT-LIB semantics)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.EMOD

    def test_arith_rpow(self):
        x = Int("x")
        r = 2 ** x
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.POW

    def test_arith_pos(self):
        x = Int("x")
        assert (+x) is x

    def test_arith_abs(self):
        x = Int("x")
        a = abs(x)
        assert isinstance(a._ast, IteNode)

    def test_arith_is_int(self):
        x = Int("x")
        assert x.is_int()
        assert not x.is_real()

    def test_arith_is_real(self):
        x = Real("x")
        assert x.is_real()
        assert not x.is_int()

    def test_bool_xor_operator(self):
        a, b = Bool("a"), Bool("b")
        result = a ^ b
        assert isinstance(result._ast, BinOpNode) and result._ast.op == BinOp.XOR

    def test_bv_rlshift(self):
        x = BitVec("x", 8)
        r = 3 << x
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.BSHL

    def test_bv_rrshift(self):
        x = BitVec("x", 8)
        r = 3 >> x
        # >> is arithmetic shift right (z3 convention)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.ASHR

    def test_bv_size(self):
        x = BitVec("x", 32)
        assert x.size() == 32

    def test_bv_div(self):
        x, y = BitVecs("x y", 8)
        r = x / y
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.SDIV

    def test_bv_mod(self):
        x, y = BitVecs("x y", 8)
        r = x % y
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.SMOD

    def test_array_getitem(self):
        a = Array("a", IntSort(), IntSort())
        i = Int("i")
        sel = a[i]
        assert isinstance(sel._ast, SelectNode)


# ------------------------------------------------------------------
# And/Or list support
# ------------------------------------------------------------------


class TestAndOrList:
    def test_and_list(self):
        a, b, c = Bool("a"), Bool("b"), Bool("c")
        result = And([a, b, c])
        assert isinstance(result._ast, BinOpNode)

    def test_or_list(self):
        a, b = Bool("a"), Bool("b")
        result = Or([a, b])
        assert isinstance(result._ast, BinOpNode) and result._ast.op == BinOp.OR

    def test_and_empty_list(self):
        result = And([])
        assert isinstance(result._ast, BoolLit) and result._ast.val is True

    def test_or_empty_list(self):
        result = Or([])
        assert isinstance(result._ast, BoolLit) and result._ast.val is False


# ------------------------------------------------------------------
# Bitvector functions
# ------------------------------------------------------------------


class TestBitvecFunctions:
    def test_lshr(self):
        x = BitVec("x", 8)
        r = LShR(x, 2)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.BSHR

    def test_ule(self):
        x, y = BitVecs("x y", 8)
        r = ULE(x, y)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.LE

    def test_ult(self):
        x, y = BitVecs("x y", 8)
        r = ULT(x, y)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.LT

    def test_uge(self):
        x, y = BitVecs("x y", 8)
        r = UGE(x, y)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.GE

    def test_ugt(self):
        x, y = BitVecs("x y", 8)
        r = UGT(x, y)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.GT

    def test_udiv(self):
        x, y = BitVecs("x y", 8)
        r = UDiv(x, y)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.DIV

    def test_urem(self):
        x, y = BitVecs("x y", 8)
        r = URem(x, y)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.MOD

    def test_extract(self):
        x = BitVec("x", 8)
        r = Extract(3, 0, x)
        assert isinstance(r._ast, ExtractNode)
        assert r._ast.hi == 3 and r._ast.lo == 0
        assert r.size() == 4

    def test_concat(self):
        a = BitVec("a", 4)
        b = BitVec("b", 4)
        r = Concat(a, b)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.CONCAT
        assert r.size() == 8

    def test_zeroext(self):
        x = BitVec("x", 8)
        r = ZeroExt(8, x)
        assert isinstance(r._ast, ZeroExtNode)
        assert r.size() == 16

    def test_signext(self):
        x = BitVec("x", 8)
        r = SignExt(8, x)
        assert isinstance(r._ast, SignExtNode)
        assert r.size() == 16

    def test_bv2int(self):
        x = BitVec("x", 8)
        r = BV2Int(x)  # default is_signed=False → unsigned (BV2NAT)
        assert isinstance(r._ast, UnOpNode) and r._ast.op == UnOp.BV2NAT
        assert r.sort() == IntSort()
        # is_signed=True → signed (BV2INT)
        r2 = BV2Int(x, is_signed=True)
        assert isinstance(r2._ast, UnOpNode) and r2._ast.op == UnOp.BV2INT

    def test_int2bv(self):
        x = Int("x")
        r = Int2BV(x, 8)
        assert r.size() == 8


# ------------------------------------------------------------------
# Arithmetic functions
# ------------------------------------------------------------------


class TestArithFunctions:
    def test_abs_function(self):
        x = Int("x")
        r = Abs(x)
        assert isinstance(r._ast, IteNode)

    def test_toreal(self):
        x = Int("x")
        r = ToReal(x)
        assert isinstance(r._ast, ToRealNode)
        assert r.sort() == RealSort()

    def test_toint(self):
        x = Real("x")
        r = ToInt(x)
        assert isinstance(r._ast, ToIntNode)
        assert r.sort() == IntSort()

    def test_sum(self):
        x, y, z = Ints("x y z")
        r = Sum(x, y, z)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.ADD

    def test_sum_list(self):
        x, y = Ints("x y")
        r = Sum([x, y])
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.ADD

    def test_sum_empty(self):
        r = Sum()
        assert isinstance(r._ast, IntLit) and r._ast.val == 0

    def test_product(self):
        x, y = Ints("x y")
        r = Product(x, y)
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.MUL

    def test_product_empty(self):
        r = Product()
        assert isinstance(r._ast, IntLit) and r._ast.val == 1


# ------------------------------------------------------------------
# Predicates
# ------------------------------------------------------------------


class TestPredicates:
    def test_is_expr(self):
        assert is_expr(Int("x"))
        assert not is_expr(42)

    def test_is_true_false(self):
        assert is_true(BoolVal(True))
        assert is_false(BoolVal(False))
        assert not is_true(BoolVal(False))
        assert not is_false(BoolVal(True))

    def test_is_int(self):
        assert is_int(Int("x"))
        assert not is_int(Real("x"))

    def test_is_real(self):
        assert is_real(Real("x"))
        assert not is_real(Int("x"))

    def test_is_bool(self):
        assert is_bool(Bool("a"))
        assert not is_bool(Int("x"))

    def test_is_bv(self):
        assert is_bv(BitVec("x", 8))
        assert not is_bv(Int("x"))

    def test_is_array(self):
        a = Array("a", IntSort(), IntSort())
        assert is_array(a)
        assert not is_array(Int("x"))

    def test_is_const_var(self):
        assert is_const(Int("x"))
        assert is_var(Int("x"))
        x, y = Ints("x y")
        assert not is_const(x + y)

    def test_is_quantifier(self):
        x = Int("x")
        assert is_quantifier(ForAll([x], x > 0))
        assert not is_quantifier(x > 0)

    def test_is_eq(self):
        x, y = Ints("x y")
        assert is_eq(x == y)
        assert not is_eq(x > y)

    def test_is_distinct(self):
        x, y = Ints("x y")
        assert is_distinct(Distinct(x, y))

    def test_is_and_or_not(self):
        a, b = Bool("a"), Bool("b")
        assert is_and(And(a, b))
        assert is_or(Or(a, b))
        assert is_not(Not(a))

    def test_is_implies(self):
        a, b = Bool("a"), Bool("b")
        assert is_implies(Implies(a, b))

    def test_is_arithmetic_ops(self):
        x, y = Ints("x y")
        assert is_add(x + y)
        assert is_mul(x * y)
        assert is_sub(x - y)
        assert is_div(x / y)


# ------------------------------------------------------------------
# Lambda
# ------------------------------------------------------------------


class TestLambda:
    def test_lambda_single_var(self):
        x = Int("x")
        lam = Lambda(x, x + 1)
        assert isinstance(lam._ast, LambdaNode)
        assert lam._ast.name == "x"

    def test_lambda_multi_var(self):
        x, y = Ints("x y")
        lam = Lambda([x, y], x + y)
        assert isinstance(lam._ast, LambdaNode)
        # Nested: outer is x, inner is y
        assert lam._ast.name == "x"
        assert isinstance(lam._ast.body, LambdaNode)
        assert lam._ast.body.name == "y"

    def test_lambda_free_vars(self):
        x, y = Ints("x y")
        lam = Lambda(x, x + y)
        # x is bound, y is free
        names = {n for n, _ in lam._vars}
        assert "x" not in names
        assert "y" in names


# ------------------------------------------------------------------
# New feature proofs (require kernel)
# ------------------------------------------------------------------


class TestNewFeatureProofs:
    def test_pow_proof(self, kernel):
        """x^1 is not provable as x via grind generally, but 2^3 = 8 is."""
        # Concrete: 2^3 = 8
        claim = IntVal(2) ** 3 == IntVal(8)
        assert _try_prove(claim)

    def test_abs_nonneg(self, kernel):
        """abs(x) >= 0 for all x."""
        x = Int("x")
        a = Abs(x)
        claim = ForAll([x], a >= 0)
        assert _try_prove(claim)

    def test_empty_solver_sat(self, kernel):
        """Empty solver returns sat."""
        s = Solver()
        assert s.check() == sat

    def test_bv_concat_size(self, kernel):
        """Concat preserves correct width (4+4=8)."""
        a = BitVec("a", 4)
        b = BitVec("b", 4)
        c = Concat(a, b)
        assert c.size() == 8

    def test_sum_proof(self, kernel):
        """Sum(x, y) == x + y."""
        x, y = Ints("x y")
        claim = ForAll([x, y], Sum(x, y) == x + y)
        assert _try_prove(claim)

    def test_product_proof(self, kernel):
        """Product(x, y) == x * y."""
        x, y = Ints("x y")
        claim = ForAll([x, y], Product(x, y) == x * y)
        assert _try_prove(claim)

    def test_lshr_differs_from_rshift(self, kernel):
        """LShR (logical) and >> (arithmetic) are different operations."""
        x = BitVec("x", 8)
        assert LShR(x, 2)._ast.op == BinOp.BSHR  # logical
        assert (x >> 2)._ast.op == BinOp.ASHR  # arithmetic


# ===================================================================
# NEW FEATURE TESTS (7 gaps)
# ===================================================================


class TestBVSignedRotation:
    """Tests for BV signed/rotation ops (gap #1)."""

    def test_rotate_left_ast(self):
        x = BitVec("x", 8)
        r = RotateLeft(x, 3)
        assert isinstance(r, BitVecRef)
        assert isinstance(r._ast, BinOpNode)
        assert r._ast.op == BinOp.ROTL

    def test_rotate_right_ast(self):
        x = BitVec("x", 8)
        r = RotateRight(x, 3)
        assert isinstance(r._ast, BinOpNode)
        assert r._ast.op == BinOp.ROTR

    def test_sdiv_ast(self):
        x = BitVec("x", 8)
        r = SDiv(x, 2)
        assert isinstance(r._ast, BinOpNode)
        assert r._ast.op == BinOp.SDIV

    def test_srem_ast(self):
        x = BitVec("x", 8)
        r = SRem(x, 2)
        assert isinstance(r._ast, BinOpNode)
        assert r._ast.op == BinOp.SREM

    def test_ashr_ast(self):
        x = BitVec("x", 8)
        r = AShr(x, 2)
        assert isinstance(r._ast, BinOpNode)
        assert r._ast.op == BinOp.ASHR

    def test_rotate_left_width_preserved(self):
        x = BitVec("x", 16)
        r = RotateLeft(x, 5)
        assert r.size() == 16

    def test_sdiv_with_bv_operand(self):
        x = BitVec("x", 8)
        y = BitVec("y", 8)
        r = SDiv(x, y)
        assert r.size() == 8

    def test_rotate_left_proof(self, kernel):
        """rotateLeft(x, 0) == x for 8-bit."""
        x = BitVec("x", 8)
        claim = ForAll(x, RotateLeft(x, 0) == x)
        assert _try_prove(claim)

    def test_rotate_right_proof(self, kernel):
        """rotateRight(x, 0) == x for 8-bit."""
        x = BitVec("x", 8)
        claim = ForAll(x, RotateRight(x, 0) == x)
        assert _try_prove(claim)


class TestBVSignedSemantics:
    """Verify signed vs unsigned BV semantics."""

    def test_signed_lt_operator(self, kernel):
        """0xFF as 8-bit signed is -1; signed -1 < 1 should prove."""
        s = Solver()
        s.add(Not(BitVecVal(0xFF, 8) < BitVecVal(0x01, 8)))
        assert s.check() == unsat  # signed: -1 < 1 is true

    def test_unsigned_lt(self, kernel):
        """Unsigned 255 < 1 should NOT prove (it's false)."""
        s = Solver()
        s.add(Not(ULT(BitVecVal(0xFF, 8), BitVecVal(0x01, 8))))
        assert s.check() != unsat  # unsigned: 255 < 1 is false

    def test_signed_le_operator(self, kernel):
        """Signed -1 <= 0 should prove."""
        s = Solver()
        s.add(Not(BitVecVal(0xFF, 8) <= BitVecVal(0x00, 8)))
        assert s.check() == unsat

    def test_unsigned_le(self, kernel):
        """Unsigned 255 <= 0 should NOT prove."""
        s = Solver()
        s.add(Not(ULE(BitVecVal(0xFF, 8), BitVecVal(0x00, 8))))
        assert s.check() != unsat

    def test_signed_gt_operator(self, kernel):
        """Signed 1 > -1 should prove."""
        s = Solver()
        s.add(Not(BitVecVal(0x01, 8) > BitVecVal(0xFF, 8)))
        assert s.check() == unsat

    def test_signed_ge_operator(self, kernel):
        """Signed 0 >= -1 should prove."""
        s = Solver()
        s.add(Not(BitVecVal(0x00, 8) >= BitVecVal(0xFF, 8)))
        assert s.check() == unsat

    def test_signed_div_operator(self, kernel):
        """Signed -4 / 2 == -2 for 8-bit."""
        # -4 as 8-bit = 0xFC, -2 as 8-bit = 0xFE
        s = Solver()
        s.add(Not(BitVecVal(0xFC, 8) / BitVecVal(2, 8) == BitVecVal(0xFE, 8)))
        assert s.check() == unsat

    def test_unsigned_div(self, kernel):
        """Unsigned 0xFC / 2 == 0x7E (= 126)."""
        s = Solver()
        s.add(Not(UDiv(BitVecVal(0xFC, 8), BitVecVal(2, 8)) == BitVecVal(0x7E, 8)))
        assert s.check() == unsat

    def test_concat_varargs(self):
        """Concat with 3+ arguments left-folds correctly."""
        a = BitVec("a", 4)
        b = BitVec("b", 4)
        c = BitVec("c", 4)
        result = Concat(a, b, c)
        assert result.size() == 12


class TestModelRef:
    """Tests for ModelRef stub (gap #2)."""

    def test_model_raises(self):
        s = Solver()
        with pytest.raises(NotImplementedError, match="not supported"):
            s.model()

    def test_model_ref_getitem_raises(self):
        m = ModelRef()
        with pytest.raises(NotImplementedError):
            m[0]

    def test_model_ref_repr(self):
        m = ModelRef()
        assert "unsupported" in repr(m)


class TestTacticGoal:
    """Tests for Tactic/Goal system (gap #3)."""

    def test_goal_add_and_len(self):
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
        x = Int("x")
        g.add(x > 0, x < 10)
        expr = g.as_expr()
        assert isinstance(expr._ast, BinOpNode)
        assert expr._ast.op == BinOp.AND

    def test_apply_result_empty_proved(self):
        r = ApplyResult([])
        assert len(r) == 0
        from lean_py.z3.core import BoolLit as BoolLitCls
        assert r.as_expr()._ast == BoolLit(True)

    def test_tactic_solve_trivial(self, kernel):
        """Tactic('decide') can solve True."""
        g = Goal()
        from lean_py.z3 import BoolVal
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
        t = Repeat(Tactic("simp"), max=5)
        assert isinstance(t, Tactic)


class TestStringSort:
    """Tests for String/Sequence support (gap #4a)."""

    def test_string_sort(self):
        s = StringSort()
        assert isinstance(s, StringSortRef)
        assert repr(s) == "String"

    def test_string_var(self):
        s = String("s")
        assert isinstance(s, StringRef)
        assert is_string(s)

    def test_strings(self):
        a, b = Strings("a b")
        assert isinstance(a, StringRef)
        assert isinstance(b, StringRef)

    def test_string_val(self):
        s = StringVal("hello")
        assert is_string_value(s)
        assert isinstance(s._ast, StringLit)
        assert s._ast.val == "hello"

    def test_string_concat(self):
        a = StringVal("hello")
        b = StringVal(" world")
        c = a + b
        assert isinstance(c, StringRef)
        assert isinstance(c._ast, StrConcatNode)

    def test_length(self):
        s = String("s")
        l = Length(s)
        assert is_int(l)
        assert isinstance(l._ast, StrLenNode)

    def test_contains(self):
        s = String("s")
        t = StringVal("abc")
        c = Contains(s, t)
        assert isinstance(c._ast, StrContainsNode)

    def test_prefix_of(self):
        s = String("s")
        t = StringVal("pre")
        p = PrefixOf(t, s)
        assert isinstance(p, ExprRef)

    def test_suffix_of(self):
        s = String("s")
        t = StringVal("suf")
        p = SuffixOf(t, s)
        assert isinstance(p, ExprRef)

    def test_replace(self):
        s = String("s")
        r = Replace(s, StringVal("a"), StringVal("b"))
        assert isinstance(r, StringRef)

    def test_substring(self):
        s = String("s")
        sub = SubString(s, 1, 3)
        assert isinstance(sub, StringRef)

    def test_indexof(self):
        s = String("s")
        idx = IndexOf(s, StringVal("x"))
        assert is_int(idx)

    def test_str_to_int(self):
        s = StringVal("42")
        i = StrToInt(s)
        assert is_int(i)

    def test_int_to_str(self):
        i = IntVal(42)
        s = IntToStr(i)
        assert isinstance(s, StringRef)

    def test_str_concat_variadic(self):
        a = StringVal("a")
        b = StringVal("b")
        c = StringVal("c")
        r = StrConcat(a, b, c)
        assert isinstance(r, StringRef)

    def test_str_concat_empty(self):
        r = StrConcat()
        assert is_string_value(r)

    def test_string_free_vars(self):
        s = String("s")
        t = String("t")
        expr = Contains(s, t)
        assert len(expr._vars) == 2

    def test_const_with_string_sort(self):
        s = Const("s", StringSort())
        assert isinstance(s, StringRef)


class TestRegex:
    """Tests for Regex support (gap #4b)."""

    def test_re_from_string(self):
        s = StringVal("abc")
        r = Re(s)
        assert isinstance(r, ExprRef)

    def test_star(self):
        r = Star(Re(StringVal("a")))
        assert isinstance(r._ast, ReStarNode)

    def test_plus(self):
        r = Plus(Re(StringVal("a")))
        assert isinstance(r, ExprRef)

    def test_option(self):
        r = Option(Re(StringVal("a")))
        assert isinstance(r, ExprRef)

    def test_union(self):
        a = Re(StringVal("a"))
        b = Re(StringVal("b"))
        r = Union(a, b)
        assert isinstance(r, ExprRef)

    def test_intersect(self):
        a = Re(StringVal("a"))
        b = Re(StringVal("b"))
        r = Intersect(a, b)
        assert isinstance(r, ExprRef)

    def test_complement(self):
        r = Complement(Re(StringVal("a")))
        assert isinstance(r, ExprRef)

    def test_range(self):
        r = Range("a", "z")
        assert isinstance(r, ExprRef)

    def test_loop(self):
        r = Loop(Re(StringVal("a")), 2, 5)
        assert isinstance(r, ExprRef)

    def test_in_re(self):
        s = String("s")
        r = Star(Re(StringVal("a")))
        result = InRe(s, r)
        assert isinstance(result._ast, InReNode)

    def test_allchar(self):
        r = AllChar()
        assert isinstance(r, ExprRef)


class TestRatVal:
    """Tests for RatVal/Q (gap #5)."""

    def test_ratval_creates_division(self):
        r = RatVal(1, 3)
        assert isinstance(r._ast, BinOpNode)
        assert r._ast.op == BinOp.DIV

    def test_q_alias(self):
        assert Q is RatVal

    def test_ratval_sort(self):
        r = RatVal(1, 2)
        assert is_real(r)

    def test_ratval_components(self):
        r = RatVal(3, 7)
        assert r.numerator_as_long() == 3
        assert r.denominator_as_long() == 7


class TestFreshConst:
    """Tests for FreshConst/FreshInt/FreshBool/FreshReal (gap #6)."""

    def test_fresh_int(self):
        a = FreshInt()
        b = FreshInt()
        assert a._ast.name != b._ast.name

    def test_fresh_bool(self):
        a = FreshBool()
        assert isinstance(a, ExprRef)
        assert is_bool(a)

    def test_fresh_real(self):
        a = FreshReal()
        assert is_real(a)

    def test_fresh_const_prefix(self):
        a = FreshConst(IntSort(), prefix="myvar")
        assert a._ast.name.startswith("myvar!")

    def test_fresh_const_unique(self):
        a = FreshConst(IntSort())
        b = FreshConst(IntSort())
        assert a._ast.name != b._ast.name

    def test_fresh_const_is_var(self):
        a = FreshInt()
        assert is_var(a)
        assert is_const(a)


class TestMapAsArray:
    """Tests for Map/AsArray (gap #7)."""

    def test_map_basic(self):
        f = Function("f", IntSort(), IntSort())
        a = Array("a", IntSort(), IntSort())
        result = Map(f, a)
        assert is_array(result)

    def test_map_requires_array(self):
        f = Function("f", IntSort(), IntSort())
        with pytest.raises(TypeError):
            Map(f)

    def test_as_array_basic(self):
        f = Function("f", IntSort(), IntSort())
        a = AsArray(f)
        assert is_array(a)

    def test_as_array_requires_unary(self):
        f = Function("f", IntSort(), IntSort(), IntSort())
        with pytest.raises(TypeError):
            AsArray(f)

    def test_map_sort(self):
        f = Function("f", IntSort(), IntSort())
        a = Array("a", IntSort(), IntSort())
        result = Map(f, a)
        from lean_py.z3 import ArraySortRef
        assert isinstance(result._sort, ArraySortRef)


# ------------------------------------------------------------------
# Floating-point support
# ------------------------------------------------------------------


class TestFPSupport:
    """Floating-point compilation and ground proofs."""

    def test_fp_sort(self):
        s = Float64()
        assert s.ebits() == 11
        assert s.sbits() == 53

    def test_fpval_construction(self):
        v = FPVal(1.5)
        assert isinstance(v, FPNumRef)
        assert not v.isNaN()
        assert not v.isInf()

    def test_fp_nan(self):
        v = fpNaN(Float64())
        assert v.isNaN()

    def test_fp_infinity(self):
        v = fpPlusInfinity(Float64())
        assert v.isInf()

    def test_fpval_ast_is_fplit(self):
        v = FPVal(3.14)
        assert isinstance(v._ast, FpLitNode)

    def test_fp_add_ground(self, kernel):
        """1.0 + 2.0 == 3.0 (ground proof via native_decide)."""
        claim = fpEQ(fpAdd(RNE(), FPVal(1.0), FPVal(2.0)), FPVal(3.0))
        assert _try_prove(claim)

    def test_fp_mul_ground(self, kernel):
        """2.0 * 3.0 == 6.0."""
        claim = fpEQ(fpMul(RNE(), FPVal(2.0), FPVal(3.0)), FPVal(6.0))
        assert _try_prove(claim)

    def test_fp_neg_ground(self, kernel):
        """-1.0 < 0.0."""
        claim = fpLT(fpNeg(FPVal(1.0)), FPVal(0.0))
        assert _try_prove(claim)

    def test_fp_comparison_ground(self, kernel):
        """1.0 < 2.0."""
        claim = fpLT(FPVal(1.0), FPVal(2.0))
        assert _try_prove(claim)

    def test_fp_nan_not_equal_self(self, kernel):
        """NaN != NaN (IEEE semantics)."""
        nan = fpNaN(Float64())
        s = Solver()
        s.add(fpEQ(nan, nan))
        assert s.check() != sat


# ------------------------------------------------------------------
# String end-to-end proofs
# ------------------------------------------------------------------


class TestStringProofs:
    """String operations proven through Lean (not just AST construction)."""

    def test_prefix_of_ground(self, kernel):
        """'ab' is a prefix of 'abc'."""
        claim = PrefixOf(StringVal("ab"), StringVal("abc"))
        assert _try_prove(claim)

    def test_suffix_of_ground(self, kernel):
        """'bc' is a suffix of 'abc'."""
        claim = SuffixOf(StringVal("bc"), StringVal("abc"))
        assert _try_prove(claim)

    def test_contains_ground(self, kernel):
        """'abc' contains 'bc'."""
        claim = Contains(StringVal("abc"), StringVal("bc"))
        assert _try_prove(claim)

    def test_string_length_ground(self, kernel):
        """len('hello') == len('world')."""
        claim = Length(StringVal("hello")) == Length(StringVal("world"))
        assert _try_prove(claim)

    def test_string_concat_ground(self, kernel):
        """'ab' ++ 'cd' == 'abcd'."""
        claim = StrConcat(StringVal("ab"), StringVal("cd")) == StringVal("abcd")
        assert _try_prove(claim)


# ------------------------------------------------------------------
# Rational number proofs
# ------------------------------------------------------------------


class TestRationalProofs:
    """Rational arithmetic proven through Lean."""

    def test_rat_add_ground(self, kernel):
        """1/3 + 2/3 == 1/1."""
        claim = Q(1, 3) + Q(2, 3) == Q(1, 1)
        assert _try_prove(claim)

    def test_rat_mul_ground(self, kernel):
        """1/2 * 2/3 == 1/3."""
        claim = Q(1, 2) * Q(2, 3) == Q(1, 3)
        assert _try_prove(claim)


# ------------------------------------------------------------------
# Negative tests (unprovable claims should NOT succeed)
# ------------------------------------------------------------------


class TestNegative:
    """Verify that unprovable/false claims correctly return False/unknown."""

    def test_false_not_provable(self, kernel):
        """False itself is not provable."""
        assert not _try_prove(BoolVal(False))

    def test_contradiction_not_provable(self, kernel):
        """x > 0 ∧ x < 0 is not provable."""
        x = Int("x")
        claim = And(x > 0, x < 0)
        assert not _try_prove(claim)

    def test_wrong_arithmetic(self, kernel):
        """1 + 1 == 3 is not provable."""
        claim = IntVal(1) + IntVal(1) == IntVal(3)
        assert not _try_prove(claim)

    def test_solver_sat_when_satisfiable(self, kernel):
        """A satisfiable system should not return unsat."""
        x = Int("x")
        s = Solver()
        s.add(x > 0)
        assert s.check() != unsat


# ------------------------------------------------------------------
# Coercion edge cases
# ------------------------------------------------------------------


class TestCoercionEdgeCases:
    """Test coercion of Python literals to z3 expressions."""

    def test_bv_negative_coercion(self):
        """BitVec + (-1) should produce two's complement."""
        from lean_py.z3._ast import BvLit
        bv = BitVec("x", 8)
        result = bv + (-1)
        # The -1 coerced to BvLit should be 255 (two's complement for 8-bit)
        rhs = result._ast.rhs
        assert isinstance(rhs, BvLit)
        assert rhs.val == 255
        assert rhs.width == 8

    def test_bv_negative_coercion_16bit(self):
        """BitVec + (-1) on 16-bit should be 65535."""
        from lean_py.z3._ast import BvLit
        bv = BitVec("x", 16)
        result = bv + (-1)
        rhs = result._ast.rhs
        assert isinstance(rhs, BvLit)
        assert rhs.val == 65535

    def test_real_float_coercion(self):
        """Real + 3.14 should not truncate to 3."""
        x = Real("x")
        result = x + 3.14
        # The AST should NOT have IntLit(3) — it should be a rational
        from lean_py.z3._ast import BinOpNode, IntLit
        assert isinstance(result._ast, BinOpNode)
        rhs = result._ast.rhs
        # rhs should NOT be IntLit(3)
        assert not (isinstance(rhs, IntLit) and rhs.val == 3)

    def test_real_float_half(self):
        """Real + 0.5 should be representable as 1/2."""
        x = Real("x")
        result = x + 0.5
        from lean_py.z3._ast import BinOpNode, ToRealNode
        assert isinstance(result._ast, BinOpNode)
        rhs = result._ast.rhs
        # Should be a division of ToReal nodes (rational representation)
        assert isinstance(rhs, BinOpNode)

    def test_bv_add_negative_ground(self, kernel):
        """BitVecVal(3, 8) + (-1) == BitVecVal(2, 8) (proven)."""
        claim = BitVecVal(3, 8) + BitVecVal(255, 8) == BitVecVal(2, 8)
        assert _try_prove(claim)


# ------------------------------------------------------------------
# Array extensionality
# ------------------------------------------------------------------


class TestArrayProofs:
    """Array operations proven through Lean."""

    def test_store_select_ground(self, kernel):
        """Store(a, i, v)[i] == v."""
        a = Array("a", IntSort(), IntSort())
        i = Int("i")
        v = Int("v")
        claim = Select(Store(a, i, v), i) == v
        assert _try_prove(claim)

    def test_store_select_different_index(self, kernel):
        """Store(a, i, v)[j] == a[j] when i != j."""
        a = Array("a", IntSort(), IntSort())
        i, j, v = Ints("i j v")
        claim = Implies(i != j, Select(Store(a, i, v), j) == Select(a, j))
        assert _try_prove(claim)


# ------------------------------------------------------------------
# Mixed-sort operations
# ------------------------------------------------------------------


class TestMixedSortProofs:
    """Cross-sort conversions proven through Lean."""

    def test_bv_to_int_ground(self, kernel):
        """BV2Int(BitVecVal(42, 8)) == 42."""
        claim = BV2Int(BitVecVal(42, 8)) == IntVal(42)
        assert _try_prove(claim)

    def test_int_to_real_ground(self, kernel):
        """ToReal(3) == ToReal(3)."""
        claim = ToReal(IntVal(3)) == ToReal(IntVal(3))
        assert _try_prove(claim)


# ------------------------------------------------------------------
# Bug fix tests
# ------------------------------------------------------------------


class TestBugFixes:
    """Tests for specific bug fixes."""

    def test_inttostr_negative(self, kernel):
        """IntToStr(-5) should return empty string per SMT-LIB spec."""
        claim = IntToStr(IntVal(-5)) == StringVal("")
        assert _try_prove(claim)

    def test_bv_add_no_overflow_unsigned(self, kernel):
        """BVAddNoOverflow unsigned: 200 + 100 overflows 8-bit."""
        from lean_py.z3 import BVAddNoOverflow

        a = BitVecVal(200, 8)
        b = BitVecVal(100, 8)
        # 200 + 100 = 300 > 255, so no-overflow should be False
        overflow_check = Not(BVAddNoOverflow(a, b, signed=False))
        assert _try_prove(overflow_check)

    def test_bv_mul_no_overflow_unsigned(self, kernel):
        """BVMulNoOverflow unsigned: 200 * 2 overflows 8-bit."""
        from lean_py.z3 import BVMulNoOverflow

        a = BitVecVal(200, 8)
        b = BitVecVal(2, 8)
        # 200 * 2 = 400 > 255, so no-overflow should be False
        overflow_check = Not(BVMulNoOverflow(a, b, signed=False))
        assert _try_prove(overflow_check)

    def test_fp_is_positive_zero(self, kernel):
        """fpIsPositive(+0.0) should be True."""
        from lean_py.z3 import fpIsPositive

        claim = fpIsPositive(FPVal(0.0, Float64()))
        assert _try_prove(claim)

    def test_fp_is_negative_neg_zero(self, kernel):
        """fpIsNegative(-0.0) should be True."""
        from lean_py.z3 import fpIsNegative

        claim = fpIsNegative(FPVal(-0.0, Float64()))
        assert _try_prove(claim)


# ------------------------------------------------------------------
# Char tests
# ------------------------------------------------------------------


class TestChar:
    """Tests for Char sort and operations."""

    def test_char_sort_creation(self):
        """CharSort() creates the char sort."""
        from lean_py.z3 import CharSort, CharSortRef

        s = CharSort()
        assert isinstance(s, CharSortRef)

    def test_char_val_from_str(self):
        """CharVal creates a char literal from string."""
        from lean_py.z3 import CharVal, CharRef

        c = CharVal("A")
        assert isinstance(c, CharRef)

    def test_char_val_from_int(self):
        """CharVal creates a char literal from int."""
        from lean_py.z3 import CharVal, CharRef

        c = CharVal(65)
        assert isinstance(c, CharRef)

    def test_char_to_int(self):
        """CharToInt returns ArithRef."""
        from lean_py.z3 import CharVal, CharToInt

        from lean_py.z3.core import ArithRef

        c = CharVal("A")
        i = CharToInt(c)
        assert isinstance(i, ArithRef)

    def test_char_to_bv(self):
        """CharToBv returns BitVecRef."""
        from lean_py.z3 import CharVal, CharToBv

        c = CharVal("A")
        bv = CharToBv(c)
        assert isinstance(bv, BitVecRef)

    def test_char_is_digit(self):
        """CharIsDigit returns BoolRef."""
        from lean_py.z3 import CharVal, CharIsDigit
        from lean_py.z3.core import BoolRef

        c = CharVal("5")
        d = CharIsDigit(c)
        assert isinstance(d, BoolRef)

    def test_char_to_int_semantic(self, kernel):
        """CharToInt(CharVal('A')) == 65."""
        from lean_py.z3 import CharVal, CharToInt

        claim = CharToInt(CharVal("A")) == IntVal(65)
        assert _try_prove(claim)

    def test_char_const(self):
        """Const with CharSort creates CharRef."""
        from lean_py.z3 import CharSort, CharRef

        c = Const("c", CharSort())
        assert isinstance(c, CharRef)


# ------------------------------------------------------------------
# Set tests
# ------------------------------------------------------------------


class TestSets:
    """Tests for Set sort and operations."""

    def test_set_sort_creation(self):
        """SetSort creates ArraySortRef."""
        from lean_py.z3 import SetSort, ArraySortRef

        s = SetSort(IntSort())
        assert isinstance(s, ArraySortRef)

    def test_empty_set(self):
        """EmptySet creates an array expression."""
        from lean_py.z3 import EmptySet, ArrayRef

        s = EmptySet(IntSort())
        assert isinstance(s, ArrayRef)

    def test_full_set(self):
        """FullSet creates an array expression."""
        from lean_py.z3 import FullSet, ArrayRef

        s = FullSet(IntSort())
        assert isinstance(s, ArrayRef)

    def test_set_add(self):
        """SetAdd adds element to set."""
        from lean_py.z3 import SetAdd, EmptySet, ArrayRef

        s = SetAdd(EmptySet(IntSort()), IntVal(1))
        assert isinstance(s, ArrayRef)

    def test_is_member(self):
        """IsMember tests membership."""
        from lean_py.z3 import IsMember, SetAdd, EmptySet, BoolRef

        s = SetAdd(EmptySet(IntSort()), IntVal(1))
        m = IsMember(IntVal(1), s)
        assert isinstance(m, BoolRef)

    def test_is_member_semantic(self, kernel):
        """IsMember(1, SetAdd(EmptySet, 1)) is provable."""
        from lean_py.z3 import IsMember, SetAdd, EmptySet

        claim = IsMember(IntVal(1), SetAdd(EmptySet(IntSort()), IntVal(1)))
        assert _try_prove(claim)

    def test_set_union(self):
        """SetUnion creates an array expression."""
        from lean_py.z3 import SetUnion, EmptySet, SetAdd, ArrayRef

        a = SetAdd(EmptySet(IntSort()), IntVal(1))
        b = SetAdd(EmptySet(IntSort()), IntVal(2))
        u = SetUnion(a, b)
        assert isinstance(u, ExprRef)

    def test_set_intersect(self):
        """SetIntersect creates an array expression."""
        from lean_py.z3 import SetIntersect, EmptySet, SetAdd

        a = SetAdd(EmptySet(IntSort()), IntVal(1))
        b = SetAdd(EmptySet(IntSort()), IntVal(1))
        i = SetIntersect(a, b)
        assert isinstance(i, ExprRef)

    def test_set_complement(self):
        """SetComplement creates an array expression."""
        from lean_py.z3 import SetComplement, EmptySet

        s = SetComplement(EmptySet(IntSort()))
        assert isinstance(s, ExprRef)

    def test_set_difference(self):
        """SetDifference creates an array expression."""
        from lean_py.z3 import SetDifference, EmptySet, SetAdd

        a = SetAdd(EmptySet(IntSort()), IntVal(1))
        b = EmptySet(IntSort())
        d = SetDifference(a, b)
        assert isinstance(d, ExprRef)

    def test_is_subset(self):
        """IsSubset creates a BoolRef."""
        from lean_py.z3 import IsSubset, EmptySet, SetAdd, BoolRef

        a = EmptySet(IntSort())
        b = SetAdd(EmptySet(IntSort()), IntVal(1))
        s = IsSubset(a, b)
        assert isinstance(s, BoolRef)


# ------------------------------------------------------------------
# Sequence tests
# ------------------------------------------------------------------


class TestSequences:
    """Tests for Sequence sort and operations."""

    def test_seq_sort_creation(self):
        """SeqSort creates a SeqSortRef."""
        from lean_py.z3 import SeqSort, SeqSortRef

        s = SeqSort(IntSort())
        assert isinstance(s, SeqSortRef)

    def test_seq_sort_char_is_string(self):
        """SeqSort(CharSort()) returns StringSort."""
        from lean_py.z3 import SeqSort, CharSort

        s = SeqSort(CharSort())
        assert isinstance(s, StringSortRef)

    def test_empty_seq(self):
        """Empty(SeqSort) creates a SeqRef."""
        from lean_py.z3 import SeqSort, SeqRef, Empty

        s = SeqSort(IntSort())
        e = Empty(s)
        assert isinstance(e, SeqRef)

    def test_unit_seq(self):
        """Unit creates a SeqRef from a non-string element."""
        from lean_py.z3 import Unit, SeqRef

        u = Unit(IntVal(42))
        assert isinstance(u, SeqRef)

    def test_seq_concat(self):
        """Sequence concatenation via + operator."""
        from lean_py.z3 import SeqSort, SeqRef, Empty, Unit

        s1 = Unit(IntVal(1))
        s2 = Unit(IntVal(2))
        assert isinstance(s1, SeqRef)
        assert isinstance(s2, SeqRef)
        s3 = s1 + s2
        assert isinstance(s3, SeqRef)

    def test_seq_length(self):
        """Length works on SeqRef."""
        from lean_py.z3 import Unit, SeqRef
        from lean_py.z3.core import ArithRef

        s = Unit(IntVal(42))
        l = Length(s)
        assert isinstance(l, ArithRef)

    def test_seq_contains(self):
        """Contains works on SeqRef."""
        from lean_py.z3 import Unit, SeqRef, BoolRef

        s = Unit(IntVal(1))
        t = Unit(IntVal(1))
        c = Contains(s, t)
        assert isinstance(c, BoolRef)

    def test_seq_prefix_of(self):
        """PrefixOf works on SeqRef."""
        from lean_py.z3 import Unit, SeqRef, BoolRef

        s = Unit(IntVal(1))
        t = Unit(IntVal(1))
        p = PrefixOf(s, t)
        assert isinstance(p, BoolRef)

    def test_seq_suffix_of(self):
        """SuffixOf works on SeqRef."""
        from lean_py.z3 import Unit, SeqRef, BoolRef

        s = Unit(IntVal(1))
        t = Unit(IntVal(1))
        su = SuffixOf(s, t)
        assert isinstance(su, BoolRef)

    def test_seq_const(self):
        """Const with SeqSort creates SeqRef."""
        from lean_py.z3 import SeqSort, SeqRef

        s = Const("s", SeqSort(IntSort()))
        assert isinstance(s, SeqRef)
