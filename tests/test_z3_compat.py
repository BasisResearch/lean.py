"""z3py compatibility layer tests.

Uses the existing TestLib fixture to avoid managed-project builds in CI.
Exercises the expression AST, solver, prove(), and convenience functions.
"""

from __future__ import annotations

import pytest

from lean_py.kernel import Kernel
from lean_py.z3 import (
    Abs,
    And,
    Array,
    ArraySort,
    BV2Int,
    BitVec,
    BitVecRef,
    BitVecSort,
    BitVecVal,
    BitVecs,
    Bool,
    BoolSort,
    BoolVal,
    Concat,
    Const,
    Consts,
    Datatype,
    DeclareSort,
    Distinct,
    Exists,
    ExprRef,
    Extract,
    ForAll,
    Function,
    If,
    Implies,
    Int,
    Int2BV,
    IntSort,
    IntVal,
    Ints,
    K,
    LShR,
    Lambda,
    Nat,
    NatSort,
    NatVal,
    Not,
    Or,
    Product,
    Real,
    RealSort,
    Select,
    SignExt,
    Solver,
    Store,
    Sum,
    ToInt,
    ToReal,
    UDiv,
    UGE,
    UGT,
    ULE,
    ULT,
    URem,
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
    is_sub,
    is_true,
    is_var,
    sat,
    set_kernel,
    simplify,
    unknown,
    unsat,
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
    IntASTSort,
    IntLit,
    IteNode,
    LambdaNode,
    NatLit,
    PropSort,
    SelectNode,
    SignExtNode,
    StoreNode,
    ToRealNode,
    ToIntNode,
    UnOp,
    UnOpNode,
    Var,
    ZeroExtNode,
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
        assert isinstance((x >> 1)._ast, BinOpNode) and (x >> 1)._ast.op == BinOp.BSHR

    def test_bitvec_comparison(self):
        x = BitVec("x", 8)
        assert isinstance((x > 5)._ast, BinOpNode) and (x > 5)._ast.op == BinOp.GT
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
    def test_declare_enum(self):
        Color = Datatype("Color")
        Color.declare("red")
        Color.declare("green")
        Color.declare("blue")
        Color = Color.create()

        assert hasattr(Color, "red")
        assert hasattr(Color, "green")
        assert hasattr(Color, "blue")

    def test_declare_with_fields(self):
        Pair = Datatype("Pair")
        Pair.declare("mk", ("fst", IntSort()), ("snd", IntSort()))
        Pair = Pair.create()

        assert hasattr(Pair, "mk")
        assert hasattr(Pair, "fst")
        assert hasattr(Pair, "snd")

    def test_enum_expression_building(self):
        """Enum constructors produce well-formed expressions."""
        Color = Datatype("Color")
        Color.declare("red")
        Color.declare("green")
        Color.declare("blue")
        Color = Color.create()

        expr = Color.red != Color.green
        assert isinstance(expr._ast, BinOpNode) and expr._ast.op == BinOp.NE

    def test_constructor_application(self):
        Pair = Datatype("Pair")
        Pair.declare("mk", ("fst", IntSort()), ("snd", IntSort()))
        Pair = Pair.create()

        x, y = Ints("x y")
        p = Pair.mk(x, y)
        from lean_py.z3._ast import AppNode
        assert isinstance(p._ast, AppNode)


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
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.DIV

    def test_arith_rmod(self):
        x = Int("x")
        r = 10 % x
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.MOD

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
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.BSHR

    def test_bv_size(self):
        x = BitVec("x", 32)
        assert x.size() == 32

    def test_bv_div(self):
        x, y = BitVecs("x y", 8)
        r = x / y
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.DIV

    def test_bv_mod(self):
        x, y = BitVecs("x y", 8)
        r = x % y
        assert isinstance(r._ast, BinOpNode) and r._ast.op == BinOp.MOD

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
        r = BV2Int(x)
        assert isinstance(r._ast, UnOpNode) and r._ast.op == UnOp.BV2INT
        assert r.sort() == IntSort()

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

    def test_lshr_same_as_rshift(self, kernel):
        """LShR(x, n) produces same AST as x >> n."""
        x = BitVec("x", 8)
        assert LShR(x, 2)._ast == (x >> 2)._ast
