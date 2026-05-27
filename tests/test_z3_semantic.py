"""Comprehensive semantic tests for the z3py compatibility layer.

Every test in this file is SEMANTIC — it proves a mathematical property
or verifies behavioral correctness through the Lean kernel, not just
AST construction. Tests are organized by theory/sort.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lean_py.kernel import Kernel
from lean_py.z3 import (
    RNE,
    UGT,
    ULE,
    ULT,
    Abs,
    And,
    Array,
    AShr,
    BitVec,
    BitVecs,
    BitVecVal,
    Bool,
    BoolSort,
    BoolVal,
    BV2Int,
    Concat,
    Const,
    Contains,
    DeclareSort,
    Distinct,
    Exists,
    Extract,
    Float64,
    ForAll,
    FPVal,
    Function,
    If,
    Implies,
    IndexOf,
    Int,
    Int2BV,
    Ints,
    IntSort,
    IntToStr,
    IntVal,
    K,
    Lambda,
    Length,
    LShR,
    Nat,
    NatVal,
    Not,
    Or,
    PrefixOf,
    Product,
    Q,
    Reals,
    RealVal,
    Replace,
    RotateLeft,
    RotateRight,
    SDiv,
    Select,
    SignExt,
    Solver,
    SRem,
    Store,
    StrConcat,
    String,
    Strings,
    StringVal,
    StrToInt,
    SubString,
    SuffixOf,
    Sum,
    ToReal,
    UDiv,
    URem,
    Xor,
    ZeroExt,
    fpAbs,
    fpAdd,
    fpDiv,
    fpEQ,
    fpGEQ,
    fpGT,
    fpIsInf,
    fpIsNaN,
    fpIsZero,
    fpLEQ,
    fpLT,
    fpMax,
    fpMin,
    fpMinusInfinity,
    fpMinusZero,
    fpMul,
    fpNaN,
    fpNeg,
    fpPlusInfinity,
    fpPlusZero,
    fpSub,
    sat,
    set_kernel,
    unsat,
)
from lean_py.z3.solver import _try_prove
from lean_py.z3.tactic import Goal, Tactic


@pytest.fixture(scope="module")
def kernel(example_lib) -> Kernel:
    k = Kernel(example_lib)
    import subprocess

    sp = (
        subprocess.check_output(
            ["lake", "env", "printenv", "LEAN_PATH"],
            cwd=str(Path(__file__).parent / "lean"),
        )
        .decode()
        .strip()
    )
    k.init_search(sp)
    k.load(["Init", "LeanPy.Z3"])
    set_kernel(k)
    return k


# ===================================================================
# SECTION 1: BOOLEAN LOGIC — Truth tables, laws, tautologies
# ===================================================================


class TestBoolTruthTables:
    """Exhaustive truth-table verification for basic connectives."""

    def test_and_tt(self, kernel):
        assert _try_prove(And(BoolVal(True), BoolVal(True)))

    def test_and_tf(self, kernel):
        assert not _try_prove(And(BoolVal(True), BoolVal(False)))

    def test_and_ft(self, kernel):
        assert not _try_prove(And(BoolVal(False), BoolVal(True)))

    def test_and_ff(self, kernel):
        assert not _try_prove(And(BoolVal(False), BoolVal(False)))

    def test_or_tt(self, kernel):
        assert _try_prove(Or(BoolVal(True), BoolVal(True)))

    def test_or_tf(self, kernel):
        assert _try_prove(Or(BoolVal(True), BoolVal(False)))

    def test_or_ft(self, kernel):
        assert _try_prove(Or(BoolVal(False), BoolVal(True)))

    def test_or_ff(self, kernel):
        assert not _try_prove(Or(BoolVal(False), BoolVal(False)))

    def test_not_true(self, kernel):
        assert not _try_prove(Not(BoolVal(True)))

    def test_not_false(self, kernel):
        assert _try_prove(Not(BoolVal(False)))

    def test_implies_tt(self, kernel):
        assert _try_prove(Implies(BoolVal(True), BoolVal(True)))

    def test_implies_tf(self, kernel):
        assert not _try_prove(Implies(BoolVal(True), BoolVal(False)))

    def test_implies_ft(self, kernel):
        assert _try_prove(Implies(BoolVal(False), BoolVal(True)))

    def test_implies_ff(self, kernel):
        assert _try_prove(Implies(BoolVal(False), BoolVal(False)))

    def test_xor_tt(self, kernel):
        assert not _try_prove(Xor(BoolVal(True), BoolVal(True)))

    def test_xor_tf(self, kernel):
        assert _try_prove(Xor(BoolVal(True), BoolVal(False)))

    def test_xor_ft(self, kernel):
        assert _try_prove(Xor(BoolVal(False), BoolVal(True)))

    def test_xor_ff(self, kernel):
        assert not _try_prove(Xor(BoolVal(False), BoolVal(False)))


class TestBoolLaws:
    """Classical propositional logic laws as universal proofs."""

    def test_demorgan_and(self, kernel):
        """¬(p ∧ q) ↔ (¬p ∨ ¬q)"""
        p, q = Bool("p"), Bool("q")
        lhs = Not(And(p, q))
        rhs = Or(Not(p), Not(q))
        assert _try_prove(lhs == rhs)

    def test_demorgan_or(self, kernel):
        """¬(p ∨ q) ↔ (¬p ∧ ¬q)"""
        p, q = Bool("p"), Bool("q")
        lhs = Not(Or(p, q))
        rhs = And(Not(p), Not(q))
        assert _try_prove(lhs == rhs)

    def test_contrapositive(self, kernel):
        """(p → q) ↔ (¬q → ¬p)"""
        p, q = Bool("p"), Bool("q")
        assert _try_prove(Implies(p, q) == Implies(Not(q), Not(p)))

    def test_excluded_middle(self, kernel):
        """p ∨ ¬p"""
        p = Bool("p")
        assert _try_prove(Or(p, Not(p)))

    def test_double_negation(self, kernel):
        """¬¬p ↔ p"""
        p = Bool("p")
        assert _try_prove(Not(Not(p)) == p)

    def test_absorption_and(self, kernel):
        """p ∧ (p ∨ q) ↔ p"""
        p, q = Bool("p"), Bool("q")
        assert _try_prove(And(p, Or(p, q)) == p)

    def test_absorption_or(self, kernel):
        """p ∨ (p ∧ q) ↔ p"""
        p, q = Bool("p"), Bool("q")
        assert _try_prove(Or(p, And(p, q)) == p)

    def test_modus_ponens(self, kernel):
        """p ∧ (p → q) → q"""
        p, q = Bool("p"), Bool("q")
        assert _try_prove(Implies(And(p, Implies(p, q)), q))

    def test_modus_tollens(self, kernel):
        """¬q ∧ (p → q) → ¬p"""
        p, q = Bool("p"), Bool("q")
        assert _try_prove(Implies(And(Not(q), Implies(p, q)), Not(p)))

    def test_hypothetical_syllogism(self, kernel):
        """(p → q) ∧ (q → r) → (p → r)"""
        p, q, r = Bool("p"), Bool("q"), Bool("r")
        assert _try_prove(Implies(And(Implies(p, q), Implies(q, r)), Implies(p, r)))

    def test_disjunctive_syllogism(self, kernel):
        """(p ∨ q) ∧ ¬p → q"""
        p, q = Bool("p"), Bool("q")
        assert _try_prove(Implies(And(Or(p, q), Not(p)), q))

    def test_distribution_and_over_or(self, kernel):
        """p ∧ (q ∨ r) ↔ (p ∧ q) ∨ (p ∧ r)"""
        p, q, r = Bool("p"), Bool("q"), Bool("r")
        lhs = And(p, Or(q, r))
        rhs = Or(And(p, q), And(p, r))
        assert _try_prove(lhs == rhs)

    def test_distribution_or_over_and(self, kernel):
        """p ∨ (q ∧ r) ↔ (p ∨ q) ∧ (p ∨ r)"""
        p, q, r = Bool("p"), Bool("q"), Bool("r")
        lhs = Or(p, And(q, r))
        rhs = And(Or(p, q), Or(p, r))
        assert _try_prove(lhs == rhs)

    def test_peirces_law(self, kernel):
        """((p → q) → p) → p"""
        p, q = Bool("p"), Bool("q")
        assert _try_prove(Implies(Implies(Implies(p, q), p), p))

    def test_ite_true_branch(self, kernel):
        """If(True, a, b) = a"""
        a, b = Bool("a"), Bool("b")
        assert _try_prove(If(BoolVal(True), a, b) == a)

    def test_ite_false_branch(self, kernel):
        """If(False, a, b) = b"""
        a, b = Bool("a"), Bool("b")
        assert _try_prove(If(BoolVal(False), a, b) == b)


# ===================================================================
# SECTION 2: INTEGER ARITHMETIC
# ===================================================================


class TestIntArithmeticGround:
    """Ground integer arithmetic proofs (concrete values)."""

    def test_add(self, kernel):
        assert _try_prove(IntVal(3) + IntVal(4) == IntVal(7))

    def test_sub(self, kernel):
        assert _try_prove(IntVal(10) - IntVal(3) == IntVal(7))

    def test_mul(self, kernel):
        assert _try_prove(IntVal(6) * IntVal(7) == IntVal(42))

    def test_neg(self, kernel):
        assert _try_prove(-IntVal(5) == IntVal(-5))

    def test_double_neg(self, kernel):
        assert _try_prove(-(-IntVal(5)) == IntVal(5))

    def test_div_positive(self, kernel):
        assert _try_prove(IntVal(10) / IntVal(3) == IntVal(3))

    def test_div_negative_numerator(self, kernel):
        assert _try_prove(IntVal(-7) / IntVal(2) == IntVal(-4))

    def test_mod_positive(self, kernel):
        assert _try_prove(IntVal(10) % IntVal(3) == IntVal(1))

    def test_mod_negative(self, kernel):
        """Lean's Int.mod: -7 % 2 = 1 (Euclidean)."""
        assert _try_prove(IntVal(-7) % IntVal(2) == IntVal(1))

    def test_power(self, kernel):
        assert _try_prove(IntVal(2) ** IntVal(10) == IntVal(1024))

    def test_zero_power(self, kernel):
        assert _try_prove(IntVal(5) ** IntVal(0) == IntVal(1))

    def test_large_addition(self, kernel):
        assert _try_prove(IntVal(999999) + IntVal(1) == IntVal(1000000))

    def test_negative_mul(self, kernel):
        assert _try_prove(IntVal(-3) * IntVal(-4) == IntVal(12))

    def test_mixed_sign_mul(self, kernel):
        assert _try_prove(IntVal(-3) * IntVal(4) == IntVal(-12))


class TestIntArithmeticUniversal:
    """Universal integer properties (ForAll quantified)."""

    def test_add_comm(self, kernel):
        x, y = Ints("x y")
        assert _try_prove(x + y == y + x)

    def test_add_assoc(self, kernel):
        x, y, z = Ints("x y z")
        assert _try_prove((x + y) + z == x + (y + z))

    def test_mul_comm(self, kernel):
        x, y = Ints("x y")
        assert _try_prove(x * y == y * x)

    def test_mul_assoc(self, kernel):
        x, y, z = Ints("x y z")
        assert _try_prove((x * y) * z == x * (y * z))

    def test_add_identity(self, kernel):
        x = Int("x")
        assert _try_prove(x + IntVal(0) == x)

    def test_mul_identity(self, kernel):
        x = Int("x")
        assert _try_prove(x * IntVal(1) == x)

    def test_mul_zero(self, kernel):
        x = Int("x")
        assert _try_prove(x * IntVal(0) == IntVal(0))

    def test_distributive(self, kernel):
        x, y, z = Ints("x y z")
        assert _try_prove(x * (y + z) == x * y + x * z)

    def test_sub_self(self, kernel):
        x = Int("x")
        assert _try_prove(x - x == IntVal(0))

    def test_neg_involution(self, kernel):
        x = Int("x")
        assert _try_prove(-(-x) == x)

    def test_add_neg_is_sub(self, kernel):
        x, y = Ints("x y")
        assert _try_prove(x + (-y) == x - y)

    def test_trichotomy(self, kernel):
        """For all x, y: x < y ∨ x == y ∨ x > y."""
        x, y = Ints("x y")
        assert _try_prove(Or(x < y, x == y, x > y))


class TestIntComparisons:
    """Integer comparison proofs."""

    def test_lt_ground(self, kernel):
        assert _try_prove(IntVal(3) < IntVal(5))

    def test_le_ground(self, kernel):
        assert _try_prove(IntVal(3) <= IntVal(3))

    def test_gt_ground(self, kernel):
        assert _try_prove(IntVal(5) > IntVal(3))

    def test_ge_ground(self, kernel):
        assert _try_prove(IntVal(5) >= IntVal(5))

    def test_lt_transitive(self, kernel):
        x, y, z = Ints("x y z")
        assert _try_prove(Implies(And(x < y, y < z), x < z))

    def test_le_antisymmetric(self, kernel):
        x, y = Ints("x y")
        assert _try_prove(Implies(And(x <= y, y <= x), x == y))

    def test_nat_nonneg(self, kernel):
        n = Nat("n")
        assert _try_prove(n >= NatVal(0))

    def test_nat_succ_pos(self, kernel):
        n = Nat("n")
        assert _try_prove(n + NatVal(1) > NatVal(0))


# ===================================================================
# SECTION 3: RATIONAL (REAL) ARITHMETIC
# ===================================================================


class TestRationalGround:
    """Ground rational arithmetic proofs."""

    def test_third_plus_two_thirds(self, kernel):
        assert _try_prove(Q(1, 3) + Q(2, 3) == Q(1, 1))

    def test_half_plus_half(self, kernel):
        assert _try_prove(Q(1, 2) + Q(1, 2) == Q(1, 1))

    def test_half_times_two(self, kernel):
        assert _try_prove(Q(1, 2) * Q(2, 1) == Q(1, 1))

    def test_quarter_plus_three_quarters(self, kernel):
        assert _try_prove(Q(1, 4) + Q(3, 4) == Q(1, 1))

    def test_rational_subtraction(self, kernel):
        assert _try_prove(Q(5, 6) - Q(1, 6) == Q(2, 3))

    def test_rational_division(self, kernel):
        assert _try_prove(Q(1, 2) / Q(3, 1) == Q(1, 6))

    def test_rational_neg(self, kernel):
        assert _try_prove(-Q(1, 3) + Q(1, 3) == Q(0, 1))

    def test_realval_integer(self, kernel):
        assert _try_prove(RealVal(5) == ToReal(IntVal(5)))

    def test_realval_float_half(self, kernel):
        """0.5 as a Real should equal 1/2."""
        assert _try_prove(RealVal(0.5) == Q(1, 2))


class TestRationalUniversal:
    """Universal rational properties."""

    def test_add_comm(self, kernel):
        x, y = Reals("x y")
        assert _try_prove(x + y == y + x)

    def test_mul_comm(self, kernel):
        x, y = Reals("x y")
        assert _try_prove(x * y == y * x)

    def test_distributive(self, kernel):
        x, y, z = Reals("x y z")
        assert _try_prove(x * (y + z) == x * y + x * z)

    def test_to_real_preserves_add(self, kernel):
        a, b = Ints("a b")
        g = Goal()
        g.add(ToReal(a + b) == ToReal(a) + ToReal(b))
        assert len(Tactic("simp [Rat.ofInt]").apply(g)) == 0

    def test_to_real_preserves_mul(self, kernel):
        a, b = Ints("a b")
        g = Goal()
        g.add(ToReal(a * b) == ToReal(a) * ToReal(b))
        assert len(Tactic("simp [Rat.ofInt]").apply(g)) == 0


# ===================================================================
# SECTION 4: BIT-VECTOR OPERATIONS
# ===================================================================


class TestBVGroundArith:
    """Ground bit-vector arithmetic proofs."""

    def test_add_8bit(self, kernel):
        assert _try_prove(BitVecVal(100, 8) + BitVecVal(28, 8) == BitVecVal(128, 8))

    def test_add_wrap(self, kernel):
        """255 + 1 wraps to 0 in 8 bits."""
        assert _try_prove(BitVecVal(255, 8) + BitVecVal(1, 8) == BitVecVal(0, 8))

    def test_sub_wrap(self, kernel):
        """0 - 1 wraps to 255 in 8 bits."""
        assert _try_prove(BitVecVal(0, 8) - BitVecVal(1, 8) == BitVecVal(255, 8))

    def test_mul_8bit(self, kernel):
        assert _try_prove(BitVecVal(3, 8) * BitVecVal(4, 8) == BitVecVal(12, 8))

    def test_mul_overflow(self, kernel):
        """16 * 16 = 256, wraps to 0 in 8 bits."""
        assert _try_prove(BitVecVal(16, 8) * BitVecVal(16, 8) == BitVecVal(0, 8))

    def test_neg_twos_complement(self, kernel):
        """-1 in 8-bit is 0xFF."""
        assert _try_prove(-BitVecVal(1, 8) == BitVecVal(255, 8))

    def test_neg_twos_complement_42(self, kernel):
        assert _try_prove(-BitVecVal(42, 8) == BitVecVal(214, 8))

    def test_udiv(self, kernel):
        assert _try_prove(UDiv(BitVecVal(10, 8), BitVecVal(3, 8)) == BitVecVal(3, 8))

    def test_urem(self, kernel):
        assert _try_prove(URem(BitVecVal(10, 8), BitVecVal(3, 8)) == BitVecVal(1, 8))


class TestBVBitwise:
    """Ground bitwise operation proofs."""

    def test_and(self, kernel):
        assert _try_prove(
            BitVecVal(0b11001100, 8) & BitVecVal(0b10101010, 8) == BitVecVal(0b10001000, 8)
        )

    def test_or(self, kernel):
        assert _try_prove(
            BitVecVal(0b11001100, 8) | BitVecVal(0b10101010, 8) == BitVecVal(0b11101110, 8)
        )

    def test_xor(self, kernel):
        assert _try_prove(
            BitVecVal(0b11001100, 8) ^ BitVecVal(0b10101010, 8) == BitVecVal(0b01100110, 8)
        )

    def test_not(self, kernel):
        assert _try_prove(~BitVecVal(0b11001100, 8) == BitVecVal(0b00110011, 8))

    def test_shl(self, kernel):
        assert _try_prove(BitVecVal(1, 8) << 4 == BitVecVal(16, 8))

    def test_lshr(self, kernel):
        assert _try_prove(LShR(BitVecVal(128, 8), 4) == BitVecVal(8, 8))

    def test_ashr_positive(self, kernel):
        assert _try_prove(AShr(BitVecVal(64, 8), 2) == BitVecVal(16, 8))

    def test_ashr_negative(self, kernel):
        """Arithmetic shift right of negative value fills with 1s."""
        assert _try_prove(AShr(BitVecVal(0x80, 8), 2) == BitVecVal(0xE0, 8))


class TestBVUniversal:
    """Universal bit-vector laws."""

    def test_xor_self_zero(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(x ^ x == BitVecVal(0, 8))

    def test_and_self_identity(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(x & x == x)

    def test_or_self_identity(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(x | x == x)

    def test_double_neg(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(-(-x) == x)

    def test_not_not(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(~~x == x)

    def test_demorgan_bv(self, kernel):
        """~(a & b) == (~a) | (~b)"""
        a, b = BitVecs("a b", 8)
        assert _try_prove(~(a & b) == (~a) | (~b))

    def test_add_comm(self, kernel):
        a, b = BitVecs("a b", 8)
        assert _try_prove(a + b == b + a)

    def test_sub_self(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(x - x == BitVecVal(0, 8))


class TestBVExtractConcat:
    """Extract/Concat/Extend proofs."""

    def test_extract_low_nibble(self, kernel):
        assert _try_prove(Extract(3, 0, BitVecVal(0xAB, 8)) == BitVecVal(0xB, 4))

    def test_extract_high_nibble(self, kernel):
        assert _try_prove(Extract(7, 4, BitVecVal(0xAB, 8)) == BitVecVal(0xA, 4))

    def test_concat_nibbles(self, kernel):
        assert _try_prove(Concat(BitVecVal(0xA, 4), BitVecVal(0xB, 4)) == BitVecVal(0xAB, 8))

    def test_zeroext_value(self, kernel):
        assert _try_prove(ZeroExt(8, BitVecVal(0xFF, 8)) == BitVecVal(0xFF, 16))

    def test_signext_positive(self, kernel):
        assert _try_prove(SignExt(8, BitVecVal(0x7F, 8)) == BitVecVal(0x007F, 16))

    def test_signext_negative(self, kernel):
        """Sign-extending 0xFF (= -1 signed) gives 0xFFFF."""
        assert _try_prove(SignExt(8, BitVecVal(0xFF, 8)) == BitVecVal(0xFFFF, 16))

    def test_rotate_left_identity(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(RotateLeft(x, 8) == x)

    def test_rotate_right_identity(self, kernel):
        x = BitVec("x", 8)
        assert _try_prove(RotateRight(x, 8) == x)

    def test_rotate_left_ground(self, kernel):
        assert _try_prove(RotateLeft(BitVecVal(0b00000001, 8), 3) == BitVecVal(0b00001000, 8))


class TestBVSigned:
    """Signed bit-vector semantics."""

    def test_sdiv_positive(self, kernel):
        assert _try_prove(SDiv(BitVecVal(6, 8), BitVecVal(2, 8)) == BitVecVal(3, 8))

    def test_srem_positive(self, kernel):
        assert _try_prove(SRem(BitVecVal(7, 8), BitVecVal(3, 8)) == BitVecVal(1, 8))

    def test_ult_unsigned(self, kernel):
        """1 < 255 unsigned."""
        assert _try_prove(ULT(BitVecVal(1, 8), BitVecVal(255, 8)))

    def test_ule_eq(self, kernel):
        assert _try_prove(ULE(BitVecVal(5, 8), BitVecVal(5, 8)))

    def test_ugt(self, kernel):
        assert _try_prove(UGT(BitVecVal(255, 8), BitVecVal(0, 8)))

    def test_bv2int_unsigned(self, kernel):
        """BV2Int(0xFF, 8) = 255 (unsigned)."""
        assert _try_prove(BV2Int(BitVecVal(0xFF, 8)) == IntVal(255))


# ===================================================================
# SECTION 5: ARRAY THEORY
# ===================================================================


class TestArraySemantics:
    """Array theory proofs — store/select axioms."""

    def test_read_after_write_same(self, kernel):
        """Select(Store(a, i, v), i) = v"""
        a = Array("a", IntSort(), IntSort())
        i, v = Ints("i v")
        assert _try_prove(Select(Store(a, i, v), i) == v)

    def test_read_after_write_different(self, kernel):
        """i ≠ j → Select(Store(a, i, v), j) = Select(a, j)"""
        a = Array("a", IntSort(), IntSort())
        i, j, v = Ints("i j v")
        assert _try_prove(Implies(i != j, Select(Store(a, i, v), j) == Select(a, j)))

    def test_constant_array(self, kernel):
        """Select(K(IntSort(), 42), i) = 42"""
        i = Int("i")
        assert _try_prove(Select(K(IntSort(), IntVal(42)), i) == IntVal(42))

    def test_double_write_same_index(self, kernel):
        """Store(Store(a, i, v1), i, v2) = Store(a, i, v2) on index i"""
        a = Array("a", IntSort(), IntSort())
        i, v1, v2 = Ints("i v1 v2")
        arr = Store(Store(a, i, v1), i, v2)
        assert _try_prove(Select(arr, i) == v2)

    def test_store_chain(self, kernel):
        """Write 10 at index 0, 20 at index 1, read both back."""
        a = K(IntSort(), IntVal(0))
        a = Store(a, IntVal(0), IntVal(10))
        a = Store(a, IntVal(1), IntVal(20))
        assert _try_prove(
            And(Select(a, IntVal(0)) == IntVal(10), Select(a, IntVal(1)) == IntVal(20))
        )

    def test_constant_array_bool(self, kernel):
        """Constant True array: all elements are True."""
        i = Int("i")
        assert _try_prove(Select(K(IntSort(), BoolVal(True)), i))

    def test_store_preserves_other(self, kernel):
        """Writing at 0 doesn't affect index 1."""
        a = K(IntSort(), IntVal(0))
        a2 = Store(a, IntVal(0), IntVal(99))
        assert _try_prove(Select(a2, IntVal(1)) == IntVal(0))


# ===================================================================
# SECTION 6: STRING THEORY
# ===================================================================


class TestStringGround:
    """Ground string proofs."""

    def test_concat(self, kernel):
        assert _try_prove(
            StrConcat(StringVal("hello"), StringVal(" world")) == StringVal("hello world")
        )

    def test_length(self, kernel):
        assert _try_prove(Length(StringVal("hello")) == IntVal(5))

    def test_length_empty(self, kernel):
        assert _try_prove(Length(StringVal("")) == IntVal(0))

    def test_length_concat(self, kernel):
        """len(a ++ b) = len(a) + len(b) for ground strings."""
        a, b = StringVal("foo"), StringVal("bar")
        assert _try_prove(Length(StrConcat(a, b)) == Length(a) + Length(b))

    def test_prefix_of(self, kernel):
        assert _try_prove(PrefixOf(StringVal("ab"), StringVal("abc")))

    def test_prefix_empty(self, kernel):
        """Empty string is prefix of everything."""
        assert _try_prove(PrefixOf(StringVal(""), StringVal("hello")))

    def test_prefix_self(self, kernel):
        assert _try_prove(PrefixOf(StringVal("abc"), StringVal("abc")))

    def test_suffix_of(self, kernel):
        assert _try_prove(SuffixOf(StringVal("bc"), StringVal("abc")))

    def test_suffix_empty(self, kernel):
        assert _try_prove(SuffixOf(StringVal(""), StringVal("hello")))

    def test_suffix_self(self, kernel):
        assert _try_prove(SuffixOf(StringVal("abc"), StringVal("abc")))

    def test_contains(self, kernel):
        assert _try_prove(Contains(StringVal("abcdef"), StringVal("cde")))

    def test_contains_empty(self, kernel):
        assert _try_prove(Contains(StringVal("abc"), StringVal("")))

    def test_contains_self(self, kernel):
        assert _try_prove(Contains(StringVal("abc"), StringVal("abc")))

    def test_replace(self, kernel):
        assert _try_prove(
            Replace(StringVal("hello world"), StringVal("world"), StringVal("lean"))
            == StringVal("hello lean")
        )

    def test_replace_no_match(self, kernel):
        assert _try_prove(
            Replace(StringVal("abc"), StringVal("xyz"), StringVal("!")) == StringVal("abc")
        )

    def test_indexof_found(self, kernel):
        assert _try_prove(IndexOf(StringVal("abcdef"), StringVal("cd"), IntVal(0)) == IntVal(2))

    def test_indexof_not_found(self, kernel):
        assert _try_prove(IndexOf(StringVal("abc"), StringVal("xyz"), IntVal(0)) == IntVal(-1))

    def test_indexof_with_offset(self, kernel):
        assert _try_prove(IndexOf(StringVal("abcabc"), StringVal("bc"), IntVal(2)) == IntVal(4))

    def test_str_to_int_valid(self, kernel):
        assert _try_prove(StrToInt(StringVal("42")) == IntVal(42))

    def test_str_to_int_invalid(self, kernel):
        assert _try_prove(StrToInt(StringVal("abc")) == IntVal(-1))

    def test_int_to_str(self, kernel):
        assert _try_prove(IntToStr(IntVal(42)) == StringVal("42"))

    def test_substring(self, kernel):
        assert _try_prove(SubString(StringVal("abcdef"), IntVal(2), IntVal(3)) == StringVal("cde"))


class TestStringUniversal:
    """Universal string properties."""

    def test_concat_assoc(self, kernel):
        """String concatenation is associative."""
        x, y, z = Strings("x y z")
        g = Goal()
        g.add(StrConcat(StrConcat(x, y), z) == StrConcat(x, StrConcat(y, z)))
        assert len(Tactic("simp [String.append_assoc]").apply(g)) == 0

    def test_empty_concat_left(self, kernel):
        x = String("x")
        g = Goal()
        g.add(StrConcat(StringVal(""), x) == x)
        assert len(Tactic("simp").apply(g)) == 0

    def test_empty_concat_right(self, kernel):
        x = String("x")
        g = Goal()
        g.add(StrConcat(x, StringVal("")) == x)
        assert len(Tactic("simp").apply(g)) == 0

    def test_prefix_of_concat_ground(self, kernel):
        """'ab' is a prefix of 'abcd' (ground)."""
        assert _try_prove(PrefixOf(StringVal("ab"), StringVal("abcd")))

    def test_length_nonneg(self, kernel):
        x = String("x")
        assert _try_prove(Length(x) >= IntVal(0))


# ===================================================================
# SECTION 7: FLOATING-POINT PROOFS
# ===================================================================


class TestFPGroundArith:
    """Ground floating-point arithmetic proofs."""

    def test_add(self, kernel):
        assert _try_prove(fpEQ(fpAdd(RNE(), FPVal(1.5), FPVal(2.5)), FPVal(4.0)))

    def test_sub(self, kernel):
        assert _try_prove(fpEQ(fpSub(RNE(), FPVal(5.0), FPVal(3.0)), FPVal(2.0)))

    def test_mul(self, kernel):
        assert _try_prove(fpEQ(fpMul(RNE(), FPVal(3.0), FPVal(4.0)), FPVal(12.0)))

    def test_div(self, kernel):
        assert _try_prove(fpEQ(fpDiv(RNE(), FPVal(10.0), FPVal(2.0)), FPVal(5.0)))

    def test_neg(self, kernel):
        assert _try_prove(fpEQ(fpNeg(FPVal(3.14)), FPVal(-3.14)))

    def test_neg_neg(self, kernel):
        assert _try_prove(fpEQ(fpNeg(fpNeg(FPVal(42.0))), FPVal(42.0)))

    def test_abs_positive(self, kernel):
        assert _try_prove(fpEQ(fpAbs(FPVal(3.14)), FPVal(3.14)))

    def test_abs_negative(self, kernel):
        assert _try_prove(fpEQ(fpAbs(FPVal(-3.14)), FPVal(3.14)))

    def test_min(self, kernel):
        assert _try_prove(fpEQ(fpMin(FPVal(1.0), FPVal(2.0)), FPVal(1.0)))

    def test_max(self, kernel):
        assert _try_prove(fpEQ(fpMax(FPVal(1.0), FPVal(2.0)), FPVal(2.0)))

    def test_add_zero(self, kernel):
        assert _try_prove(fpEQ(fpAdd(RNE(), FPVal(5.0), FPVal(0.0)), FPVal(5.0)))

    def test_mul_one(self, kernel):
        assert _try_prove(fpEQ(fpMul(RNE(), FPVal(5.0), FPVal(1.0)), FPVal(5.0)))

    def test_mul_zero(self, kernel):
        assert _try_prove(fpEQ(fpMul(RNE(), FPVal(5.0), FPVal(0.0)), FPVal(0.0)))


class TestFPComparisons:
    """Floating-point comparison proofs."""

    def test_lt(self, kernel):
        assert _try_prove(fpLT(FPVal(1.0), FPVal(2.0)))

    def test_leq_strict(self, kernel):
        assert _try_prove(fpLEQ(FPVal(1.0), FPVal(2.0)))

    def test_leq_equal(self, kernel):
        assert _try_prove(fpLEQ(FPVal(3.0), FPVal(3.0)))

    def test_gt(self, kernel):
        assert _try_prove(fpGT(FPVal(5.0), FPVal(3.0)))

    def test_geq(self, kernel):
        assert _try_prove(fpGEQ(FPVal(5.0), FPVal(5.0)))

    def test_eq(self, kernel):
        assert _try_prove(fpEQ(FPVal(3.14), FPVal(3.14)))

    def test_negative_lt_zero(self, kernel):
        assert _try_prove(fpLT(FPVal(-1.0), FPVal(0.0)))

    def test_neg_infinity_lt_all(self, kernel):
        assert _try_prove(fpLT(fpMinusInfinity(Float64()), FPVal(0.0)))

    def test_all_lt_pos_infinity(self, kernel):
        assert _try_prove(fpLT(FPVal(1e300), fpPlusInfinity(Float64())))


class TestFPSpecialValues:
    """IEEE 754 special value semantics."""

    def test_nan_neq_self(self, kernel):
        """NaN != NaN (IEEE semantics)."""
        nan = fpNaN(Float64())
        assert not _try_prove(fpEQ(nan, nan))

    def test_nan_not_lt_anything(self, kernel):
        nan = fpNaN(Float64())
        assert not _try_prove(fpLT(nan, FPVal(0.0)))

    def test_nan_not_gt_anything(self, kernel):
        nan = fpNaN(Float64())
        assert not _try_prove(fpGT(nan, FPVal(0.0)))

    def test_positive_zero_eq_negative_zero(self, kernel):
        """IEEE: +0.0 == -0.0."""
        assert _try_prove(fpEQ(fpPlusZero(Float64()), fpMinusZero(Float64())))

    def test_inf_is_inf(self, kernel):
        assert _try_prove(fpIsInf(fpPlusInfinity(Float64())))

    def test_nan_is_nan(self, kernel):
        assert _try_prove(fpIsNaN(fpNaN(Float64())))

    def test_zero_is_zero(self, kernel):
        assert _try_prove(fpIsZero(fpPlusZero(Float64())))

    def test_neg_zero_is_zero(self, kernel):
        assert _try_prove(fpIsZero(fpMinusZero(Float64())))

    def test_normal_is_not_nan(self, kernel):
        assert not _try_prove(fpIsNaN(FPVal(1.0)))

    def test_normal_is_not_inf(self, kernel):
        assert not _try_prove(fpIsInf(FPVal(1.0)))


# ===================================================================
# SECTION 8: QUANTIFIER PROOFS
# ===================================================================


class TestForAllProofs:
    """Universal quantifier proofs."""

    def test_identity_add(self, kernel):
        x = Int("x")
        assert _try_prove(ForAll([x], x + IntVal(0) == x))

    def test_double_forall(self, kernel):
        x, y = Ints("x y")
        assert _try_prove(ForAll([x, y], x + y == y + x))

    def test_nat_nonneg(self, kernel):
        n = Nat("n")
        assert _try_prove(ForAll([n], n >= NatVal(0)))

    def test_square_nonneg(self, kernel):
        n = Nat("n")
        assert _try_prove(ForAll([n], n * n >= NatVal(0)))

    def test_implication_chain(self, kernel):
        """ForAll x: (x > 0 ∧ x < 10) → x < 10"""
        x = Int("x")
        assert _try_prove(ForAll([x], Implies(And(x > IntVal(0), x < IntVal(10)), x < IntVal(10))))

    def test_bv_xor_self_zero(self, kernel):
        x = BitVec("x", 16)
        assert _try_prove(ForAll([x], x ^ x == BitVecVal(0, 16)))

    def test_not_universally_positive(self, kernel):
        """Not all integers are positive."""
        x = Int("x")
        assert not _try_prove(ForAll([x], x > IntVal(0)))

    def test_not_universally_equal(self, kernel):
        x, y = Ints("x y")
        assert not _try_prove(ForAll([x, y], x == y))


class TestExistsProofs:
    """Existential quantifier proofs."""

    def test_exists_zero(self, kernel):
        """There exists an x such that x = 0."""
        x = Int("x")
        assert _try_prove(Exists([x], x == IntVal(0)))

    def test_exists_sum(self, kernel):
        """There exists x such that x + 3 = 5."""
        x = Int("x")
        assert _try_prove(Exists([x], x + IntVal(3) == IntVal(5)))


class TestUninterpretedFunctions:
    """Proofs about uninterpreted functions."""

    def test_congruence(self, kernel):
        """x = y → f(x) = f(y)"""
        S = DeclareSort("S")
        f = Function("f", S, S)
        x, y = Const("x", S), Const("y", S)
        assert _try_prove(Implies(x == y, f(x) == f(y)))

    def test_congruence_binary(self, kernel):
        """x1=y1 ∧ x2=y2 → g(x1,x2) = g(y1,y2)"""
        S = DeclareSort("S")
        g = Function("g", S, S, S)
        x1, y1, x2, y2 = Const("x1", S), Const("y1", S), Const("x2", S), Const("y2", S)
        assert _try_prove(Implies(And(x1 == y1, x2 == y2), g(x1, x2) == g(y1, y2)))

    def test_composition(self, kernel):
        """x = y → f(f(x)) = f(f(y))"""
        S = DeclareSort("S")
        f = Function("f", S, S)
        x, y = Const("x", S), Const("y", S)
        assert _try_prove(Implies(x == y, f(f(x)) == f(f(y))))

    def test_syllogism(self, kernel):
        """If all humans are mortal, and Socrates is human, then Socrates is mortal."""
        Person = DeclareSort("Person")
        Human = Function("Human", Person, BoolSort())
        Mortal = Function("Mortal", Person, BoolSort())
        socrates = Const("socrates", Person)
        x = Const("x", Person)
        premise = And(ForAll([x], Implies(Human(x), Mortal(x))), Human(socrates))
        assert _try_prove(Implies(premise, Mortal(socrates)))


# ===================================================================
# SECTION 9: SOLVER SEMANTICS
# ===================================================================


class TestSolverSemantics:
    """Solver behavioral correctness tests."""

    def test_empty_solver_is_sat(self, kernel):
        s = Solver()
        assert s.check() == sat

    def test_true_is_sat(self, kernel):
        s = Solver()
        s.add(BoolVal(True))
        assert s.check() == sat

    def test_false_is_unsat(self, kernel):
        s = Solver()
        s.add(BoolVal(False))
        assert s.check() == unsat

    def test_contradiction_is_unsat(self, kernel):
        x = Int("x")
        s = Solver()
        s.add(x > IntVal(0))
        s.add(x < IntVal(0))
        assert s.check() == unsat

    def test_two_equalities_unsat(self, kernel):
        x = Int("x")
        s = Solver()
        s.add(x == IntVal(1))
        s.add(x == IntVal(2))
        assert s.check() == unsat

    def test_push_pop_restores(self, kernel):
        s = Solver()
        s.add(BoolVal(True))
        s.push()
        s.add(BoolVal(False))
        assert s.check() == unsat
        s.pop()
        # After pop, only True remains — provable, so sat
        assert s.check() == sat

    def test_nested_push_pop(self, kernel):
        x = Int("x")
        s = Solver()
        s.add(x == x)  # tautology
        s.push()
        s.add(IntVal(1) == IntVal(1))  # tautology
        s.push()
        s.add(IntVal(1) == IntVal(2))  # contradiction
        assert s.check() == unsat
        s.pop()
        assert s.check() == sat  # x == x ∧ 1 == 1
        s.pop()
        assert s.check() == sat  # x == x

    def test_reset_clears(self, kernel):
        s = Solver()
        s.add(BoolVal(False))
        assert s.check() == unsat
        s.reset()
        assert s.check() == sat

    def test_distinct_two(self, kernel):
        x, y = Ints("x y")
        s = Solver()
        s.add(Distinct(x, y))
        s.add(x == IntVal(1))
        s.add(y == IntVal(1))
        assert s.check() == unsat

    def test_distinct_three(self, kernel):
        x, y, z = Ints("x y z")
        s = Solver()
        s.add(Distinct(x, y, z))
        s.add(x == IntVal(1))
        s.add(y == IntVal(2))
        s.add(z == IntVal(1))
        assert s.check() == unsat

    def test_context_manager(self, kernel):
        s = Solver()
        s.add(BoolVal(True))
        with s:
            s.add(BoolVal(False))
            assert s.check() == unsat
        assert s.check() == sat


# ===================================================================
# SECTION 10: NEGATIVE PROOFS (things that should NOT be provable)
# ===================================================================


class TestNegativeProofs:
    """Claims that must NOT be provable."""

    def test_false(self, kernel):
        assert not _try_prove(BoolVal(False))

    def test_wrong_add(self, kernel):
        assert not _try_prove(IntVal(1) + IntVal(1) == IntVal(3))

    def test_wrong_mul(self, kernel):
        assert not _try_prove(IntVal(2) * IntVal(3) == IntVal(7))

    def test_all_positive(self, kernel):
        x = Int("x")
        assert not _try_prove(x > IntVal(0))

    def test_all_equal(self, kernel):
        x, y = Ints("x y")
        assert not _try_prove(x == y)

    def test_nat_has_predecessor(self, kernel):
        """Not every Nat has a predecessor (0 doesn't)."""
        n = Nat("n")
        assert not _try_prove(n > NatVal(0))

    def test_bv_wrong_value(self, kernel):
        assert not _try_prove(BitVecVal(1, 8) == BitVecVal(2, 8))

    def test_wrong_string_length(self, kernel):
        assert not _try_prove(Length(StringVal("abc")) == IntVal(4))

    def test_wrong_fp(self, kernel):
        assert not _try_prove(fpEQ(FPVal(1.0), FPVal(2.0)))

    def test_implies_wrong_direction(self, kernel):
        """p → q does NOT imply q → p."""
        p, q = Bool("p"), Bool("q")
        assert not _try_prove(Implies(Implies(p, q), Implies(q, p)))

    def test_xor_not_and(self, kernel):
        """XOR is not AND."""
        p, q = Bool("p"), Bool("q")
        assert not _try_prove(Xor(p, q) == And(p, q))

    def test_lt_not_le(self, kernel):
        """< is strictly less, not ≤."""
        x = Int("x")
        assert not _try_prove(x < x)

    def test_empty_does_not_contain(self, kernel):
        """Empty string doesn't contain 'a'."""
        assert not _try_prove(Contains(StringVal(""), StringVal("a")))

    def test_prefix_not_suffix(self, kernel):
        assert not _try_prove(PrefixOf(StringVal("bc"), StringVal("abc")))

    def test_suffix_not_prefix(self, kernel):
        assert not _try_prove(SuffixOf(StringVal("ab"), StringVal("abc")))

    def test_nan_not_zero(self, kernel):
        assert not _try_prove(fpIsZero(fpNaN(Float64())))


# ===================================================================
# SECTION 11: IF-THEN-ELSE PROOFS
# ===================================================================


class TestIfThenElse:
    """Conditional expression proofs."""

    def test_ite_ground_true(self, kernel):
        assert _try_prove(If(BoolVal(True), IntVal(1), IntVal(2)) == IntVal(1))

    def test_ite_ground_false(self, kernel):
        assert _try_prove(If(BoolVal(False), IntVal(1), IntVal(2)) == IntVal(2))

    def test_ite_abs(self, kernel):
        """If(x >= 0, x, -x) >= 0"""
        x = Int("x")
        assert _try_prove(If(x >= IntVal(0), x, -x) >= IntVal(0))

    def test_ite_max(self, kernel):
        """max(x, y) >= x and max(x, y) >= y"""
        x, y = Ints("x y")
        mx = If(x >= y, x, y)
        assert _try_prove(And(mx >= x, mx >= y))

    def test_ite_min(self, kernel):
        """min(x, y) <= x and min(x, y) <= y"""
        x, y = Ints("x y")
        mn = If(x <= y, x, y)
        assert _try_prove(And(mn <= x, mn <= y))


# ===================================================================
# SECTION 12: DISTINCT
# ===================================================================


class TestDistinct:
    """Distinctness constraint proofs."""

    def test_distinct_two_ground(self, kernel):
        assert _try_prove(Distinct(IntVal(1), IntVal(2)))

    def test_distinct_three_ground(self, kernel):
        assert _try_prove(Distinct(IntVal(1), IntVal(2), IntVal(3)))

    def test_not_distinct_same(self, kernel):
        assert not _try_prove(Distinct(IntVal(1), IntVal(1)))

    def test_distinct_implies_neq(self, kernel):
        x, y = Ints("x y")
        assert _try_prove(Implies(Distinct(x, y), x != y))


# ===================================================================
# SECTION 13: MIXED-SORT PROOFS
# ===================================================================


class TestMixedSort:
    """Cross-sort interaction proofs."""

    def test_bv_to_int(self, kernel):
        assert _try_prove(BV2Int(BitVecVal(42, 8)) == IntVal(42))

    def test_int_to_real(self, kernel):
        assert _try_prove(ToReal(IntVal(7)) == RealVal(7))

    def test_int_to_bv_roundtrip(self, kernel):
        """Int2BV(BV2Int(x)) = x for unsigned values."""
        x = BitVec("x", 8)
        assert _try_prove(Int2BV(BV2Int(x), 8) == x)

    def test_bv_to_int_add(self, kernel):
        """BV2Int(3#8 + 4#8) = 7 (no overflow)."""
        assert _try_prove(BV2Int(BitVecVal(3, 8) + BitVecVal(4, 8)) == IntVal(7))


# ===================================================================
# SECTION 14: SUM / PRODUCT / ABS
# ===================================================================


class TestSumProductAbs:
    """Aggregation function proofs."""

    def test_sum_ground(self, kernel):
        assert _try_prove(Sum(IntVal(1), IntVal(2), IntVal(3)) == IntVal(6))

    def test_product_ground(self, kernel):
        assert _try_prove(Product(IntVal(2), IntVal(3), IntVal(4)) == IntVal(24))

    def test_abs_positive(self, kernel):
        assert _try_prove(Abs(IntVal(5)) == IntVal(5))

    def test_abs_negative(self, kernel):
        assert _try_prove(Abs(IntVal(-5)) == IntVal(5))

    def test_abs_zero(self, kernel):
        assert _try_prove(Abs(IntVal(0)) == IntVal(0))

    def test_abs_nonneg(self, kernel):
        """|x| >= 0 for all x."""
        x = Int("x")
        assert _try_prove(Abs(x) >= IntVal(0))

    def test_triangle_inequality(self, kernel):
        """|x + y| <= |x| + |y|"""
        x, y = Ints("x y")
        assert _try_prove(Abs(x + y) <= Abs(x) + Abs(y))


# ===================================================================
# SECTION 15: LAMBDA APPLICATION
# ===================================================================


class TestLambdaApplication:
    """Lambda expression semantics via arrays."""

    def test_lambda_select(self, kernel):
        """Select(Lambda(x, x + 1), 5) = 6"""
        x = Int("x")
        f = Lambda([x], x + IntVal(1))
        assert _try_prove(Select(f, IntVal(5)) == IntVal(6))

    def test_lambda_constant(self, kernel):
        """Select(Lambda(x, 42), anything) = 42"""
        x = Int("x")
        f = Lambda([x], IntVal(42))
        assert _try_prove(Select(f, IntVal(999)) == IntVal(42))

    def test_lambda_square(self, kernel):
        """Select(Lambda(x, x*x), 7) = 49"""
        x = Int("x")
        f = Lambda([x], x * x)
        assert _try_prove(Select(f, IntVal(7)) == IntVal(49))


# ===================================================================
# SECTION 16: COMPLEX COMBINED PROOFS
# ===================================================================


class TestComplexProofs:
    """Multi-step proofs combining multiple theories."""

    def test_pigeonhole_2(self, kernel):
        """2 pigeons, 1 hole: not all different."""
        x, y = Ints("x y")
        s = Solver()
        s.add(And(x >= IntVal(0), x <= IntVal(0)))  # x in {0}
        s.add(And(y >= IntVal(0), y <= IntVal(0)))  # y in {0}
        s.add(x != y)
        assert s.check() == unsat

    def test_linear_system(self, kernel):
        """x + y = 10, x - y = 4 → x = 7, y = 3"""
        x, y = Ints("x y")
        premises = And(x + y == IntVal(10), x - y == IntVal(4))
        assert _try_prove(Implies(premises, And(x == IntVal(7), y == IntVal(3))))

    def test_modular_identity(self, kernel):
        """(a + b) mod n = ((a mod n) + (b mod n)) mod n for n > 0"""
        # Ground instance: (7 + 8) mod 5 = ((7 mod 5) + (8 mod 5)) mod 5
        assert _try_prove(
            IntVal(15) % IntVal(5)
            == ((IntVal(7) % IntVal(5)) + (IntVal(8) % IntVal(5))) % IntVal(5)
        )

    def test_bv_add_sub_inverse(self, kernel):
        """(x + y) - y = x for bitvectors."""
        x, y = BitVecs("x y", 16)
        assert _try_prove((x + y) - y == x)

    def test_string_length_nonneg(self, kernel):
        """String length is always non-negative."""
        s = String("s")
        assert _try_prove(Length(s) >= IntVal(0))

    def test_concat_contains_parts(self, kernel):
        """'hello' ++ 'world' contains 'hello' as prefix (ground)."""
        assert _try_prove(
            PrefixOf(StringVal("hello"), StrConcat(StringVal("hello"), StringVal("world")))
        )

    def test_fp_mul_comm_ground(self, kernel):
        """FP multiplication is commutative for ground values."""
        assert _try_prove(
            fpEQ(fpMul(RNE(), FPVal(2.0), FPVal(3.0)), fpMul(RNE(), FPVal(3.0), FPVal(2.0)))
        )

    def test_array_swap(self, kernel):
        """Swapping two elements and reading back."""
        a = Array("a", IntSort(), IntSort())
        i, j = Ints("i j")
        vi = Select(a, i)
        vj = Select(a, j)
        swapped = Store(Store(a, i, vj), j, vi)
        # After swap, a[j] = original a[i] (when i ≠ j)
        assert _try_prove(Implies(i != j, Select(swapped, j) == Select(a, i)))

    def test_bool_to_int_encoding(self, kernel):
        """Encoding booleans as 0/1: if p then 1 else 0."""
        p = Bool("p")
        enc = If(p, IntVal(1), IntVal(0))
        assert _try_prove(And(enc >= IntVal(0), enc <= IntVal(1)))

    def test_nat_induction_base(self, kernel):
        """Base case of a simple property: 0 + 0 = 0."""
        assert _try_prove(NatVal(0) + NatVal(0) == NatVal(0))

    def test_power_of_two_bv(self, kernel):
        """2^4 = 16 in 8-bit bitvectors."""
        two = BitVecVal(2, 8)
        result = two * two * two * two  # 2^4
        assert _try_prove(result == BitVecVal(16, 8))
