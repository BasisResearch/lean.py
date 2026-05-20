"""z3py compatibility layer tests.

Uses the existing TestLib fixture to avoid managed-project builds in CI.
Exercises the expression AST, solver, prove(), and convenience functions.
"""

from __future__ import annotations

import pytest

from lean_py.kernel import Kernel
from lean_py.z3 import (
    And,
    Array,
    ArraySort,
    BitVec,
    BitVecRef,
    BitVecSort,
    BitVecVal,
    BitVecs,
    Bool,
    BoolSort,
    BoolVal,
    Const,
    Consts,
    Datatype,
    DeclareSort,
    Distinct,
    Exists,
    ForAll,
    Function,
    If,
    Implies,
    Int,
    IntSort,
    IntVal,
    Ints,
    K,
    Nat,
    NatSort,
    NatVal,
    Not,
    Or,
    Real,
    RealSort,
    Select,
    Solver,
    Store,
    Xor,
    sat,
    set_kernel,
    unknown,
    unsat,
)
from lean_py.z3.solver import _goal_string, _try_prove


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
        assert x.to_lean() == "x"
        assert x.sort() == IntSort()
        assert ("x", "Int") in x._vars

    def test_arith_ops(self):
        x, y = Ints("x y")
        assert (x + y).to_lean() == "(x + y)"
        assert (x - y).to_lean() == "(x - y)"
        assert (x * y).to_lean() == "(x * y)"
        assert (-x).to_lean() == "(-x)"

    def test_comparison(self):
        x = Int("x")
        assert (x > 5).to_lean() == "(x > (5 : Int))"
        assert (x < 5).to_lean() == "(x < (5 : Int))"
        assert (x >= 5).to_lean() == "(x \u2265 (5 : Int))"
        assert (x <= 5).to_lean() == "(x \u2264 (5 : Int))"

    def test_eq_ne(self):
        x, y = Ints("x y")
        eq = x == y
        ne = x != y
        assert eq.to_lean() == "(x = y)"
        assert ne.to_lean() == "(x \u2260 y)"

    def test_bool_ops(self):
        a, b = Bool("a"), Bool("b")
        assert And(a, b).to_lean() == "(a \u2227 b)"
        assert Or(a, b).to_lean() == "(a \u2228 b)"
        assert Not(a).to_lean() == "(\u00aca)"
        assert Implies(a, b).to_lean() == "(a \u2192 b)"
        assert Xor(a, b).to_lean() == "(Xor' a b)"

    def test_bool_operators(self):
        a, b = Bool("a"), Bool("b")
        assert (a & b).to_lean() == "(a \u2227 b)"
        assert (a | b).to_lean() == "(a \u2228 b)"
        assert (~a).to_lean() == "(\u00aca)"

    def test_forall(self):
        x = Int("x")
        expr = ForAll([x], x + 0 == x)
        assert "\u2200" in expr.to_lean()
        assert "(x : Int)" in expr.to_lean()
        # x should be bound, not free
        assert ("x", "Int") not in expr._vars

    def test_exists(self):
        x = Int("x")
        expr = Exists([x], x > 0)
        assert "\u2203" in expr.to_lean()

    def test_distinct(self):
        x, y, z = Ints("x y z")
        d = Distinct(x, y, z)
        assert "\u2260" in d.to_lean()
        assert "\u2227" in d.to_lean()

    def test_if_then_else(self):
        x = Int("x")
        expr = If(x > 0, x, -x)
        assert "if" in expr.to_lean()
        assert "then" in expr.to_lean()
        assert "else" in expr.to_lean()

    def test_int_coercion(self):
        x = Int("x")
        assert (x + 1).to_lean() == "(x + (1 : Int))"
        assert (1 + x).to_lean() == "((1 : Int) + x)"
        assert (x > 5).to_lean() == "(x > (5 : Int))"

    def test_function_decl(self):
        S = DeclareSort("S")
        f = Function("f", IntSort(), S)
        x = Int("x")
        app = f(x)
        assert app.to_lean() == "(f x)"
        # f and S should be free vars
        assert any(n == "f" for n, _ in app._vars)
        assert ("S", "Type") in app._vars

    def test_nat_var(self):
        n = Nat("n")
        assert n.sort() == NatSort()
        assert ("n", "Nat") in n._vars

    def test_val_constructors(self):
        assert IntVal(42).to_lean() == "(42 : Int)"
        assert NatVal(7).to_lean() == "(7 : Nat)"
        assert BoolVal(True).to_lean() == "True"
        assert BoolVal(False).to_lean() == "False"


class TestGoalString:
    def test_no_vars(self):
        assert _goal_string(BoolVal(True)) == "True"

    def test_single_var(self):
        x = Int("x")
        goal = _goal_string(x > 0)
        assert goal == "\u2200 (x : Int), (x > (0 : Int))"

    def test_multiple_vars_sorted(self):
        x, y = Ints("x y")
        goal = _goal_string(And(x > 0, y > 0))
        assert "\u2200" in goal
        assert "(x : Int)" in goal
        assert "(y : Int)" in goal

    def test_uninterpreted_sort_comes_first(self):
        S = DeclareSort("S")
        f = Function("f", S, BoolSort())
        a = Const("a", S)
        goal = _goal_string(f(a))
        # Type var S should come before value var a and function f
        idx_s = goal.index("(S : Type)")
        idx_a = goal.index("(a : S)")
        assert idx_s < idx_a


# ------------------------------------------------------------------
# Proving (requires kernel)
# ------------------------------------------------------------------


class TestProve:
    def test_arith_simple(self, kernel, capsys):
        x = Int("x")
        result = _try_prove(_goal_string(Implies(x > 0, x + 1 > 0)))
        assert result is True

    def test_linear_combo(self, kernel):
        x, y = Ints("x y")
        claim = Implies(And(x > 0, y > 0), x + y > 0)
        assert _try_prove(_goal_string(claim))

    def test_nat_identity(self, kernel):
        n = Nat("n")
        claim = ForAll([n], n + 0 == n)
        assert _try_prove(_goal_string(claim))

    def test_bool_tautology(self, kernel):
        p = Bool("p")
        claim = Implies(p, p)
        assert _try_prove(_goal_string(claim))

    def test_double_negation(self, kernel):
        p = Bool("p")
        claim = Implies(Not(Not(p)), p)
        assert _try_prove(_goal_string(claim))

    def test_nat_arith(self, kernel):
        n = Nat("n")
        claim = ForAll([n], Implies(n > 0, n + 1 > 1))
        assert _try_prove(_goal_string(claim))


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
        # (can't prove negation of a satisfiable formula)
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
        assert _try_prove(_goal_string(claim))


# ------------------------------------------------------------------
# N-Queens (small)
# ------------------------------------------------------------------


class TestNQueens:
    def test_2queens_unsat(self, kernel):
        """2 queens on a 2x2 board is impossible."""
        # q_i = column of queen in row i (1-indexed for simplicity)
        q0, q1 = Int("q0"), Int("q1")

        constraints = []
        # Columns in range [1,2]
        for q in (q0, q1):
            constraints.append(q >= IntVal(1))
            constraints.append(q <= IntVal(2))

        # Different columns
        constraints.append(Distinct(q0, q1))

        # No diagonal attacks: |q0 - q1| != |0 - 1| = 1
        # Since we have 2 rows, row diff is always 1
        # q0 - q1 != 1 and q0 - q1 != -1
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
        assert x.to_lean() == "x"
        assert x.sort() == BitVecSort(8)
        assert ("x", "(BitVec 8)") in x._vars

    def test_bitvec_val(self):
        v = BitVecVal(42, 8)
        assert v.to_lean() == "(42 : BitVec 8)"

    def test_bitvec_arithmetic(self):
        x, y = BitVecs("x y", 8)
        assert (x + y).to_lean() == "(x + y)"
        assert (x - y).to_lean() == "(x - y)"
        assert (x * y).to_lean() == "(x * y)"
        assert (-x).to_lean() == "(-x)"

    def test_bitvec_bitwise(self):
        x, y = BitVecs("x y", 8)
        assert (x & y).to_lean() == "(x &&& y)"
        assert (x | y).to_lean() == "(x ||| y)"
        assert (x ^ y).to_lean() == "(x ^^^ y)"
        assert (~x).to_lean() == "(~~~x)"

    def test_bitvec_shift(self):
        x = BitVec("x", 8)
        assert (x << 2).to_lean() == "(x <<< (2 : BitVec 8))"
        assert (x >> 1).to_lean() == "(x >>> (1 : BitVec 8))"

    def test_bitvec_comparison(self):
        x = BitVec("x", 8)
        assert (x > 5).to_lean() == "(x > (5 : BitVec 8))"
        assert (x == BitVecVal(0, 8)).to_lean() == "(x = (0 : BitVec 8))"

    def test_bitvec_coercion(self):
        x = BitVec("x", 8)
        assert (x + 1).to_lean() == "(x + (1 : BitVec 8))"
        assert (1 + x).to_lean() == "((1 : BitVec 8) + x)"

    def test_bitvec_or_idempotent(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(_goal_string(ForAll([x], (x | x) == x)))

    def test_bitvec_and_self(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(_goal_string(ForAll([x], (x & x) == x)))


# ------------------------------------------------------------------
# Arrays (SMT theory)
# ------------------------------------------------------------------


class TestArray:
    def test_array_sort(self):
        s = ArraySort(IntSort(), IntSort())
        assert "→" in s.to_lean()

    def test_array_var(self):
        a = Array("a", IntSort(), IntSort())
        assert a.to_lean() == "a"
        assert ("a", "(Int → Int)") in a._vars

    def test_select(self):
        a = Array("a", IntSort(), IntSort())
        i = Int("i")
        sel = Select(a, i)
        assert sel.to_lean() == "(a i)"

    def test_store(self):
        a = Array("a", IntSort(), IntSort())
        i = Int("i")
        v = Int("v")
        s = Store(a, i, v)
        assert "if" in s.to_lean()
        assert "then" in s.to_lean()

    def test_constant_array(self):
        c = K(IntSort(), IntVal(0))
        assert "fun" in c.to_lean()
        assert "(0 : Int)" in c.to_lean()

    def test_select_store_same_index(self, kernel):
        """Store then Select at the same index gives the written value."""
        a = Array("a", IntSort(), IntSort())
        v = Int("v")
        written = Store(a, IntVal(3), v)
        read_back = Select(written, IntVal(3))
        claim = ForAll([a, v], read_back == v)
        assert _try_prove(_goal_string(claim))

    def test_constant_array_read(self, kernel):
        """Reading from a constant array gives the constant value."""
        i = Int("i")
        c = K(IntSort(), IntVal(42))
        claim = ForAll([i], Select(c, i) == IntVal(42))
        assert _try_prove(_goal_string(claim))


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
        assert "≠" in expr.to_lean()
        assert "red" in expr.to_lean()
        assert "green" in expr.to_lean()

    def test_constructor_application(self):
        Pair = Datatype("Pair")
        Pair.declare("mk", ("fst", IntSort()), ("snd", IntSort()))
        Pair = Pair.create()

        x, y = Ints("x y")
        p = Pair.mk(x, y)
        assert "(mk x y)" in p.to_lean()
