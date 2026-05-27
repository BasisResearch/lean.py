"""z3py-compatible expression AST backed by Z3 AST nodes.

Each expression node carries:
- ``_ast``: a Z3 AST node (from :mod:`lean_py.z3._ast`)
- ``_sort``: the expression's sort
- ``_vars``: free variables as ``frozenset[tuple[str, ASTSort]]``

The tree is purely structural -- no Lean kernel interaction is needed
to build expressions. Lean interaction only happens at proof time
(see :mod:`lean_py.z3.solver`).
"""

from __future__ import annotations

import math
import struct
from decimal import Decimal, getcontext
from fractions import Fraction
from typing import Any, Sequence

from lean_py.z3._inductive_reg import _register_inductive
from lean_py.z3._ast import (
    ASTNode,
    ASTSort,
    AppNode,
    ArrowASTSort,
    BitvecASTSort,
    BinOp,
    BinOpNode,
    BoolLit,
    BvLit,
    ConstArrayNode,
    DistinctNode,
    ExistsNode,
    ExtractNode,
    ForAllNode,
    InReNode,
    Int2BvNode,
    IntASTSort,
    IntLit,
    IntToStrNode,
    IteNode,
    LambdaNode,
    NatASTSort,
    NatLit,
    PropSort,
    RealASTSort,
    ReConcatNode,
    ReComplementNode,
    ReIntersectNode,
    ReLoopNode,
    ReOptionNode,
    RePlusNode,
    ReRangeNode,
    ReStarNode,
    ReUnionNode,
    SelectNode,
    SignExtNode,
    StoreNode,
    StrConcatNode,
    StrContainsNode,
    StrIndexOfNode,
    StrLenNode,
    StrPrefixOfNode,
    StrReplaceNode,
    StrSubstrNode,
    StrSuffixOfNode,
    StrToIntNode,
    StringASTSort,
    StringLit,
    ToIntNode,
    ToRealNode,
    UnOp,
    TypeASTSort,
    UnOpNode,
    UninterpASTSort,
    Var as _AstVar,
    ZeroExtNode,
    FpASTSort,
    FpLitNode,
    FpOpNode,
    FinDomainASTSort,
    FinDomainLit,
    InductiveASTSort,
    InductiveCtorNode,
    InductiveAccessorNode,
    InductiveRecognizerNode,
    CharASTSort,
    CharLit,
    CharToNatNode,
    CharFromBvNode,
    CharIsDigitNode,
    SeqASTSort,
    SeqEmptyNode,
    SeqUnitNode,
    SeqLenNode,
    SeqConcatNode,
    SeqContainsNode,
    SeqPrefixOfNode,
    SeqSuffixOfNode,
    SeqNthNode,
)


def _is_literal(node: ASTNode) -> bool:
    """True for ground literal AST nodes (no variables/operations)."""
    return isinstance(
        node,
        (IntLit, NatLit, BoolLit, BvLit, StringLit, FpLitNode, FinDomainLit, CharLit),
    )


# ---------------------------------------------------------------------------
# Sorts
# ---------------------------------------------------------------------------


class SortRef:
    """Base sort."""

    __slots__ = ("_ast_sort",)

    def __init__(self, ast_sort: ASTSort) -> None:
        self._ast_sort = ast_sort

    def __repr__(self) -> str:
        return _sort_repr(self._ast_sort)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SortRef) and self._ast_sort == other._ast_sort

    def __hash__(self) -> int:
        return hash(self._ast_sort)

    def name(self) -> str:
        """Return sort name as string (z3py compat)."""
        return _sort_repr(self._ast_sort)

    def kind(self) -> int:
        """Return sort kind as integer (z3py compat).

        Values match z3 Z3_sort_kind: UNINTERPRETED=0, BOOL=1, INT=2,
        REAL=3, BV=4, ARRAY=5, DATATYPE=6, UNKNOWN=1000.
        """
        s = self._ast_sort
        if isinstance(s, PropSort):
            return 1  # Z3_BOOL_SORT
        if isinstance(s, IntASTSort):
            return 2  # Z3_INT_SORT
        if isinstance(s, NatASTSort):
            return 2  # treat Nat as int kind
        if isinstance(s, RealASTSort):
            return 3  # Z3_REAL_SORT
        if isinstance(s, BitvecASTSort):
            return 4  # Z3_BV_SORT
        if isinstance(s, ArrowASTSort):
            return 5  # Z3_ARRAY_SORT
        if isinstance(s, StringASTSort):
            return 7  # Z3_SEQ_SORT
        if isinstance(s, UninterpASTSort):
            return 0  # Z3_UNINTERPRETED_SORT
        if isinstance(s, InductiveASTSort):
            return 6  # Z3_DATATYPE_SORT
        return 1000  # Z3_UNKNOWN_SORT

    def sexpr(self) -> str:
        """S-expression representation of this sort."""
        return _sort_repr(self._ast_sort)


class BoolSortRef(SortRef):
    pass


class ArithSortRef(SortRef):
    pass


class UninterpretedSortRef(SortRef):
    """Declared via ``DeclareSort``."""

    pass


class DatatypeSortRef(SortRef):
    """Sort backed by a Lean inductive type."""

    def __init__(self, ast_sort: ASTSort, type_name: str, ctor_info: list) -> None:
        super().__init__(ast_sort)
        self._type_name = type_name
        self._ctor_info = ctor_info  # list of (ctor_name, fields)
        self._constructors: list = []
        self._recognizers: list = []
        self._accessors: list[list] = []  # list of list[FuncDeclRef]

    def name(self) -> str:
        return self._type_name

    def num_constructors(self) -> int:
        return len(self._ctor_info)

    def constructor(self, i: int):
        return self._constructors[i]

    def recognizer(self, i: int):
        return self._recognizers[i]

    def accessor(self, i: int, j: int):
        return self._accessors[i][j]

    def kind(self) -> int:
        return 6  # Z3_DATATYPE_SORT


def BoolSort() -> BoolSortRef:
    return BoolSortRef(PropSort())


def IntSort() -> ArithSortRef:
    return ArithSortRef(IntASTSort())


def NatSort() -> ArithSortRef:
    return ArithSortRef(NatASTSort())


def RealSort() -> ArithSortRef:
    return ArithSortRef(RealASTSort())


def DeclareSort(name: str) -> UninterpretedSortRef:
    return UninterpretedSortRef(UninterpASTSort(name))


class BitVecSortRef(SortRef):
    """Fixed-width bit-vector sort, maps to Lean's ``BitVec n``."""

    __slots__ = ("_width",)

    def __init__(self, width: int) -> None:
        super().__init__(BitvecASTSort(width))
        self._width = width

    @property
    def size(self) -> int:
        return self._width


def BitVecSort(n: int) -> BitVecSortRef:
    return BitVecSortRef(n)


class ArraySortRef(SortRef):
    """SMT array sort, maps to Lean function type ``dom → rng``."""

    __slots__ = ("_domain", "_range")

    def __init__(self, domain: SortRef, range_sort: SortRef) -> None:
        super().__init__(ArrowASTSort(domain._ast_sort, range_sort._ast_sort))
        self._domain = domain
        self._range = range_sort

    def domain(self) -> SortRef:
        return self._domain

    def range(self) -> SortRef:
        return self._range


def ArraySort(domain: SortRef, range_sort: SortRef) -> ArraySortRef:
    return ArraySortRef(domain, range_sort)


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------


class ExprRef:
    """Base expression node."""

    __slots__ = ("_ast", "_sort", "_vars")

    def __init__(
        self,
        ast: ASTNode,
        sort: SortRef,
        vars: frozenset[tuple[str, ASTSort]] = frozenset(),
    ) -> None:
        self._ast = ast
        self._sort = sort
        self._vars = vars

    def sort(self) -> SortRef:
        return self._sort

    def __repr__(self) -> str:
        return _ast_repr(self._ast)

    def __eq__(self, other: object) -> BoolRef:  # type: ignore[override]
        if isinstance(other, (int, float)):
            other = _coerce_val(other, self._sort)
        if not isinstance(other, ExprRef):
            return NotImplemented
        # Normalize: put non-literal args on the left.  Python's reflected
        # comparison protocol can swap self/other when one type is a subclass
        # of the other (e.g. IntNumRef subclasses ArithRef), leading to
        # "5 = x + 3" instead of "x + 3 = 5".  We canonicalize by putting
        # literal/value AST nodes on the RHS so tactics see the natural order.
        lhs, rhs = self._ast, other._ast
        if _is_literal(lhs) and not _is_literal(rhs):
            lhs, rhs = rhs, lhs
        return BoolRef(
            BinOpNode(BinOp.EQ, lhs, rhs),
            _merge(self._vars, other._vars),
        )

    def __ne__(self, other: object) -> BoolRef:  # type: ignore[override]
        if isinstance(other, (int, float)):
            other = _coerce_val(other, self._sort)
        if not isinstance(other, ExprRef):
            return NotImplemented
        return BoolRef(
            BinOpNode(BinOp.NE, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __hash__(self) -> int:
        return hash(self._ast)

    def __bool__(self) -> bool:
        raise TypeError(
            "Symbolic expressions cannot be cast to concrete Boolean values"
        )

    def num_args(self) -> int:
        """Number of arguments (children) of this expression."""
        return len(_ast_children(self._ast))

    def arg(self, i: int) -> ExprRef:
        """Return the i-th argument of this expression."""
        children = _ast_children(self._ast)
        if i < 0 or i >= len(children):
            raise IndexError(f"arg index {i} out of range (0..{len(children) - 1})")
        return _child_expr(children[i], self, i)

    def children(self) -> list[ExprRef]:
        """Return list of all children of this expression."""
        return [_child_expr(c, self, i) for i, c in enumerate(_ast_children(self._ast))]

    def decl(self) -> FuncDeclRef:
        """Return the function declaration for this expression."""
        name = _ast_decl_name(self._ast)
        return FuncDeclRef(name, (), self._sort)

    def sexpr(self) -> str:
        """Return S-expression representation."""
        return _ast_repr(self._ast)

    def params(self) -> list:
        """Return parameters of this expression (e.g. bit-width for Extract)."""
        ast = self._ast
        if isinstance(ast, ExtractNode):
            return [ast.hi, ast.lo]
        if isinstance(ast, (ZeroExtNode, SignExtNode)):
            return [ast.bits]
        if isinstance(ast, Int2BvNode):
            return [ast.width]
        if isinstance(ast, BvLit):
            return [ast.width]
        if isinstance(ast, ReLoopNode):
            return [ast.lo, ast.hi]
        return []

    def translate(self, ctx: object) -> ExprRef:
        """Translate expression to another context (no-op — single context)."""
        return self

    def get_id(self) -> int:
        """Return a unique integer identifier for this expression."""
        return id(self._ast)

    def serialize(self) -> str:
        """Serialize expression to string."""
        return _ast_repr(self._ast)


class DatatypeRef(ExprRef):
    """Datatype expression (constructor application result)."""

    pass


class BoolRef(ExprRef):
    """Boolean / Prop expression."""

    __slots__ = ()

    def __init__(
        self,
        ast: ASTNode,
        vars: frozenset[tuple[str, ASTSort]] = frozenset(),
    ) -> None:
        super().__init__(ast, BoolSort(), vars)

    def __and__(self, other: BoolRef) -> BoolRef:
        return And(self, other)

    def __or__(self, other: BoolRef) -> BoolRef:
        return Or(self, other)

    def __invert__(self) -> BoolRef:
        return Not(self)

    def __xor__(self, other: BoolRef) -> BoolRef:
        return Xor(self, other)

    # Bool→Int coercion: z3py converts b + 0 to If(b, 1, 0) + 0
    def __add__(self, other: object) -> ArithRef:
        return _bool_to_int(self).__add__(_coerce_arith_any(other))

    def __radd__(self, other: object) -> ArithRef:
        return _coerce_arith_any(other).__add__(_bool_to_int(self))

    def __mul__(self, other: object) -> ArithRef:
        return _bool_to_int(self).__mul__(_coerce_arith_any(other))

    def __rmul__(self, other: object) -> ArithRef:
        return _coerce_arith_any(other).__mul__(_bool_to_int(self))


class ArithRef(ExprRef):
    """Arithmetic expression (Int, Nat, Real)."""

    __slots__ = ()

    def __init__(
        self,
        ast: ASTNode,
        sort: ArithSortRef,
        vars: frozenset[tuple[str, ASTSort]] = frozenset(),
    ) -> None:
        super().__init__(ast, sort, vars)

    def _binop(self, op: str, other: ArithRef | int | float) -> ArithRef:
        other = _coerce_arith(other, self._sort)
        return ArithRef(
            BinOpNode(op, self._ast, other._ast),
            self._sort,  # type: ignore[arg-type]
            _merge(self._vars, other._vars),
        )

    def __add__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop(BinOp.ADD, other)

    def __radd__(self, other: int | float) -> ArithRef:
        return _coerce_arith(other, self._sort)._binop(BinOp.ADD, self)

    def __sub__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop(BinOp.SUB, other)

    def __rsub__(self, other: int | float) -> ArithRef:
        return _coerce_arith(other, self._sort)._binop(BinOp.SUB, self)

    def __mul__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop(BinOp.MUL, other)

    def __rmul__(self, other: int | float) -> ArithRef:
        return _coerce_arith(other, self._sort)._binop(BinOp.MUL, self)

    def __truediv__(self, other: ArithRef | int | float) -> ArithRef:
        # Int uses Euclidean div (SMT-LIB), Real uses normal div
        op = BinOp.EDIV if isinstance(self._sort._ast_sort, IntASTSort) else BinOp.DIV
        return self._binop(op, other)

    def __mod__(self, other: ArithRef | int | float) -> ArithRef:
        # Int uses Euclidean mod (SMT-LIB), Real uses normal mod
        op = BinOp.EMOD if isinstance(self._sort._ast_sort, IntASTSort) else BinOp.MOD
        return self._binop(op, other)

    def __rtruediv__(self, other: int | float) -> ArithRef:
        op = BinOp.EDIV if isinstance(self._sort._ast_sort, IntASTSort) else BinOp.DIV
        return _coerce_arith(other, self._sort)._binop(op, self)

    def __rmod__(self, other: int | float) -> ArithRef:
        op = BinOp.EMOD if isinstance(self._sort._ast_sort, IntASTSort) else BinOp.MOD
        return _coerce_arith(other, self._sort)._binop(op, self)

    def __pow__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop(BinOp.POW, other)

    def __rpow__(self, other: int | float) -> ArithRef:
        return _coerce_arith(other, self._sort)._binop(BinOp.POW, self)

    def __pos__(self) -> ArithRef:
        return self

    def __abs__(self) -> ArithRef:
        zero = _coerce_arith(0, self._sort)
        cond = BoolRef(
            BinOpNode(BinOp.GE, self._ast, zero._ast),
            self._vars,
        )
        neg = ArithRef(UnOpNode(UnOp.NEG, self._ast), self._sort, self._vars)  # type: ignore[arg-type]
        return ArithRef(
            IteNode(cond._ast, self._ast, neg._ast),
            self._sort,  # type: ignore[arg-type]
            self._vars,
        )

    def is_int(self) -> bool:
        return isinstance(self._sort._ast_sort, IntASTSort)

    def is_real(self) -> bool:
        return isinstance(self._sort._ast_sort, RealASTSort)

    def __neg__(self) -> ArithRef:
        return ArithRef(
            UnOpNode(UnOp.NEG, self._ast),
            self._sort,  # type: ignore[arg-type]
            self._vars,
        )

    def __lt__(self, other: ArithRef | int | float) -> BoolRef:
        other = _coerce_arith(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.LT, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __le__(self, other: ArithRef | int | float) -> BoolRef:
        other = _coerce_arith(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.LE, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __gt__(self, other: ArithRef | int | float) -> BoolRef:
        other = _coerce_arith(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.GT, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __ge__(self, other: ArithRef | int | float) -> BoolRef:
        other = _coerce_arith(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.GE, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )


class IntNumRef(ArithRef):
    """Integer numeral — concrete integer value with extraction methods."""

    __slots__ = ()

    def as_long(self) -> int:
        """Return the integer value as a Python int."""
        if isinstance(self._ast, IntLit):
            return self._ast.val
        if isinstance(self._ast, NatLit):
            return self._ast.val
        raise TypeError("Not an integer literal")

    def as_string(self) -> str:
        return str(self.as_long())


class RatNumRef(ArithRef):
    """Rational numeral — concrete rational value with extraction methods."""

    __slots__ = ("_num", "_den")

    def __init__(self, num: int, den: int) -> None:
        ast = BinOpNode(BinOp.DIV, ToRealNode(IntLit(num)), ToRealNode(IntLit(den)))
        super().__init__(ast, RealSort())
        self._num = num
        self._den = den

    def numerator(self) -> IntNumRef:
        return IntNumRef(IntLit(self._num), IntSort())

    def denominator(self) -> IntNumRef:
        return IntNumRef(IntLit(self._den), IntSort())

    def numerator_as_long(self) -> int:
        return self._num

    def denominator_as_long(self) -> int:
        return self._den

    def as_fraction(self):
        return Fraction(self._num, self._den)

    def as_decimal(self, prec: int = 10) -> str:
        ctx = getcontext()
        ctx.prec = prec
        return str(Decimal(self._num) / Decimal(self._den))

    def as_string(self) -> str:
        return f"{self._num}/{self._den}"

    def as_long(self) -> int:
        return self._num // self._den


class AlgebraicNumRef(ArithRef):
    """Algebraic number reference with approximation method."""

    __slots__ = ()

    def approx(self, precision: int = 10) -> RatNumRef:
        """Return rational approximation to given precision."""
        # In lean.py, algebraic numbers are not natively supported;
        # return a placeholder rational
        return RatNumRef(0, 1)


class BitVecRef(ExprRef):
    """Bit-vector expression, maps to Lean's ``BitVec n``."""

    __slots__ = ()

    def __init__(
        self,
        ast: ASTNode,
        sort: BitVecSortRef,
        vars: frozenset[tuple[str, ASTSort]] = frozenset(),
    ) -> None:
        super().__init__(ast, sort, vars)

    def _binop(self, op: str, other: BitVecRef | int) -> BitVecRef:
        other = _coerce_bv(other, self._sort)
        return BitVecRef(
            BinOpNode(op, self._ast, other._ast),
            self._sort,  # type: ignore[arg-type]
            _merge(self._vars, other._vars),
        )

    # Arithmetic
    def __add__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop(BinOp.ADD, other)

    def __radd__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop(BinOp.ADD, self)

    def __sub__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop(BinOp.SUB, other)

    def __rsub__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop(BinOp.SUB, self)

    def __mul__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop(BinOp.MUL, other)

    def __rmul__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop(BinOp.MUL, self)

    def __neg__(self) -> BitVecRef:
        return BitVecRef(
            UnOpNode(UnOp.NEG, self._ast),
            self._sort,  # type: ignore[arg-type]
            self._vars,
        )

    # Bitwise
    def __and__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop(BinOp.BAND, other)

    def __rand__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop(BinOp.BAND, self)

    def __or__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop(BinOp.BOR, other)

    def __ror__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop(BinOp.BOR, self)

    def __xor__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop(BinOp.BXOR, other)

    def __rxor__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop(BinOp.BXOR, self)

    def __invert__(self) -> BitVecRef:
        return BitVecRef(
            UnOpNode(UnOp.BNOT, self._ast),
            self._sort,  # type: ignore[arg-type]
            self._vars,
        )

    def __lshift__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop(BinOp.BSHL, other)

    def __rshift__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop(BinOp.ASHR, other)

    def __rlshift__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop(BinOp.BSHL, self)

    def __rrshift__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop(BinOp.ASHR, self)

    def __truediv__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop(BinOp.SDIV, other)

    def __mod__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop(BinOp.SMOD, other)

    def __pos__(self) -> BitVecRef:
        return self

    def size(self) -> int:
        sort = self._sort
        if isinstance(sort, BitVecSortRef):
            return sort._width
        raise TypeError("size() requires BitVecSortRef")

    # Comparisons (signed, matching z3py operator semantics)
    def __lt__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.SLT, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __le__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.SLE, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __gt__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.SGT, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __ge__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.SGE, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )


class BitVecNumRef(BitVecRef):
    """Bit-vector numeral — concrete bitvector value with extraction methods."""

    __slots__ = ()

    def as_long(self) -> int:
        """Return the unsigned integer value."""
        if isinstance(self._ast, BvLit):
            return self._ast.val
        raise TypeError("Not a bitvector literal")

    def as_signed_long(self) -> int:
        """Return the signed integer value."""
        if isinstance(self._ast, BvLit):
            val = self._ast.val
            w = self._ast.width
            if val >= (1 << (w - 1)):
                return val - (1 << w)
            return val
        raise TypeError("Not a bitvector literal")

    def as_string(self) -> str:
        return str(self.as_long())


class ArrayRef(ExprRef):
    """SMT array expression, maps to Lean function type."""

    __slots__ = ()

    def __init__(
        self,
        ast: ASTNode,
        sort: ArraySortRef,
        vars: frozenset[tuple[str, ASTSort]] = frozenset(),
    ) -> None:
        super().__init__(ast, sort, vars)

    def __getitem__(self, idx: ExprRef) -> ExprRef:
        return Select(self, idx)


class QuantifierRef(BoolRef):
    """Quantified expression (ForAll / Exists)."""

    __slots__ = ("_quantifier", "_bound", "_body")

    def __init__(
        self,
        quantifier: str,
        bound: list[ExprRef],
        body: BoolRef,
    ) -> None:
        # Build nested ForAllNode/ExistsNode from inside out
        bound_names = frozenset(
            (v._ast.name, v._sort._ast_sort)
            for v in bound
            if isinstance(v._ast, _AstVar)
        )
        free = body._vars - bound_names

        # Build the nested AST node
        node_cls = ForAllNode if quantifier == "\u2200" else ExistsNode
        ast: ASTNode = body._ast
        for v in reversed(bound):
            ast = node_cls(
                name=v._ast.name if isinstance(v._ast, _AstVar) else str(v._ast),
                sort=v._sort._ast_sort,
                body=ast,
            )

        super().__init__(ast, free)
        self._quantifier = quantifier
        self._bound = bound
        self._body = body

    def body(self) -> BoolRef:
        """Return the body of the quantifier."""
        return self._body

    def is_forall(self) -> bool:
        return self._quantifier == "\u2200"

    def is_exists(self) -> bool:
        return self._quantifier == "\u2203"

    def num_vars(self) -> int:
        """Return the number of bound variables."""
        return len(self._bound)

    def var_name(self, i: int) -> str:
        """Return the name of the i-th bound variable."""
        v = self._bound[i]
        if isinstance(v._ast, _AstVar):
            return v._ast.name
        return str(v._ast)

    def var_sort(self, i: int) -> SortRef:
        """Return the sort of the i-th bound variable."""
        return self._bound[i]._sort

    def weight(self) -> int:
        """Return quantifier weight (default 0)."""
        return 0

    def qid(self) -> str:
        """Return quantifier identifier (empty string)."""
        return ""

    def skolem_id(self) -> str:
        """Return Skolem identifier (empty string)."""
        return ""

    def num_patterns(self) -> int:
        """Return number of patterns (0 — patterns not supported)."""
        return 0

    def pattern(self, i: int) -> ExprRef:
        """Return the i-th pattern."""
        raise IndexError("No patterns")

    def num_no_patterns(self) -> int:
        """Return number of no-patterns (0)."""
        return 0

    def no_pattern(self, i: int) -> ExprRef:
        """Return the i-th no-pattern."""
        raise IndexError("No no-patterns")


# ---------------------------------------------------------------------------
# Function declarations
# ---------------------------------------------------------------------------


def _wrap_expr(ast: ASTNode, sort: SortRef, vars_: frozenset) -> ExprRef:
    """Wrap an AST node into the correct ExprRef subclass based on sort."""
    s = sort._ast_sort
    if isinstance(s, PropSort):
        return BoolRef(ast, vars_)
    if isinstance(s, (IntASTSort, NatASTSort, RealASTSort)):
        return ArithRef(ast, sort, vars_)  # type: ignore[arg-type]
    if isinstance(s, BitvecASTSort):
        return BitVecRef(ast, sort, vars_)  # type: ignore[arg-type]
    if isinstance(s, ArrowASTSort):
        return ArrayRef(ast, sort, vars_)  # type: ignore[arg-type]
    return ExprRef(ast, sort, vars_)


class FuncDeclRef:
    """Uninterpreted function declaration, created via ``Function(...)``."""

    __slots__ = ("_name", "_domain", "_range", "_ast_sort")

    def __init__(
        self,
        name: str,
        domain: tuple[SortRef, ...],
        range_sort: SortRef,
    ) -> None:
        self._name = name
        self._domain = domain
        self._range = range_sort
        # Build arrow sort for the function type
        sorts = [*domain, range_sort]
        ast_sort: ASTSort = sorts[-1]._ast_sort
        for s in reversed(sorts[:-1]):
            ast_sort = ArrowASTSort(s._ast_sort, ast_sort)
        self._ast_sort = ast_sort

    def __call__(self, *args: ExprRef) -> ExprRef:
        if len(args) != len(self._domain):
            raise TypeError(
                f"{self._name} expects {len(self._domain)} args, got {len(args)}"
            )
        merged: frozenset[tuple[str, ASTSort]] = frozenset().union(
            *(a._vars for a in args)
        )
        # The function itself is a free variable
        merged = merged | frozenset([(self._name, self._ast_sort)])
        # Uninterpreted sorts used by the function are also free
        for s in (*self._domain, self._range):
            if isinstance(s, UninterpretedSortRef) and isinstance(
                s._ast_sort, UninterpASTSort
            ):
                merged = merged | frozenset([(s._ast_sort.name, TypeASTSort())])
        func_ast = _AstVar(self._name)
        args_ast = tuple(a._ast for a in args)
        ast = AppNode(func_ast, args_ast) if args else func_ast
        return _wrap_expr(ast, self._range, merged)

    def name(self) -> str:
        """Return the function name."""
        return self._name

    def arity(self) -> int:
        """Return the number of arguments."""
        return len(self._domain)

    def domain(self, i: int) -> SortRef:
        """Return the sort of the i-th argument."""
        return self._domain[i]

    def range(self) -> SortRef:
        """Return the range (return) sort."""
        return self._range

    def __repr__(self) -> str:
        return f"{self._name} : {_sort_repr(self._ast_sort)}"


class _InductiveCtorDecl(FuncDeclRef):
    """Constructor for an inductive type — produces InductiveCtorNode."""

    __slots__ = ("_type_name", "_ctor_name", "_result_sort")

    def __init__(
        self,
        type_name: str,
        ctor_name: str,
        domain: tuple[SortRef, ...],
        result_sort: SortRef,
    ) -> None:
        super().__init__(ctor_name, domain, result_sort)
        self._type_name = type_name
        self._ctor_name = ctor_name
        self._result_sort = result_sort

    def __call__(self, *args: ExprRef) -> DatatypeRef:
        if len(args) != len(self._domain):
            raise TypeError(
                f"{self._ctor_name} expects {len(self._domain)} args, got {len(args)}"
            )
        coerced = []
        for a, d in zip(args, self._domain):
            if isinstance(a, (int, float)):
                a = _coerce_val(a, d)
            coerced.append(a)
        merged: frozenset[tuple[str, ASTSort]] = (
            frozenset().union(*(a._vars for a in coerced)) if coerced else frozenset()
        )
        ast = InductiveCtorNode(
            self._type_name, self._ctor_name, tuple(a._ast for a in coerced)
        )
        return DatatypeRef(ast, self._result_sort, merged)


class _InductiveAccessorDecl(FuncDeclRef):
    """Accessor for an inductive type — produces InductiveAccessorNode."""

    __slots__ = ("_type_name", "_accessor_name", "_field_sort")

    def __init__(
        self,
        type_name: str,
        accessor_name: str,
        domain: tuple[SortRef, ...],
        field_sort: SortRef,
    ) -> None:
        super().__init__(accessor_name, domain, field_sort)
        self._type_name = type_name
        self._accessor_name = accessor_name
        self._field_sort = field_sort

    def __call__(self, *args: ExprRef) -> ExprRef:
        if len(args) != 1:
            raise TypeError(f"{self._accessor_name} expects 1 arg, got {len(args)}")
        arg = args[0]
        ast = InductiveAccessorNode(self._type_name, self._accessor_name, arg._ast)
        return ExprRef(ast, self._field_sort, arg._vars)


class _InductiveRecognizerDecl(FuncDeclRef):
    """Recognizer for an inductive type — produces InductiveRecognizerNode."""

    __slots__ = ("_type_name", "_recognizer_name")

    def __init__(
        self,
        type_name: str,
        recognizer_name: str,
        domain: tuple[SortRef, ...],
        result_sort: SortRef,
    ) -> None:
        super().__init__(recognizer_name, domain, result_sort)
        self._type_name = type_name
        self._recognizer_name = recognizer_name

    def __call__(self, *args: ExprRef) -> BoolRef:
        if len(args) != 1:
            raise TypeError(f"{self._recognizer_name} expects 1 arg, got {len(args)}")
        arg = args[0]
        ast = InductiveRecognizerNode(self._type_name, self._recognizer_name, arg._ast)
        return BoolRef(ast, arg._vars)


def Function(name: str, *sorts: SortRef) -> FuncDeclRef:
    """Declare an uninterpreted function.

    ``Function('f', IntSort(), IntSort(), BoolSort())`` declares
    ``f : Int -> Int -> Prop``.
    """
    if len(sorts) < 2:
        raise TypeError("Function needs at least a domain and range sort")
    return FuncDeclRef(name, tuple(sorts[:-1]), sorts[-1])


# ---------------------------------------------------------------------------
# Variable constructors
# ---------------------------------------------------------------------------


def Int(name: str) -> ArithRef:
    s = IntSort()
    return ArithRef(_AstVar(name), s, frozenset([(name, s._ast_sort)]))


def Ints(names: str) -> tuple[ArithRef, ...]:
    return tuple(Int(n) for n in names.split())


def Nat(name: str) -> ArithRef:
    s = NatSort()
    return ArithRef(_AstVar(name), s, frozenset([(name, s._ast_sort)]))


def Real(name: str) -> ArithRef:
    s = RealSort()
    return ArithRef(_AstVar(name), s, frozenset([(name, s._ast_sort)]))


def Reals(names: str) -> tuple[ArithRef, ...]:
    return tuple(Real(n) for n in names.split())


def Bool(name: str) -> BoolRef:
    return BoolRef(_AstVar(name), frozenset([(name, PropSort())]))


def Bools(names: str) -> tuple[BoolRef, ...]:
    return tuple(Bool(n) for n in names.split())


def BitVec(name: str, width: int) -> BitVecRef:
    s = BitVecSort(width)
    return BitVecRef(_AstVar(name), s, frozenset([(name, s._ast_sort)]))


def BitVecs(names: str, width: int) -> tuple[BitVecRef, ...]:
    return tuple(BitVec(n, width) for n in names.split())


def Array(name: str, domain: SortRef, range_sort: SortRef) -> ArrayRef:
    s = ArraySort(domain, range_sort)
    return ArrayRef(_AstVar(name), s, frozenset([(name, s._ast_sort)]))


def Const(name: str, sort: SortRef) -> ExprRef:
    v: frozenset[tuple[str, ASTSort]] = frozenset([(name, sort._ast_sort)])
    # If the sort is uninterpreted, also track it as a free type variable.
    if isinstance(sort, UninterpretedSortRef) and isinstance(
        sort._ast_sort, UninterpASTSort
    ):
        v = v | frozenset([(sort._ast_sort.name, TypeASTSort())])
    if isinstance(sort, BoolSortRef):
        return BoolRef(_AstVar(name), v)
    if isinstance(sort, ArithSortRef):
        return ArithRef(_AstVar(name), sort, v)
    if isinstance(sort, BitVecSortRef):
        return BitVecRef(_AstVar(name), sort, v)
    if isinstance(sort, ArraySortRef):
        return ArrayRef(_AstVar(name), sort, v)
    if isinstance(sort, StringSortRef):
        return StringRef(_AstVar(name), v)
    if isinstance(sort, CharSortRef):
        return CharRef(_AstVar(name), v)
    if isinstance(sort, SeqSortRef):
        return SeqRef(_AstVar(name), sort, v)
    if isinstance(sort, DatatypeSortRef):
        return DatatypeRef(_AstVar(name), sort, v)
    return ExprRef(_AstVar(name), sort, v)


def Consts(names: str, sort: SortRef) -> tuple[ExprRef, ...]:
    return tuple(Const(n, sort) for n in names.split())


# ---------------------------------------------------------------------------
# Value constructors
# ---------------------------------------------------------------------------


def IntVal(n: int) -> IntNumRef:
    return IntNumRef(IntLit(n), IntSort())


def NatVal(n: int) -> IntNumRef:
    return IntNumRef(NatLit(n), NatSort())


def RealVal(n: int | float | str) -> ArithRef:
    if isinstance(n, float):
        num, den = n.as_integer_ratio()
        return RatNumRef(num, den)
    if isinstance(n, str):
        if "/" in n:
            num, den = n.split("/", 1)
            return RatNumRef(int(num.strip()), int(den.strip()))
        n = float(n) if "." in n or "e" in n.lower() else int(n)
        return RealVal(n)
    return ArithRef(ToRealNode(IntLit(n)), RealSort())


def BoolVal(b: bool) -> BoolRef:
    return BoolRef(BoolLit(b))


def BitVecVal(val: int, width: int) -> BitVecNumRef:
    val = val % (1 << width)  # normalize to [0, 2^width)
    s = BitVecSort(width)
    return BitVecNumRef(BvLit(val, width), s)


# ---------------------------------------------------------------------------
# Array operations (SMT theory of arrays → Lean function types)
# ---------------------------------------------------------------------------


def Select(a: ExprRef, idx: ExprRef) -> ExprRef:
    """Read from array or apply lambda. Maps to function application in Lean."""
    sort = a._sort
    if isinstance(sort, ArraySortRef):
        result_sort = sort.range()
    elif isinstance(a._ast, LambdaNode):
        # Lambda expressions can be used as arrays (function abstraction)
        result_sort = a._sort
    else:
        raise TypeError(f"Select requires ArrayRef or Lambda, got {type(a)}")
    return ExprRef(
        SelectNode(a._ast, idx._ast),
        result_sort,
        _merge(a._vars, idx._vars),
    )


def Store(a: ArrayRef, idx: ExprRef, val: ExprRef) -> ArrayRef:
    """Write to array."""
    sort = a._sort
    if not isinstance(sort, ArraySortRef):
        raise TypeError(f"Store requires ArrayRef, got {type(a)}")
    merged: frozenset[tuple[str, ASTSort]] = frozenset().union(
        a._vars, idx._vars, val._vars
    )
    return ArrayRef(
        StoreNode(a._ast, idx._ast, val._ast),
        sort,
        merged,
    )


def K(domain: SortRef, val: ExprRef) -> ArrayRef:
    """Constant array (all indices map to ``val``)."""
    sort = ArraySort(domain, val._sort)
    return ArrayRef(
        ConstArrayNode(domain._ast_sort, val._ast),
        sort,
        val._vars,
    )


# ---------------------------------------------------------------------------
# Datatype builder
# ---------------------------------------------------------------------------


class _DatatypeBuilder:
    """Build an algebraic datatype backed by a real Lean inductive."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._ctors: list[
            tuple[str, tuple[tuple[str, SortRef | _DatatypeBuilder], ...]]
        ] = []

    def declare(
        self, ctor_name: str, *fields: tuple[str, SortRef | _DatatypeBuilder]
    ) -> None:
        self._ctors.append((ctor_name, tuple(fields)))

    def create(self) -> DatatypeSortRef:
        _register_inductive(self._name, self._ctors)

        sort = DatatypeSortRef(InductiveASTSort(self._name), self._name, self._ctors)

        for ctor_name, fields in self._ctors:
            if fields:
                domain = tuple(
                    DatatypeSortRef(
                        InductiveASTSort(f[1]._name), f[1]._name, f[1]._ctors
                    )
                    if isinstance(f[1], _DatatypeBuilder)
                    else f[1]
                    for f in fields
                )
                ctor = _InductiveCtorDecl(self._name, ctor_name, domain, sort)
                setattr(sort, ctor_name, ctor)
                sort._constructors.append(ctor)
            else:
                # Nullary: z3py stores a DatatypeRef directly
                val = DatatypeRef(
                    InductiveCtorNode(self._name, ctor_name, ()), sort, frozenset()
                )
                setattr(sort, ctor_name, val)
                sort._constructors.append(val)

            # Recognizer: sort.is_<ctor_name>
            rec = _InductiveRecognizerDecl(
                self._name, f"is_{ctor_name}", (sort,), BoolSort()
            )
            setattr(sort, f"is_{ctor_name}", rec)
            sort._recognizers.append(rec)

            # Accessors: sort.<field_name>
            ctor_accessors = []
            for field_name, field_sort in fields:
                if isinstance(field_sort, _DatatypeBuilder):
                    field_sort = sort  # self-reference
                acc = _InductiveAccessorDecl(
                    self._name, field_name, (sort,), field_sort
                )
                setattr(sort, field_name, acc)
                ctor_accessors.append(acc)
            sort._accessors.append(ctor_accessors)

        return sort


def Datatype(name: str) -> _DatatypeBuilder:
    return _DatatypeBuilder(name)


def CreateDatatypes(*builders: _DatatypeBuilder) -> tuple[DatatypeSortRef, ...]:
    """Create multiple (possibly mutually recursive) datatypes."""
    if len(builders) == 1 and isinstance(builders[0], (list, tuple)):
        builders = tuple(builders[0])
    return tuple(b.create() for b in builders)


def EnumSort(name: str, values: list[str] | tuple[str, ...]) -> tuple:
    """Create an enumeration sort.

    Returns (sort, list_of_enum_constants).
    """
    b = _DatatypeBuilder(name)
    for v in values:
        b.declare(v)
    sort = b.create()
    consts = [getattr(sort, v) for v in values]
    return sort, consts


def TupleSort(name: str, sorts: list[SortRef] | tuple[SortRef, ...]) -> tuple:
    """Create a tuple sort.

    Returns (sort, constructor, list_of_accessor_FuncDeclRefs).
    z3py compat: ctor name = sort name, accessors named project0, project1, ...
    """
    b = _DatatypeBuilder(name)
    fields = [(f"project{i}", s) for i, s in enumerate(sorts)]
    b.declare(name, *fields)
    sort = b.create()
    return sort, sort.constructor(0), [sort.accessor(0, i) for i in range(len(sorts))]


# ---------------------------------------------------------------------------
# Boolean combinators
# ---------------------------------------------------------------------------


def And(*args: BoolRef) -> BoolRef:
    if len(args) == 1 and isinstance(args[0], list):
        args = tuple(args[0])
    if len(args) == 0:
        return BoolVal(True)
    if len(args) == 1:
        return args[0]
    merged: frozenset[tuple[str, ASTSort]] = frozenset().union(*(a._vars for a in args))
    # Build left-associated And chain
    ast: ASTNode = args[0]._ast
    for a in args[1:]:
        ast = BinOpNode(BinOp.AND, ast, a._ast)
    return BoolRef(ast, merged)


def Or(*args: BoolRef) -> BoolRef:
    if len(args) == 1 and isinstance(args[0], list):
        args = tuple(args[0])
    if len(args) == 0:
        return BoolVal(False)
    if len(args) == 1:
        return args[0]
    merged: frozenset[tuple[str, ASTSort]] = frozenset().union(*(a._vars for a in args))
    ast: ASTNode = args[0]._ast
    for a in args[1:]:
        ast = BinOpNode(BinOp.OR, ast, a._ast)
    return BoolRef(ast, merged)


def Not(a: BoolRef) -> BoolRef:
    return BoolRef(UnOpNode(UnOp.NOT, a._ast), a._vars)


def Implies(a: BoolRef, b: BoolRef) -> BoolRef:
    return BoolRef(BinOpNode(BinOp.IMPLIES, a._ast, b._ast), _merge(a._vars, b._vars))


def Xor(a: BoolRef, b: BoolRef) -> BoolRef:
    return BoolRef(BinOpNode(BinOp.XOR, a._ast, b._ast), _merge(a._vars, b._vars))


def If(c: BoolRef, t: ExprRef, e: ExprRef) -> ExprRef:
    merged: frozenset[tuple[str, ASTSort]] = frozenset().union(
        c._vars, t._vars, e._vars
    )
    ast = IteNode(c._ast, t._ast, e._ast)
    sort = t._sort
    # Return the appropriate subclass so arithmetic/comparison ops work
    if isinstance(t, ArithRef):
        return ArithRef(ast, sort, merged)  # type: ignore[arg-type]
    if isinstance(t, BitVecRef):
        return BitVecRef(ast, sort, merged)  # type: ignore[arg-type]
    if isinstance(t, BoolRef):
        return BoolRef(ast, merged)
    return ExprRef(ast, sort, merged)


def Distinct(*args: ExprRef) -> BoolRef:
    if len(args) <= 1:
        return BoolVal(True)
    merged: frozenset[tuple[str, ASTSort]] = frozenset().union(*(a._vars for a in args))
    return BoolRef(
        DistinctNode(tuple(a._ast for a in args)),
        merged,
    )


# ---------------------------------------------------------------------------
# Quantifiers
# ---------------------------------------------------------------------------


def ForAll(
    vars: ExprRef | Sequence[ExprRef],
    body: BoolRef,
) -> QuantifierRef:
    vs = [vars] if isinstance(vars, ExprRef) else list(vars)
    return QuantifierRef("\u2200", vs, body)


def Exists(
    vars: ExprRef | Sequence[ExprRef],
    body: BoolRef,
) -> QuantifierRef:
    vs = [vars] if isinstance(vars, ExprRef) else list(vars)
    return QuantifierRef("\u2203", vs, body)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _merge(
    a: frozenset[tuple[str, ASTSort]],
    b: frozenset[tuple[str, ASTSort]],
) -> frozenset[tuple[str, ASTSort]]:
    return a | b


def _coerce_arith(v: ArithRef | int | float, sort: SortRef) -> ArithRef:
    if isinstance(v, ArithRef):
        return v
    if isinstance(v, (int, float)):
        ast_sort = sort._ast_sort
        if isinstance(ast_sort, NatASTSort):
            return ArithRef(NatLit(int(v)), sort)  # type: ignore[arg-type]
        elif isinstance(ast_sort, RealASTSort) and isinstance(v, float):
            # Convert float to exact rational to avoid truncation
            frac = Fraction(v).limit_denominator()
            if frac.denominator == 1:
                return ArithRef(ToRealNode(IntLit(frac.numerator)), sort)  # type: ignore[arg-type]
            return RatNumRef(frac.numerator, frac.denominator)
        else:
            return ArithRef(IntLit(int(v)), sort)  # type: ignore[arg-type]
    raise TypeError(f"Cannot coerce {type(v)} to ArithRef")


def _coerce_bv(v: BitVecRef | int, sort: SortRef) -> BitVecRef:
    if isinstance(v, BitVecRef):
        return v
    if isinstance(v, int) and isinstance(sort, BitVecSortRef):
        # Convert negative to unsigned two's complement
        if v < 0:
            v = (1 << sort._width) + v
        return BitVecRef(BvLit(v, sort._width), sort)
    raise TypeError(f"Cannot coerce {type(v)} to BitVecRef")


def _coerce_val(v: int | float, sort: SortRef) -> ExprRef:
    if isinstance(sort, ArithSortRef):
        return _coerce_arith(v, sort)
    if isinstance(sort, BitVecSortRef):
        return BitVecRef(BvLit(int(v), sort._width), sort)
    return ExprRef(IntLit(int(v)), sort)


def _bool_to_int(b: BoolRef, coeff: int = 1) -> ArithRef:
    """Convert BoolRef to ArithRef via If(b, coeff, 0)."""
    return ArithRef(
        IteNode(b._ast, IntLit(coeff), IntLit(0)),
        IntSort(),
        b._vars,
    )


def _coerce_arith_any(v: object) -> ArithRef:
    """Coerce int/float/BoolRef/ArithRef to ArithRef."""
    if isinstance(v, ArithRef):
        return v
    if isinstance(v, BoolRef):
        return _bool_to_int(v)
    if isinstance(v, (int, float)):
        return ArithRef(IntLit(int(v)), IntSort())
    raise TypeError(f"Cannot coerce {type(v)} to ArithRef")


def _sort_repr(s: ASTSort) -> str:
    """Human-readable string for an ASTSort."""
    if isinstance(s, PropSort):
        return "Prop"
    if isinstance(s, IntASTSort):
        return "Int"
    if isinstance(s, NatASTSort):
        return "Nat"
    if isinstance(s, RealASTSort):
        return "Real"
    if isinstance(s, BitvecASTSort):
        return f"(BitVec {s.width})"
    if isinstance(s, StringASTSort):
        return "String"
    if isinstance(s, UninterpASTSort):
        return s.name
    if isinstance(s, ArrowASTSort):
        return f"({_sort_repr(s.dom)} \u2192 {_sort_repr(s.cod)})"
    if isinstance(s, InductiveASTSort):
        return s.name
    if isinstance(s, CharASTSort):
        return "Char"
    if isinstance(s, SeqASTSort):
        return f"(Seq {_sort_repr(s.elem)})"
    return str(s)


# ---------------------------------------------------------------------------
# Bitvector functions
# ---------------------------------------------------------------------------


def LShR(a: BitVecRef, b: BitVecRef | int) -> BitVecRef:
    """Logical (unsigned) shift right."""
    return a._binop(BinOp.BSHR, b)


def ULE(a: BitVecRef, b: BitVecRef | int) -> BoolRef:
    """Unsigned less-than-or-equal."""
    b = _coerce_bv(b, a._sort)
    return BoolRef(
        BinOpNode(BinOp.LE, a._ast, b._ast),
        _merge(a._vars, b._vars),
    )


def ULT(a: BitVecRef, b: BitVecRef | int) -> BoolRef:
    """Unsigned less-than."""
    b = _coerce_bv(b, a._sort)
    return BoolRef(
        BinOpNode(BinOp.LT, a._ast, b._ast),
        _merge(a._vars, b._vars),
    )


def UGE(a: BitVecRef, b: BitVecRef | int) -> BoolRef:
    """Unsigned greater-than-or-equal."""
    b = _coerce_bv(b, a._sort)
    return BoolRef(
        BinOpNode(BinOp.GE, a._ast, b._ast),
        _merge(a._vars, b._vars),
    )


def UGT(a: BitVecRef, b: BitVecRef | int) -> BoolRef:
    """Unsigned greater-than."""
    b = _coerce_bv(b, a._sort)
    return BoolRef(
        BinOpNode(BinOp.GT, a._ast, b._ast),
        _merge(a._vars, b._vars),
    )


def UDiv(a: BitVecRef, b: BitVecRef | int) -> BitVecRef:
    """Unsigned division."""
    return a._binop(BinOp.DIV, b)


def URem(a: BitVecRef, b: BitVecRef | int) -> BitVecRef:
    """Unsigned remainder."""
    return a._binop(BinOp.MOD, b)


def Extract(hi: int, lo: int, x: BitVecRef) -> BitVecRef:
    """Extract bits [hi:lo] from a bit-vector."""
    width = hi - lo + 1
    return BitVecRef(
        ExtractNode(hi, lo, x._ast),
        BitVecSort(width),
        x._vars,
    )


def Concat(*args: BitVecRef) -> BitVecRef:
    """Concatenate two or more bit-vectors (left-fold)."""
    if len(args) < 2:
        raise TypeError("Concat requires at least 2 arguments")
    result = args[0]
    for b in args[1:]:
        a_sort = result._sort
        b_sort = b._sort
        if not isinstance(a_sort, BitVecSortRef) or not isinstance(
            b_sort, BitVecSortRef
        ):
            raise TypeError("Concat requires BitVecRef arguments")
        width = a_sort._width + b_sort._width
        result = BitVecRef(
            BinOpNode(BinOp.CONCAT, result._ast, b._ast),
            BitVecSort(width),
            _merge(result._vars, b._vars),
        )
    return result


def ZeroExt(n: int, x: BitVecRef) -> BitVecRef:
    """Zero-extend a bit-vector by n bits."""
    sort = x._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("ZeroExt requires BitVecRef")
    new_width = sort._width + n
    return BitVecRef(
        ZeroExtNode(new_width, x._ast),
        BitVecSort(new_width),
        x._vars,
    )


def SignExt(n: int, x: BitVecRef) -> BitVecRef:
    """Sign-extend a bit-vector by n bits."""
    sort = x._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("SignExt requires BitVecRef")
    new_width = sort._width + n
    return BitVecRef(
        SignExtNode(new_width, x._ast),
        BitVecSort(new_width),
        x._vars,
    )


def BV2Int(x: BitVecRef, is_signed: bool = False) -> ArithRef:
    """Convert a bit-vector to an integer.

    If is_signed is False (default, matching z3), uses unsigned (toNat).
    If is_signed is True, uses signed (toInt).
    """
    op = UnOp.BV2INT if is_signed else UnOp.BV2NAT
    return ArithRef(
        UnOpNode(op, x._ast),
        IntSort(),
        x._vars,
    )


def Int2BV(x: ArithRef, n: int) -> BitVecRef:
    """Convert an integer to a bit-vector of width n."""
    return BitVecRef(
        Int2BvNode(n, x._ast),
        BitVecSort(n),
        x._vars,
    )


def RotateLeft(a: BitVecRef, b: BitVecRef | int) -> BitVecRef:
    """Rotate left."""
    return a._binop(BinOp.ROTL, b)


def RotateRight(a: BitVecRef, b: BitVecRef | int) -> BitVecRef:
    """Rotate right."""
    return a._binop(BinOp.ROTR, b)


def SDiv(a: BitVecRef, b: BitVecRef | int) -> BitVecRef:
    """Signed division."""
    return a._binop(BinOp.SDIV, b)


def SRem(a: BitVecRef, b: BitVecRef | int) -> BitVecRef:
    """Signed remainder."""
    return a._binop(BinOp.SREM, b)


def AShr(a: BitVecRef, b: BitVecRef | int) -> BitVecRef:
    """Arithmetic shift right (sign-extending)."""
    return a._binop(BinOp.ASHR, b)


# ---------------------------------------------------------------------------
# Arithmetic functions
# ---------------------------------------------------------------------------


def Abs(x: ArithRef) -> ArithRef:
    """Absolute value via ITE."""
    return abs(x)


def ToReal(x: ArithRef) -> ArithRef:
    """Convert Int to Real."""
    return ArithRef(
        ToRealNode(x._ast),
        RealSort(),
        x._vars,
    )


def ToInt(x: ArithRef) -> ArithRef:
    """Convert Real to Int (floor)."""
    return ArithRef(
        ToIntNode(x._ast),
        IntSort(),
        x._vars,
    )


def Sum(*args: ArithRef) -> ArithRef:
    """Left-fold sum."""
    flat: list[ArithRef] = []
    for a in args:
        if isinstance(a, (list, tuple)):
            flat.extend(a)
        else:
            flat.append(a)
    if not flat:
        return IntVal(0)
    result = flat[0]
    for a in flat[1:]:
        result = result + a
    return result


def Product(*args: ArithRef) -> ArithRef:
    """Left-fold product."""
    flat: list[ArithRef] = []
    for a in args:
        if isinstance(a, (list, tuple)):
            flat.extend(a)
        else:
            flat.append(a)
    if not flat:
        return IntVal(1)
    result = flat[0]
    for a in flat[1:]:
        result = result * a
    return result


# ---------------------------------------------------------------------------
# Rational literals
# ---------------------------------------------------------------------------


def RatVal(a: int, b: int) -> RatNumRef:
    """Rational value a/b as Real division."""
    return RatNumRef(a, b)


Q = RatVal


# ---------------------------------------------------------------------------
# Vector constructors
# ---------------------------------------------------------------------------


def IntVector(prefix: str, sz: int) -> list[ArithRef]:
    """Create a vector of ``sz`` integer variables named prefix__0, ..., prefix__sz-1."""
    return [Int(f"{prefix}__{i}") for i in range(sz)]


def BoolVector(prefix: str, sz: int) -> list[BoolRef]:
    """Create a vector of ``sz`` boolean variables."""
    return [Bool(f"{prefix}__{i}") for i in range(sz)]


def RealVector(prefix: str, sz: int) -> list[ArithRef]:
    """Create a vector of ``sz`` real variables."""
    return [Real(f"{prefix}__{i}") for i in range(sz)]


# ---------------------------------------------------------------------------
# Substitute
# ---------------------------------------------------------------------------


def _substitute_ast(ast: ASTNode, mapping: dict[str, ASTNode]) -> ASTNode:
    """Walk and replace variables in an AST tree."""
    if isinstance(ast, _AstVar):
        return mapping.get(ast.name, ast)
    if isinstance(ast, (IntLit, NatLit, BoolLit, BvLit, StringLit)):
        return ast
    if isinstance(ast, BinOpNode):
        return BinOpNode(
            ast.op, _substitute_ast(ast.lhs, mapping), _substitute_ast(ast.rhs, mapping)
        )
    if isinstance(ast, UnOpNode):
        return UnOpNode(ast.op, _substitute_ast(ast.arg, mapping))
    if isinstance(ast, IteNode):
        return IteNode(
            _substitute_ast(ast.cond, mapping),
            _substitute_ast(ast.then_, mapping),
            _substitute_ast(ast.else_, mapping),
        )
    if isinstance(ast, ForAllNode):
        inner = dict(mapping)
        inner.pop(ast.name, None)
        return ForAllNode(ast.name, ast.sort, _substitute_ast(ast.body, inner))
    if isinstance(ast, ExistsNode):
        inner = dict(mapping)
        inner.pop(ast.name, None)
        return ExistsNode(ast.name, ast.sort, _substitute_ast(ast.body, inner))
    if isinstance(ast, AppNode):
        return AppNode(
            _substitute_ast(ast.func, mapping),
            tuple(_substitute_ast(a, mapping) for a in ast.args),
        )
    if isinstance(ast, DistinctNode):
        return DistinctNode(tuple(_substitute_ast(a, mapping) for a in ast.args))
    if isinstance(ast, SelectNode):
        return SelectNode(
            _substitute_ast(ast.arr, mapping), _substitute_ast(ast.idx, mapping)
        )
    if isinstance(ast, StoreNode):
        return StoreNode(
            _substitute_ast(ast.arr, mapping),
            _substitute_ast(ast.idx, mapping),
            _substitute_ast(ast.val, mapping),
        )
    if isinstance(ast, ConstArrayNode):
        return ConstArrayNode(ast.dom_sort, _substitute_ast(ast.val, mapping))
    if isinstance(ast, ExtractNode):
        return ExtractNode(ast.hi, ast.lo, _substitute_ast(ast.arg, mapping))
    if isinstance(ast, ZeroExtNode):
        return ZeroExtNode(ast.bits, _substitute_ast(ast.arg, mapping))
    if isinstance(ast, SignExtNode):
        return SignExtNode(ast.bits, _substitute_ast(ast.arg, mapping))
    if isinstance(ast, Int2BvNode):
        return Int2BvNode(ast.width, _substitute_ast(ast.arg, mapping))
    if isinstance(ast, ToRealNode):
        return ToRealNode(_substitute_ast(ast.arg, mapping))
    if isinstance(ast, ToIntNode):
        return ToIntNode(_substitute_ast(ast.arg, mapping))
    if isinstance(ast, LambdaNode):
        inner = dict(mapping)
        inner.pop(ast.name, None)
        return LambdaNode(ast.name, ast.sort, _substitute_ast(ast.body, inner))
    if isinstance(ast, StrConcatNode):
        return StrConcatNode(
            _substitute_ast(ast.lhs, mapping), _substitute_ast(ast.rhs, mapping)
        )
    if isinstance(ast, StrLenNode):
        return StrLenNode(_substitute_ast(ast.arg, mapping))
    if isinstance(ast, StrContainsNode):
        return StrContainsNode(
            _substitute_ast(ast.haystack, mapping), _substitute_ast(ast.needle, mapping)
        )
    if isinstance(ast, StrPrefixOfNode):
        return StrPrefixOfNode(
            _substitute_ast(ast.prefix_, mapping), _substitute_ast(ast.s, mapping)
        )
    if isinstance(ast, StrSuffixOfNode):
        return StrSuffixOfNode(
            _substitute_ast(ast.suffix_, mapping), _substitute_ast(ast.s, mapping)
        )
    if isinstance(ast, StrReplaceNode):
        return StrReplaceNode(
            _substitute_ast(ast.s, mapping),
            _substitute_ast(ast.old, mapping),
            _substitute_ast(ast.new_, mapping),
        )
    if isinstance(ast, StrSubstrNode):
        return StrSubstrNode(
            _substitute_ast(ast.s, mapping),
            _substitute_ast(ast.offset, mapping),
            _substitute_ast(ast.length, mapping),
        )
    if isinstance(ast, StrIndexOfNode):
        return StrIndexOfNode(
            _substitute_ast(ast.s, mapping),
            _substitute_ast(ast.substr, mapping),
            _substitute_ast(ast.offset, mapping),
        )
    if isinstance(ast, StrToIntNode):
        return StrToIntNode(_substitute_ast(ast.arg, mapping))
    if isinstance(ast, IntToStrNode):
        return IntToStrNode(_substitute_ast(ast.arg, mapping))
    if isinstance(ast, InReNode):
        return InReNode(
            _substitute_ast(ast.s, mapping), _substitute_ast(ast.re, mapping)
        )
    if isinstance(ast, ReStarNode):
        return ReStarNode(_substitute_ast(ast.arg, mapping))
    if isinstance(ast, RePlusNode):
        return RePlusNode(_substitute_ast(ast.arg, mapping))
    if isinstance(ast, ReOptionNode):
        return ReOptionNode(_substitute_ast(ast.arg, mapping))
    if isinstance(ast, ReUnionNode):
        return ReUnionNode(
            _substitute_ast(ast.a, mapping), _substitute_ast(ast.b, mapping)
        )
    if isinstance(ast, ReIntersectNode):
        return ReIntersectNode(
            _substitute_ast(ast.a, mapping), _substitute_ast(ast.b, mapping)
        )
    if isinstance(ast, ReConcatNode):
        return ReConcatNode(
            _substitute_ast(ast.a, mapping), _substitute_ast(ast.b, mapping)
        )
    if isinstance(ast, ReComplementNode):
        return ReComplementNode(_substitute_ast(ast.arg, mapping))
    if isinstance(ast, ReLoopNode):
        return ReLoopNode(_substitute_ast(ast.arg, mapping), ast.lo, ast.hi)
    if isinstance(ast, ReRangeNode):
        return ast
    return ast


def substitute(t: ExprRef, *m: tuple[ExprRef, ExprRef]) -> ExprRef:
    """Substitute expressions: substitute(t, (old1, new1), (old2, new2), ...).

    Each pair (old, new) replaces occurrences of old with new in t.
    old must be a variable (Const/Int/Bool/etc.).
    """
    mapping: dict[str, ASTNode] = {}
    for old, new in m:
        if not isinstance(old._ast, _AstVar):
            raise TypeError(f"substitute old must be a variable, got {type(old._ast)}")
        mapping[old._ast.name] = new._ast

    new_ast = _substitute_ast(t._ast, mapping)

    # Recompute free vars
    new_vars = t._vars
    for old, new in m:
        if isinstance(old._ast, _AstVar):
            old_var = (old._ast.name, old._sort._ast_sort)
            if old_var in new_vars:
                new_vars = (new_vars - frozenset([old_var])) | new._vars
    return (
        type(t)(new_ast, t._sort, new_vars)
        if not isinstance(t, BoolRef)
        else BoolRef(new_ast, new_vars)
    )


# ---------------------------------------------------------------------------
# Arithmetic extras: IsInt, Sqrt
# ---------------------------------------------------------------------------


def IsInt(a: ArithRef) -> BoolRef:
    """Check if a real value is an integer."""
    return BoolRef(
        BinOpNode(BinOp.EQ, ToIntNode(a._ast), a._ast),
        a._vars,
    )


def Sqrt(a: ArithRef) -> ArithRef:
    """Square root (represented as a^(1/2))."""
    half = RatVal(1, 2)
    return a**half


# ---------------------------------------------------------------------------
# BV extras: RepeatBitVec, BVRedAnd, BVRedOr, BvNand, BvNor, BvXnor
# ---------------------------------------------------------------------------


def RepeatBitVec(n: int, a: BitVecRef) -> BitVecRef:
    """Repeat a bit-vector n times by concatenation."""
    if n < 1:
        raise TypeError("RepeatBitVec requires n >= 1")
    result = a
    for _ in range(n - 1):
        result = Concat(result, a)
    return result


def BVRedAnd(a: BitVecRef) -> BitVecRef:
    """Reduction AND: 1-bit result, all bits ANDed."""
    sort = a._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("BVRedAnd requires BitVecRef")
    w = sort._width
    # AND all individual bits: extract each bit and AND
    result = Extract(0, 0, a)
    for i in range(1, w):
        result = result & Extract(i, i, a)
    return result


def BVRedOr(a: BitVecRef) -> BitVecRef:
    """Reduction OR: 1-bit result, all bits ORed."""
    sort = a._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("BVRedOr requires BitVecRef")
    w = sort._width
    result = Extract(0, 0, a)
    for i in range(1, w):
        result = result | Extract(i, i, a)
    return result


def BvNand(a: BitVecRef, b: BitVecRef) -> BitVecRef:
    """Bitwise NAND."""
    return ~(a & b)


def BvNor(a: BitVecRef, b: BitVecRef) -> BitVecRef:
    """Bitwise NOR."""
    return ~(a | b)


def BvXnor(a: BitVecRef, b: BitVecRef) -> BitVecRef:
    """Bitwise XNOR."""
    return ~(a ^ b)


# ---------------------------------------------------------------------------
# BV overflow predicates
# ---------------------------------------------------------------------------


def BVAddNoOverflow(a: BitVecRef, b: BitVecRef, signed: bool = False) -> BoolRef:
    """Check that a + b does not overflow."""
    sort = a._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("BVAddNoOverflow requires BitVecRef")
    w = sort._width
    if signed:
        # Signed: extend to w+1, add, check fits in w signed range
        ea = SignExt(1, a)
        eb = SignExt(1, b)
        s = ea + eb
        upper = BitVecVal((1 << (w - 1)) - 1, w + 1)
        return s <= upper
    else:
        ea = ZeroExt(1, a)
        eb = ZeroExt(1, b)
        s = ea + eb
        upper = BitVecVal((1 << w) - 1, w + 1)
        return ULE(s, upper)


def BVAddNoUnderflow(a: BitVecRef, b: BitVecRef) -> BoolRef:
    """Check that signed a + b does not underflow."""
    sort = a._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("BVAddNoUnderflow requires BitVecRef")
    w = sort._width
    ea = SignExt(1, a)
    eb = SignExt(1, b)
    s = ea + eb
    lower = BitVecVal(-(1 << (w - 1)), w + 1)
    return s >= lower


def BVSubNoOverflow(a: BitVecRef, b: BitVecRef) -> BoolRef:
    """Check that signed a - b does not overflow."""
    sort = a._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("BVSubNoOverflow requires BitVecRef")
    w = sort._width
    ea = SignExt(1, a)
    eb = SignExt(1, b)
    s = ea - eb
    upper = BitVecVal((1 << (w - 1)) - 1, w + 1)
    return s <= upper


def BVSubNoUnderflow(a: BitVecRef, b: BitVecRef, signed: bool = False) -> BoolRef:
    """Check that a - b does not underflow."""
    sort = a._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("BVSubNoUnderflow requires BitVecRef")
    w = sort._width
    if signed:
        ea = SignExt(1, a)
        eb = SignExt(1, b)
        s = ea - eb
        lower = BitVecVal(-(1 << (w - 1)), w + 1)
        return s >= lower
    else:
        return ULE(b, a)


def BVMulNoOverflow(a: BitVecRef, b: BitVecRef, signed: bool = False) -> BoolRef:
    """Check that a * b does not overflow."""
    sort = a._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("BVMulNoOverflow requires BitVecRef")
    w = sort._width
    if signed:
        ea = SignExt(w, a)
        eb = SignExt(w, b)
        p = ea * eb
        upper = BitVecVal((1 << (w - 1)) - 1, 2 * w)
        return p <= upper
    else:
        ea = ZeroExt(w, a)
        eb = ZeroExt(w, b)
        p = ea * eb
        upper = BitVecVal((1 << w) - 1, 2 * w)
        return ULE(p, upper)


def BVMulNoUnderflow(a: BitVecRef, b: BitVecRef) -> BoolRef:
    """Check that signed a * b does not underflow."""
    sort = a._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("BVMulNoUnderflow requires BitVecRef")
    w = sort._width
    ea = SignExt(w, a)
    eb = SignExt(w, b)
    p = ea * eb
    lower = BitVecVal(-(1 << (w - 1)), 2 * w)
    return p >= lower


def BVSDivNoOverflow(a: BitVecRef, b: BitVecRef) -> BoolRef:
    """Check that signed a / b does not overflow (MIN_INT / -1)."""
    sort = a._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("BVSDivNoOverflow requires BitVecRef")
    w = sort._width
    min_int = BitVecVal(1 << (w - 1), w)
    neg_one = BitVecVal((1 << w) - 1, w)
    # Overflow happens when a == MIN_INT and b == -1
    return Not(And(a == min_int, b == neg_one))


def BVSNegNoOverflow(a: BitVecRef) -> BoolRef:
    """Check that signed negation does not overflow (i.e. a != MIN_INT)."""
    sort = a._sort
    if not isinstance(sort, BitVecSortRef):
        raise TypeError("BVSNegNoOverflow requires BitVecRef")
    w = sort._width
    min_int = BitVecVal(1 << (w - 1), w)
    return Not(a == min_int)


# ---------------------------------------------------------------------------
# Pseudo-boolean constraints
# ---------------------------------------------------------------------------


def AtMost(args: Sequence[BoolRef], k: int) -> BoolRef:
    """At most k of the boolean args are true."""
    exprs = list(args)
    if not exprs:
        return BoolVal(True)
    int_args = [_bool_to_int(b) for b in exprs]
    total = Sum(*int_args)
    return total <= k


def AtLeast(args: Sequence[BoolRef], k: int) -> BoolRef:
    """At least k of the boolean args are true."""
    exprs = list(args)
    if not exprs:
        return BoolVal(k <= 0)
    int_args = [_bool_to_int(b) for b in exprs]
    total = Sum(*int_args)
    return total >= k


def PbEq(args: Sequence[tuple[BoolRef, int]], k: int) -> BoolRef:
    """Pseudo-boolean equality: sum of (coeff * bool) == k."""
    if not args:
        return BoolVal(k == 0)
    int_args = [_bool_to_int(b, c) for b, c in args]
    total = Sum(*int_args)
    return total == k


def PbLe(args: Sequence[tuple[BoolRef, int]], k: int) -> BoolRef:
    """Pseudo-boolean <=: sum of (coeff * bool) <= k."""
    if not args:
        return BoolVal(0 <= k)
    int_args = [_bool_to_int(b, c) for b, c in args]
    total = Sum(*int_args)
    return total <= k


def PbGe(args: Sequence[tuple[BoolRef, int]], k: int) -> BoolRef:
    """Pseudo-boolean >=: sum of (coeff * bool) >= k."""
    if not args:
        return BoolVal(0 >= k)
    int_args = [_bool_to_int(b, c) for b, c in args]
    total = Sum(*int_args)
    return total >= k


# ---------------------------------------------------------------------------
# FreshConst
# ---------------------------------------------------------------------------

_fresh_counter = 0


def FreshConst(sort: SortRef, prefix: str = "c") -> ExprRef:
    """Create a fresh constant with a unique name."""
    global _fresh_counter
    _fresh_counter += 1
    return Const(f"{prefix}!{_fresh_counter}", sort)


def FreshInt(prefix: str = "x") -> ArithRef:
    """Create a fresh integer constant."""
    r = FreshConst(IntSort(), prefix)
    assert isinstance(r, ArithRef)
    return r


def FreshBool(prefix: str = "b") -> BoolRef:
    """Create a fresh boolean constant."""
    r = FreshConst(BoolSort(), prefix)
    assert isinstance(r, BoolRef)
    return r


def FreshReal(prefix: str = "x") -> ArithRef:
    """Create a fresh real constant."""
    r = FreshConst(RealSort(), prefix)
    assert isinstance(r, ArithRef)
    return r


# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------


def Lambda(vars: ExprRef | Sequence[ExprRef], body: ExprRef) -> ExprRef:
    """Build a lambda expression (maps to Lean lambda)."""
    vs = [vars] if isinstance(vars, ExprRef) else list(vars)
    bound_names = frozenset(
        (v._ast.name, v._sort._ast_sort) for v in vs if isinstance(v._ast, _AstVar)
    )
    free = body._vars - bound_names
    for v in vs:
        free = free | v._vars - bound_names

    ast: ASTNode = body._ast
    for v in reversed(vs):
        ast = LambdaNode(
            name=v._ast.name if isinstance(v._ast, _AstVar) else str(v._ast),
            sort=v._sort._ast_sort,
            body=ast,
        )
    return ExprRef(ast, body._sort, free)


# ---------------------------------------------------------------------------
# Array Map / AsArray
# ---------------------------------------------------------------------------


def Map(f: FuncDeclRef, *arrays: ArrayRef) -> ArrayRef:
    """Apply f element-wise over arrays, producing a new array."""
    if not arrays:
        raise TypeError("Map requires at least one array")
    dom = arrays[0]._sort
    if not isinstance(dom, ArraySortRef):
        raise TypeError("Map requires ArrayRef arguments")
    i = Const("__map_idx", dom.domain())
    args = [Select(a, i) for a in arrays]
    body = f(*args)
    lam = Lambda(i, body)
    result_sort = ArraySort(dom.domain(), f._range)
    return ArrayRef(lam._ast, result_sort, lam._vars)


def AsArray(f: FuncDeclRef) -> ArrayRef:
    """Convert a function declaration to an array."""
    if len(f._domain) != 1:
        raise TypeError("AsArray requires a unary function")
    x = Const("__asarray_x", f._domain[0])
    lam = Lambda(x, f(x))
    result_sort = ArraySort(f._domain[0], f._range)
    return ArrayRef(lam._ast, result_sort, lam._vars)


# ---------------------------------------------------------------------------
# String sorts and expressions
# ---------------------------------------------------------------------------


class StringSortRef(SortRef):
    """String sort."""

    pass


class StringRef(ExprRef):
    """String expression."""

    __slots__ = ()

    def __init__(
        self,
        ast: ASTNode,
        vars: frozenset[tuple[str, ASTSort]] = frozenset(),
    ) -> None:
        super().__init__(ast, StringSort(), vars)

    def __add__(self, other: StringRef) -> StringRef:
        if isinstance(other, str):
            other = StringVal(other)
        return StringRef(
            StrConcatNode(self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __radd__(self, other: str) -> StringRef:
        return StringVal(other) + self


def StringSort() -> StringSortRef:
    return StringSortRef(StringASTSort())


def String(name: str) -> StringRef:
    """Create a string variable."""
    return StringRef(_AstVar(name), frozenset([(name, StringASTSort())]))


def Strings(names: str) -> tuple[StringRef, ...]:
    return tuple(String(n) for n in names.split())


def StringVal(s: str) -> StringRef:
    """Create a string literal."""
    return StringRef(StringLit(s))


def Length(s: StringRef | SeqRef) -> ArithRef:
    """String or sequence length."""
    if isinstance(s, SeqRef):
        return ArithRef(SeqLenNode(s._ast), IntSort(), s._vars)
    return ArithRef(StrLenNode(s._ast), IntSort(), s._vars)


def Contains(s: StringRef | SeqRef, t: StringRef | SeqRef) -> BoolRef:
    """Check if s contains t."""
    if isinstance(s, SeqRef) or isinstance(t, SeqRef):
        return BoolRef(SeqContainsNode(s._ast, t._ast), _merge(s._vars, t._vars))
    return BoolRef(StrContainsNode(s._ast, t._ast), _merge(s._vars, t._vars))


def PrefixOf(pre: StringRef | SeqRef, s: StringRef | SeqRef) -> BoolRef:
    """Check if pre is a prefix of s."""
    if isinstance(pre, SeqRef) or isinstance(s, SeqRef):
        return BoolRef(SeqPrefixOfNode(pre._ast, s._ast), _merge(pre._vars, s._vars))
    return BoolRef(StrPrefixOfNode(pre._ast, s._ast), _merge(pre._vars, s._vars))


def SuffixOf(suf: StringRef | SeqRef, s: StringRef | SeqRef) -> BoolRef:
    """Check if suf is a suffix of s."""
    if isinstance(suf, SeqRef) or isinstance(s, SeqRef):
        return BoolRef(SeqSuffixOfNode(suf._ast, s._ast), _merge(suf._vars, s._vars))
    return BoolRef(StrSuffixOfNode(suf._ast, s._ast), _merge(suf._vars, s._vars))


def Replace(s: StringRef, old: StringRef, new: StringRef) -> StringRef:
    """Replace first occurrence of old with new in s."""
    merged: frozenset[tuple[str, ASTSort]] = frozenset().union(
        s._vars, old._vars, new._vars
    )
    return StringRef(StrReplaceNode(s._ast, old._ast, new._ast), merged)


def SubString(
    s: StringRef, offset: ArithRef | int, length: ArithRef | int
) -> StringRef:
    """Extract substring."""
    if isinstance(offset, int):
        offset = IntVal(offset)
    if isinstance(length, int):
        length = IntVal(length)
    merged: frozenset[tuple[str, ASTSort]] = frozenset().union(
        s._vars, offset._vars, length._vars
    )
    return StringRef(StrSubstrNode(s._ast, offset._ast, length._ast), merged)


def IndexOf(s: StringRef, substr: StringRef, offset: ArithRef | int = 0) -> ArithRef:
    """Find index of substr in s starting at offset."""
    if isinstance(offset, int):
        offset = IntVal(offset)
    merged: frozenset[tuple[str, ASTSort]] = frozenset().union(
        s._vars, substr._vars, offset._vars
    )
    return ArithRef(StrIndexOfNode(s._ast, substr._ast, offset._ast), IntSort(), merged)


def StrToInt(s: StringRef) -> ArithRef:
    """Convert string to integer."""
    return ArithRef(StrToIntNode(s._ast), IntSort(), s._vars)


def IntToStr(i: ArithRef) -> StringRef:
    """Convert integer to string."""
    return StringRef(IntToStrNode(i._ast), i._vars)


def StrConcat(*args: StringRef) -> StringRef:
    """Concatenate strings."""
    if not args:
        return StringVal("")
    result = args[0]
    for a in args[1:]:
        result = result + a
    return result


# ---------------------------------------------------------------------------
# Regex sorts and expressions
# ---------------------------------------------------------------------------


class ReSort(SortRef):
    """Regex sort (opaque — for type tagging only)."""

    pass


class ReRef(ExprRef):
    """Regex expression."""

    __slots__ = ()

    def __init__(
        self,
        ast: ASTNode,
        vars: frozenset[tuple[str, ASTSort]] = frozenset(),
    ) -> None:
        super().__init__(ast, ReSort(StringASTSort()), vars)


def Re(s: StringRef) -> ReRef:
    """Regex matching exactly the string s."""
    # A string literal used as a regex pattern
    return ReRef(s._ast, s._vars)


def Star(re: ReRef) -> ReRef:
    """Kleene star."""
    return ReRef(ReStarNode(re._ast), re._vars)


def Plus(re: ReRef) -> ReRef:
    """One or more repetitions."""
    return ReRef(RePlusNode(re._ast), re._vars)


def Option(re: ReRef) -> ReRef:
    """Zero or one."""
    return ReRef(ReOptionNode(re._ast), re._vars)


def Union(*args: ReRef) -> ReRef:
    """Union of regexes."""
    if len(args) < 2:
        raise TypeError("Union requires at least 2 arguments")
    result = args[0]
    for a in args[1:]:
        result = ReRef(ReUnionNode(result._ast, a._ast), _merge(result._vars, a._vars))
    return result


def Intersect(*args: ReRef) -> ReRef:
    """Intersection of regexes."""
    if len(args) < 2:
        raise TypeError("Intersect requires at least 2 arguments")
    result = args[0]
    for a in args[1:]:
        result = ReRef(
            ReIntersectNode(result._ast, a._ast), _merge(result._vars, a._vars)
        )
    return result


def Complement(re: ReRef) -> ReRef:
    """Complement of regex."""
    return ReRef(ReComplementNode(re._ast), re._vars)


def Range(lo: str, hi: str) -> ReRef:
    """Character range [lo..hi]."""
    return ReRef(ReRangeNode(lo, hi))


def Loop(re: ReRef, lo: int, hi: int) -> ReRef:
    """Bounded repetition."""
    return ReRef(ReLoopNode(re._ast, lo, hi), re._vars)


def InRe(s: StringRef, re: ReRef) -> BoolRef:
    """String membership in regex."""
    return BoolRef(InReNode(s._ast, re._ast), _merge(s._vars, re._vars))


def AllChar(sort: SortRef | None = None) -> ReRef:
    """Regex matching any single character."""
    return Range(chr(0), chr(0x10FFFF))


# ---------------------------------------------------------------------------
# Predicate functions
# ---------------------------------------------------------------------------


def is_expr(a: object) -> bool:
    return isinstance(a, ExprRef)


def is_true(a: ExprRef) -> bool:
    return isinstance(a._ast, BoolLit) and a._ast.val is True


def is_false(a: ExprRef) -> bool:
    return isinstance(a._ast, BoolLit) and a._ast.val is False


def is_int(a: ExprRef) -> bool:
    return isinstance(a._sort._ast_sort, IntASTSort)


def is_real(a: ExprRef) -> bool:
    return isinstance(a._sort._ast_sort, RealASTSort)


def is_bool(a: ExprRef) -> bool:
    return isinstance(a, BoolRef)


def is_bv(a: ExprRef) -> bool:
    return isinstance(a, BitVecRef)


def is_array(a: ExprRef) -> bool:
    return isinstance(a, ArrayRef)


def is_const(a: ExprRef) -> bool:
    return isinstance(a._ast, _AstVar)


def is_var(a: ExprRef) -> bool:
    return isinstance(a._ast, _AstVar)


def is_quantifier(a: ExprRef) -> bool:
    return isinstance(a._ast, (ForAllNode, ExistsNode))


def is_eq(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op == BinOp.EQ


def is_distinct(a: ExprRef) -> bool:
    return isinstance(a._ast, DistinctNode)


def is_and(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op == BinOp.AND


def is_or(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op == BinOp.OR


def is_not(a: ExprRef) -> bool:
    return isinstance(a._ast, UnOpNode) and a._ast.op == UnOp.NOT


def is_implies(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op == BinOp.IMPLIES


def is_add(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op == BinOp.ADD


def is_mul(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op == BinOp.MUL


def is_sub(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op == BinOp.SUB


def is_div(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op in (BinOp.DIV, BinOp.EDIV)


def is_string(a: ExprRef) -> bool:
    return isinstance(a, StringRef)


def is_string_value(a: ExprRef) -> bool:
    return isinstance(a._ast, StringLit)


def is_arith(a: object) -> bool:
    """True if a is an arithmetic expression (Int, Nat, or Real)."""
    return isinstance(a, ArithRef)


def is_sort(a: object) -> bool:
    """True if a is a sort reference."""
    return isinstance(a, SortRef)


def is_app(a: object) -> bool:
    """True if a is a function application."""
    return isinstance(a, ExprRef) and isinstance(a._ast, AppNode)


def is_func_decl(a: object) -> bool:
    """True if a is a function declaration."""
    return isinstance(a, FuncDeclRef)


def is_int_value(a: ExprRef) -> bool:
    """True if a is a concrete integer literal."""
    return isinstance(a._ast, IntLit) and isinstance(a._sort._ast_sort, IntASTSort)


def _unwrap_toreal(node: ASTNode) -> ASTNode:
    """Unwrap a ToRealNode wrapper, if present."""
    return node.arg if isinstance(node, ToRealNode) else node


def is_rational_value(a: ExprRef) -> bool:
    """True if a is a rational value (division of two integer literals on Real sort)."""
    if not isinstance(a._sort._ast_sort, RealASTSort):
        return False
    ast = a._ast
    if isinstance(ast, ToRealNode):
        ast = ast.arg
    if isinstance(ast, IntLit):
        return True
    if isinstance(ast, BinOpNode) and ast.op == BinOp.DIV:
        return isinstance(_unwrap_toreal(ast.lhs), IntLit) and isinstance(
            _unwrap_toreal(ast.rhs), IntLit
        )
    return False


def is_bv_value(a: ExprRef) -> bool:
    """True if a is a concrete bitvector literal."""
    return isinstance(a._ast, BvLit)


def is_le(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op == BinOp.LE


def is_lt(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op == BinOp.LT


def is_ge(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op == BinOp.GE


def is_gt(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op == BinOp.GT


def is_mod(a: ExprRef) -> bool:
    return isinstance(a._ast, BinOpNode) and a._ast.op in (BinOp.MOD, BinOp.EMOD)


def is_idiv(a: ExprRef) -> bool:
    """True for integer division."""
    return isinstance(a._ast, BinOpNode) and a._ast.op in (BinOp.DIV, BinOp.EDIV)


# ---------------------------------------------------------------------------
# AST introspection helpers
# ---------------------------------------------------------------------------


def _ast_children(node: ASTNode) -> list[ASTNode]:
    """Return child AST nodes of an AST node."""
    if isinstance(node, (_AstVar, IntLit, NatLit, BoolLit, BvLit, StringLit)):
        return []
    if isinstance(node, BinOpNode):
        return [node.lhs, node.rhs]
    if isinstance(node, UnOpNode):
        return [node.arg]
    if isinstance(node, IteNode):
        return [node.cond, node.then_, node.else_]
    if isinstance(node, (ForAllNode, ExistsNode)):
        return [node.body]
    if isinstance(node, AppNode):
        return list(node.args)
    if isinstance(node, DistinctNode):
        return list(node.args)
    if isinstance(node, SelectNode):
        return [node.arr, node.idx]
    if isinstance(node, StoreNode):
        return [node.arr, node.idx, node.val]
    if isinstance(node, ConstArrayNode):
        return [node.val]
    if isinstance(node, ExtractNode):
        return [node.arg]
    if isinstance(node, (ZeroExtNode, SignExtNode)):
        return [node.arg]
    if isinstance(node, Int2BvNode):
        return [node.arg]
    if isinstance(node, (ToRealNode, ToIntNode)):
        return [node.arg]
    if isinstance(node, LambdaNode):
        return [node.body]
    if isinstance(node, StrLenNode):
        return [node.arg]
    if isinstance(node, StrContainsNode):
        return [node.haystack, node.needle]
    if isinstance(node, StrPrefixOfNode):
        return [node.prefix_, node.s]
    if isinstance(node, StrSuffixOfNode):
        return [node.suffix_, node.s]
    if isinstance(node, StrReplaceNode):
        return [node.s, node.old, node.new_]
    if isinstance(node, StrConcatNode):
        return [node.lhs, node.rhs]
    if isinstance(node, StrSubstrNode):
        return [node.s, node.offset, node.length]
    if isinstance(node, StrIndexOfNode):
        return [node.s, node.substr, node.offset]
    if isinstance(node, (StrToIntNode, IntToStrNode)):
        return [node.arg]
    if isinstance(node, (ReStarNode, RePlusNode, ReOptionNode, ReComplementNode)):
        return [node.arg]
    if isinstance(node, (ReUnionNode, ReIntersectNode, ReConcatNode)):
        return [node.a, node.b]
    if isinstance(node, ReLoopNode):
        return [node.arg]
    if isinstance(node, InReNode):
        return [node.s, node.re]
    if isinstance(node, ReRangeNode):
        return []
    # Char nodes
    if isinstance(node, CharLit):
        return []
    if isinstance(node, (CharToNatNode, CharFromBvNode, CharIsDigitNode)):
        return [node.arg]
    # Seq nodes
    if isinstance(node, SeqEmptyNode):
        return []
    if isinstance(node, SeqUnitNode):
        return [node.arg]
    if isinstance(node, SeqLenNode):
        return [node.arg]
    if isinstance(node, SeqConcatNode):
        return [node.lhs, node.rhs]
    if isinstance(node, SeqContainsNode):
        return [node.haystack, node.needle]
    if isinstance(node, SeqPrefixOfNode):
        return [node.prefix_, node.s]
    if isinstance(node, SeqSuffixOfNode):
        return [node.suffix_, node.s]
    if isinstance(node, SeqNthNode):
        return [node.s, node.idx]
    return []


def _ast_decl_name(node: ASTNode) -> str:
    """Return the 'declaration name' for an AST node."""
    if isinstance(node, BinOpNode):
        return node.op
    if isinstance(node, UnOpNode):
        return node.op
    if isinstance(node, IteNode):
        return "if"
    if isinstance(node, AppNode):
        if isinstance(node.func, _AstVar):
            return node.func.name
        return "app"
    if isinstance(node, DistinctNode):
        return "distinct"
    if isinstance(node, SelectNode):
        return "select"
    if isinstance(node, StoreNode):
        return "store"
    if isinstance(node, ConstArrayNode):
        return "const"
    if isinstance(node, ExtractNode):
        return "extract"
    if isinstance(node, ZeroExtNode):
        return "zero_extend"
    if isinstance(node, SignExtNode):
        return "sign_extend"
    if isinstance(node, Int2BvNode):
        return "int2bv"
    if isinstance(node, ToRealNode):
        return "to_real"
    if isinstance(node, ToIntNode):
        return "to_int"
    if isinstance(node, LambdaNode):
        return "lambda"
    if isinstance(node, ForAllNode):
        return "forall"
    if isinstance(node, ExistsNode):
        return "exists"
    if isinstance(node, _AstVar):
        return node.name
    if isinstance(node, (IntLit, NatLit)):
        return "Int"
    if isinstance(node, BoolLit):
        return "Bool"
    if isinstance(node, BvLit):
        return "bv"
    if isinstance(node, StringLit):
        return "String"
    if isinstance(node, StrLenNode):
        return "str.len"
    if isinstance(node, StrContainsNode):
        return "str.contains"
    if isinstance(node, StrPrefixOfNode):
        return "str.prefixof"
    if isinstance(node, StrSuffixOfNode):
        return "str.suffixof"
    if isinstance(node, StrReplaceNode):
        return "str.replace"
    if isinstance(node, StrConcatNode):
        return "str.++"
    if isinstance(node, StrSubstrNode):
        return "str.substr"
    if isinstance(node, StrIndexOfNode):
        return "str.indexof"
    if isinstance(node, StrToIntNode):
        return "str.to_int"
    if isinstance(node, IntToStrNode):
        return "int.to_str"
    if isinstance(node, ReStarNode):
        return "re.*"
    if isinstance(node, RePlusNode):
        return "re.+"
    if isinstance(node, ReOptionNode):
        return "re.opt"
    if isinstance(node, ReUnionNode):
        return "re.union"
    if isinstance(node, ReIntersectNode):
        return "re.inter"
    if isinstance(node, ReConcatNode):
        return "re.++"
    if isinstance(node, ReRangeNode):
        return "re.range"
    if isinstance(node, ReComplementNode):
        return "re.comp"
    if isinstance(node, ReLoopNode):
        return "re.loop"
    if isinstance(node, InReNode):
        return "str.in_re"
    return type(node).__name__


def _make_typed_expr(
    ast: ASTNode, sort: SortRef, vars: frozenset[tuple[str, ASTSort]]
) -> ExprRef:
    """Create appropriately-typed ExprRef subclass for a sort."""
    if isinstance(sort, BoolSortRef):
        return BoolRef(ast, vars)
    if isinstance(sort, ArithSortRef):
        return ArithRef(ast, sort, vars)
    if isinstance(sort, BitVecSortRef):
        return BitVecRef(ast, sort, vars)
    if isinstance(sort, StringSortRef):
        return StringRef(ast, vars)
    if isinstance(sort, CharSortRef):
        return CharRef(ast, vars)
    if isinstance(sort, SeqSortRef):
        return SeqRef(ast, sort, vars)
    return ExprRef(ast, sort, vars)


def _sort_from_ast_sort(ast_sort: ASTSort) -> SortRef:
    """Create a SortRef from an ASTSort."""
    if isinstance(ast_sort, PropSort):
        return BoolSortRef(ast_sort)
    if isinstance(ast_sort, IntASTSort):
        return ArithSortRef(ast_sort)
    if isinstance(ast_sort, NatASTSort):
        return ArithSortRef(ast_sort)
    if isinstance(ast_sort, RealASTSort):
        return ArithSortRef(ast_sort)
    if isinstance(ast_sort, BitvecASTSort):
        return BitVecSortRef(ast_sort.width)
    if isinstance(ast_sort, StringASTSort):
        return StringSortRef(ast_sort)
    if isinstance(ast_sort, ArrowASTSort):
        return ArraySortRef(
            _sort_from_ast_sort(ast_sort.dom),
            _sort_from_ast_sort(ast_sort.cod),
        )
    if isinstance(ast_sort, UninterpASTSort):
        return UninterpretedSortRef(ast_sort)
    if isinstance(ast_sort, CharASTSort):
        return CharSortRef(ast_sort)
    if isinstance(ast_sort, SeqASTSort):
        return SeqSortRef(_sort_from_ast_sort(ast_sort.elem))
    return SortRef(ast_sort)


def _child_expr(child_ast: ASTNode, parent: ExprRef, idx: int) -> ExprRef:
    """Wrap a child AST node as an ExprRef with best-effort sort inference."""
    pvars = parent._vars

    # Literals: sort is known directly
    if isinstance(child_ast, IntLit):
        psort = parent._sort._ast_sort
        if isinstance(psort, RealASTSort):
            return ArithRef(child_ast, RealSort(), pvars)
        return ArithRef(child_ast, IntSort(), pvars)
    if isinstance(child_ast, NatLit):
        return ArithRef(child_ast, NatSort(), pvars)
    if isinstance(child_ast, BoolLit):
        return BoolRef(child_ast, pvars)
    if isinstance(child_ast, BvLit):
        return BitVecRef(child_ast, BitVecSort(child_ast.width), pvars)
    if isinstance(child_ast, StringLit):
        return StringRef(child_ast, pvars)

    # Variables: look up sort in parent's free vars
    if isinstance(child_ast, _AstVar):
        for vname, vsort in pvars:
            if vname == child_ast.name:
                s = _sort_from_ast_sort(vsort)
                return _make_typed_expr(child_ast, s, pvars)
        return ExprRef(child_ast, parent._sort, pvars)

    # Compound children: infer from parent node type
    past = parent._ast
    if isinstance(past, BinOpNode):
        if past.op in (BinOp.AND, BinOp.OR, BinOp.IMPLIES, BinOp.XOR):
            return BoolRef(child_ast, pvars)
        if past.op in (BinOp.LT, BinOp.LE, BinOp.GT, BinOp.GE, BinOp.EQ, BinOp.NE):
            return ExprRef(child_ast, SortRef(IntASTSort()), pvars)
        return _make_typed_expr(child_ast, parent._sort, pvars)
    if isinstance(past, UnOpNode):
        if past.op == UnOp.NOT:
            return BoolRef(child_ast, pvars)
        return _make_typed_expr(child_ast, parent._sort, pvars)
    if isinstance(past, IteNode):
        if idx == 0:
            return BoolRef(child_ast, pvars)
        return _make_typed_expr(child_ast, parent._sort, pvars)

    return ExprRef(child_ast, parent._sort, pvars)


# ---------------------------------------------------------------------------
# Repr helpers
# ---------------------------------------------------------------------------


def _ast_repr(node: ASTNode) -> str:
    """Human-readable string for an ASTNode (for debugging)."""
    if isinstance(node, _AstVar):
        return node.name
    if isinstance(node, IntLit):
        return str(node.val)
    if isinstance(node, NatLit):
        return str(node.val)
    if isinstance(node, BoolLit):
        return "True" if node.val else "False"
    if isinstance(node, BvLit):
        return f"{node.val}#{node.width}"
    if isinstance(node, BinOpNode):
        return f"({_ast_repr(node.lhs)} {node.op} {_ast_repr(node.rhs)})"
    if isinstance(node, UnOpNode):
        return f"({node.op} {_ast_repr(node.arg)})"
    if isinstance(node, IteNode):
        return f"(if {_ast_repr(node.cond)} then {_ast_repr(node.then_)} else {_ast_repr(node.else_)})"
    if isinstance(node, ForAllNode):
        return f"(\u2200 {node.name}, {_ast_repr(node.body)})"
    if isinstance(node, ExistsNode):
        return f"(\u2203 {node.name}, {_ast_repr(node.body)})"
    if isinstance(node, AppNode):
        args = " ".join(_ast_repr(a) for a in node.args)
        return f"({_ast_repr(node.func)} {args})"
    if isinstance(node, DistinctNode):
        args = ", ".join(_ast_repr(a) for a in node.args)
        return f"(distinct {args})"
    if isinstance(node, SelectNode):
        return f"(select {_ast_repr(node.arr)} {_ast_repr(node.idx)})"
    if isinstance(node, StoreNode):
        return (
            f"(store {_ast_repr(node.arr)} {_ast_repr(node.idx)} {_ast_repr(node.val)})"
        )
    if isinstance(node, ConstArrayNode):
        return f"(const-array {_ast_repr(node.val)})"
    if isinstance(node, ExtractNode):
        return f"(extract {node.hi} {node.lo} {_ast_repr(node.arg)})"
    if isinstance(node, ZeroExtNode):
        return f"(zero-ext {node.bits} {_ast_repr(node.arg)})"
    if isinstance(node, SignExtNode):
        return f"(sign-ext {node.bits} {_ast_repr(node.arg)})"
    if isinstance(node, Int2BvNode):
        return f"(int2bv {node.width} {_ast_repr(node.arg)})"
    if isinstance(node, ToRealNode):
        return f"(to-real {_ast_repr(node.arg)})"
    if isinstance(node, ToIntNode):
        return f"(to-int {_ast_repr(node.arg)})"
    if isinstance(node, LambdaNode):
        return f"(λ {node.name}, {_ast_repr(node.body)})"
    if isinstance(node, StringLit):
        return f'"{node.val}"'
    if isinstance(node, StrLenNode):
        return f"(str.len {_ast_repr(node.arg)})"
    if isinstance(node, StrContainsNode):
        return f"(str.contains {_ast_repr(node.haystack)} {_ast_repr(node.needle)})"
    if isinstance(node, StrPrefixOfNode):
        return f"(str.prefixof {_ast_repr(node.prefix_)} {_ast_repr(node.s)})"
    if isinstance(node, StrSuffixOfNode):
        return f"(str.suffixof {_ast_repr(node.suffix_)} {_ast_repr(node.s)})"
    if isinstance(node, StrReplaceNode):
        return f"(str.replace {_ast_repr(node.s)} {_ast_repr(node.old)} {_ast_repr(node.new_)})"
    if isinstance(node, StrConcatNode):
        return f"(str.++ {_ast_repr(node.lhs)} {_ast_repr(node.rhs)})"
    if isinstance(node, StrSubstrNode):
        return f"(str.substr {_ast_repr(node.s)} {_ast_repr(node.offset)} {_ast_repr(node.length)})"
    if isinstance(node, StrIndexOfNode):
        return f"(str.indexof {_ast_repr(node.s)} {_ast_repr(node.substr)} {_ast_repr(node.offset)})"
    if isinstance(node, StrToIntNode):
        return f"(str.to_int {_ast_repr(node.arg)})"
    if isinstance(node, IntToStrNode):
        return f"(int.to_str {_ast_repr(node.arg)})"
    if isinstance(node, ReStarNode):
        return f"(re.* {_ast_repr(node.arg)})"
    if isinstance(node, RePlusNode):
        return f"(re.+ {_ast_repr(node.arg)})"
    if isinstance(node, ReOptionNode):
        return f"(re.opt {_ast_repr(node.arg)})"
    if isinstance(node, ReUnionNode):
        return f"(re.union {_ast_repr(node.a)} {_ast_repr(node.b)})"
    if isinstance(node, ReIntersectNode):
        return f"(re.inter {_ast_repr(node.a)} {_ast_repr(node.b)})"
    if isinstance(node, ReConcatNode):
        return f"(re.++ {_ast_repr(node.a)} {_ast_repr(node.b)})"
    if isinstance(node, ReRangeNode):
        return f"(re.range {node.lo} {node.hi})"
    if isinstance(node, ReComplementNode):
        return f"(re.comp {_ast_repr(node.arg)})"
    if isinstance(node, ReLoopNode):
        return f"(re.loop {_ast_repr(node.arg)} {node.lo} {node.hi})"
    if isinstance(node, InReNode):
        return f"(str.in_re {_ast_repr(node.s)} {_ast_repr(node.re)})"
    if isinstance(node, InductiveCtorNode):
        if node.args:
            args = " ".join(_ast_repr(a) for a in node.args)
            return f"({node.type_name}.{node.ctor_name} {args})"
        return f"{node.type_name}.{node.ctor_name}"
    if isinstance(node, InductiveAccessorNode):
        return f"({node.type_name}.{node.accessor_name} {_ast_repr(node.arg)})"
    if isinstance(node, InductiveRecognizerNode):
        return f"({node.type_name}.{node.recognizer_name} {_ast_repr(node.arg)})"
    return str(node)


# ---------------------------------------------------------------------------
# Context (z3py multi-context compat — lean.py uses a single global context)
# ---------------------------------------------------------------------------


class Context:
    """Z3 context — lean.py uses a single global context."""

    def __init__(self, *args: Any, **kws: Any) -> None:
        pass

    def __del__(self) -> None:
        pass

    def __repr__(self) -> str:
        return "Context()"


_main_ctx: Context | None = None


def main_ctx() -> Context:
    """Return the main context."""
    global _main_ctx
    if _main_ctx is None:
        _main_ctx = Context()
    return _main_ctx


def get_ctx(ctx: Context | None = None) -> Context:
    """Return ctx if not None, else main context."""
    return ctx if ctx is not None else main_ctx()


# ---------------------------------------------------------------------------
# AstRef / AstVector / AstMap
# ---------------------------------------------------------------------------

AstRef = ExprRef  # z3py base for all AST objects


class AstVector:
    """Vector of AST nodes."""

    def __init__(self, ctx: Context | None = None) -> None:
        self._elems: list[Any] = []

    def push(self, v: Any) -> None:
        self._elems.append(v)

    def __len__(self) -> int:
        return len(self._elems)

    def __getitem__(self, i: int) -> Any:
        return self._elems[i]

    def __setitem__(self, i: int, v: Any) -> None:
        self._elems[i] = v

    def __iter__(self):
        return iter(self._elems)

    def __contains__(self, v: Any) -> bool:
        return v in self._elems

    def __repr__(self) -> str:
        return f"[{', '.join(repr(e) for e in self._elems)}]"

    def translate(self, ctx: Context) -> AstVector:
        return self

    def sexpr(self) -> str:
        return repr(self)


class AstMap:
    """Map from AST nodes to AST nodes."""

    def __init__(self, ctx: Context | None = None) -> None:
        self._map: dict[Any, Any] = {}

    def __setitem__(self, k: Any, v: Any) -> None:
        self._map[k] = v

    def __getitem__(self, k: Any) -> Any:
        return self._map[k]

    def __contains__(self, k: Any) -> bool:
        return k in self._map

    def __len__(self) -> int:
        return len(self._map)

    def __repr__(self) -> str:
        return repr(self._map)

    def erase(self, k: Any) -> None:
        self._map.pop(k, None)

    def reset(self) -> None:
        self._map.clear()

    def keys(self):
        return list(self._map.keys())


# ---------------------------------------------------------------------------
# Floating-point sorts and expressions
# ---------------------------------------------------------------------------

_rm_ast_sort = UninterpASTSort("RoundingMode")


class FPSortRef(SortRef):
    """Floating-point sort (IEEE 754)."""

    __slots__ = ("_ebits", "_sbits")

    def __init__(self, ebits: int, sbits: int) -> None:
        super().__init__(FpASTSort(ebits, sbits))
        self._ebits = ebits
        self._sbits = sbits

    def ebits(self) -> int:
        return self._ebits

    def sbits(self) -> int:
        return self._sbits


class FPRef(ExprRef):
    """Floating-point expression."""

    __slots__ = ()

    def __init__(
        self,
        ast: ASTNode,
        sort: SortRef,
        vars: frozenset[tuple[str, ASTSort]] = frozenset(),
    ) -> None:
        super().__init__(ast, sort, vars)

    def sort(self) -> FPSortRef:
        s = self._sort
        if isinstance(s, FPSortRef):
            return s
        return FPSortRef(0, 0)

    def ebits(self) -> int:
        return self.sort().ebits()

    def sbits(self) -> int:
        return self.sort().sbits()

    def __add__(self, other: Any) -> FPRef:
        return fpAdd(RNE(), self, other)

    def __radd__(self, other: Any) -> FPRef:
        return fpAdd(RNE(), other, self)

    def __sub__(self, other: Any) -> FPRef:
        return fpSub(RNE(), self, other)

    def __mul__(self, other: Any) -> FPRef:
        return fpMul(RNE(), self, other)

    def __truediv__(self, other: Any) -> FPRef:
        return fpDiv(RNE(), self, other)

    def __neg__(self) -> FPRef:
        return fpNeg(self)

    def __pos__(self) -> FPRef:
        return self

    def __abs__(self) -> FPRef:
        return fpAbs(self)

    def __lt__(self, other: Any) -> BoolRef:
        return fpLT(self, other)

    def __le__(self, other: Any) -> BoolRef:
        return fpLEQ(self, other)

    def __gt__(self, other: Any) -> BoolRef:
        return fpGT(self, other)

    def __ge__(self, other: Any) -> BoolRef:
        return fpGEQ(self, other)


class FPNumRef(FPRef):
    """Floating-point numeral."""

    __slots__ = ()

    def as_string(self) -> str:
        return repr(self)

    def isNaN(self) -> bool:
        if isinstance(self._ast, FpLitNode):
            return math.isnan(struct.unpack("<d", struct.pack("<Q", self._ast.bits))[0])
        return False

    def isInf(self) -> bool:
        if isinstance(self._ast, FpLitNode):
            return math.isinf(struct.unpack("<d", struct.pack("<Q", self._ast.bits))[0])
        return False

    def isZero(self) -> bool:
        if isinstance(self._ast, FpLitNode):
            return struct.unpack("<d", struct.pack("<Q", self._ast.bits))[0] == 0.0
        return False


class FPRMRef(ExprRef):
    """Floating-point rounding mode."""

    __slots__ = ()

    def __init__(self, name: str) -> None:
        super().__init__(
            _AstVar(name),
            SortRef(_rm_ast_sort),
            frozenset(),
        )


def FPSort(ebits: int, sbits: int, ctx: Context | None = None) -> FPSortRef:
    return FPSortRef(ebits, sbits)


def Float16(ctx: Context | None = None) -> FPSortRef:
    return FPSort(5, 11)


def Float32(ctx: Context | None = None) -> FPSortRef:
    return FPSort(8, 24)


def Float64(ctx: Context | None = None) -> FPSortRef:
    return FPSort(11, 53)


def Float128(ctx: Context | None = None) -> FPSortRef:
    return FPSort(15, 113)


def FP(name: str, fpsort: FPSortRef, ctx: Context | None = None) -> FPRef:
    return FPRef(_AstVar(name), fpsort, frozenset([(name, fpsort._ast_sort)]))


def FPs(names: str, fpsort: FPSortRef, ctx: Context | None = None) -> tuple[FPRef, ...]:
    return tuple(FP(n, fpsort) for n in names.split())


def FPVal(
    val: float | int | str,
    sort: FPSortRef | None = None,
    ctx: Context | None = None,
) -> FPNumRef:
    if sort is None:
        sort = Float64()
    val = float(val) if isinstance(val, (int, str)) else val
    bits = struct.unpack("<Q", struct.pack("<d", val))[0]
    return FPNumRef(FpLitNode(bits, sort.ebits(), sort.sbits()), sort, frozenset())


def fpNaN(sort: FPSortRef, ctx: Context | None = None) -> FPNumRef:
    bits = struct.unpack("<Q", struct.pack("<d", float("nan")))[0]
    return FPNumRef(FpLitNode(bits, sort.ebits(), sort.sbits()), sort, frozenset())


def fpPlusInfinity(sort: FPSortRef, ctx: Context | None = None) -> FPNumRef:
    bits = struct.unpack("<Q", struct.pack("<d", float("inf")))[0]
    return FPNumRef(FpLitNode(bits, sort.ebits(), sort.sbits()), sort, frozenset())


def fpMinusInfinity(sort: FPSortRef, ctx: Context | None = None) -> FPNumRef:
    bits = struct.unpack("<Q", struct.pack("<d", float("-inf")))[0]
    return FPNumRef(FpLitNode(bits, sort.ebits(), sort.sbits()), sort, frozenset())


def fpPlusZero(sort: FPSortRef, ctx: Context | None = None) -> FPNumRef:
    bits = struct.unpack("<Q", struct.pack("<d", 0.0))[0]
    return FPNumRef(FpLitNode(bits, sort.ebits(), sort.sbits()), sort, frozenset())


def fpMinusZero(sort: FPSortRef, ctx: Context | None = None) -> FPNumRef:
    bits = struct.unpack("<Q", struct.pack("<d", -0.0))[0]
    return FPNumRef(FpLitNode(bits, sort.ebits(), sort.sbits()), sort, frozenset())


# Rounding modes
def RoundNearestTiesToEven(ctx: Context | None = None) -> FPRMRef:
    return FPRMRef("RoundNearestTiesToEven")


def RNE(ctx: Context | None = None) -> FPRMRef:
    return RoundNearestTiesToEven(ctx)


def RoundNearestTiesToAway(ctx: Context | None = None) -> FPRMRef:
    return FPRMRef("RoundNearestTiesToAway")


def RNA(ctx: Context | None = None) -> FPRMRef:
    return RoundNearestTiesToAway(ctx)


def RoundTowardPositive(ctx: Context | None = None) -> FPRMRef:
    return FPRMRef("RoundTowardPositive")


def RTP(ctx: Context | None = None) -> FPRMRef:
    return RoundTowardPositive(ctx)


def RoundTowardNegative(ctx: Context | None = None) -> FPRMRef:
    return FPRMRef("RoundTowardNegative")


def RTN(ctx: Context | None = None) -> FPRMRef:
    return RoundTowardNegative(ctx)


def RoundTowardZero(ctx: Context | None = None) -> FPRMRef:
    return FPRMRef("RoundTowardZero")


def RTZ(ctx: Context | None = None) -> FPRMRef:
    return RoundTowardZero(ctx)


def _fp_op(name: str, *args: ExprRef) -> FPRef:
    # Filter out rounding mode args — we only support RNE
    real_args = [a for a in args if not isinstance(a, FPRMRef)]
    fp_args = [a for a in real_args if isinstance(a, FPRef)]
    sort = fp_args[0]._sort if fp_args else FPSort(11, 53)
    merged: frozenset[tuple[str, ASTSort]] = frozenset()
    for a in real_args:
        if isinstance(a, ExprRef):
            merged = merged | a._vars
    return FPRef(FpOpNode(name, tuple(a._ast for a in real_args)), sort, merged)


def _fp_pred(name: str, *args: ExprRef) -> BoolRef:
    real_args = [a for a in args if not isinstance(a, FPRMRef)]
    merged: frozenset[tuple[str, ASTSort]] = frozenset()
    for a in real_args:
        if isinstance(a, ExprRef):
            merged = merged | a._vars
    return BoolRef(FpOpNode(name, tuple(a._ast for a in real_args)), merged)


# FP arithmetic
def fpAdd(rm: FPRMRef, a: FPRef, b: FPRef, ctx: Context | None = None) -> FPRef:
    return _fp_op("fpAdd", rm, a, b)


def fpSub(rm: FPRMRef, a: FPRef, b: FPRef, ctx: Context | None = None) -> FPRef:
    return _fp_op("fpSub", rm, a, b)


def fpMul(rm: FPRMRef, a: FPRef, b: FPRef, ctx: Context | None = None) -> FPRef:
    return _fp_op("fpMul", rm, a, b)


def fpDiv(rm: FPRMRef, a: FPRef, b: FPRef, ctx: Context | None = None) -> FPRef:
    return _fp_op("fpDiv", rm, a, b)


def fpNeg(a: FPRef, ctx: Context | None = None) -> FPRef:
    return _fp_op("fpNeg", a)


def fpAbs(a: FPRef, ctx: Context | None = None) -> FPRef:
    return _fp_op("fpAbs", a)


def fpSqrt(rm: FPRMRef, a: FPRef, ctx: Context | None = None) -> FPRef:
    return _fp_op("fpSqrt", rm, a)


def fpFMA(
    rm: FPRMRef, a: FPRef, b: FPRef, c: FPRef, ctx: Context | None = None
) -> FPRef:
    return _fp_op("fpFMA", rm, a, b, c)


def fpRem(a: FPRef, b: FPRef, ctx: Context | None = None) -> FPRef:
    return _fp_op("fpRem", a, b)


def fpMin(a: FPRef, b: FPRef, ctx: Context | None = None) -> FPRef:
    return _fp_op("fpMin", a, b)


def fpMax(a: FPRef, b: FPRef, ctx: Context | None = None) -> FPRef:
    return _fp_op("fpMax", a, b)


# FP comparisons
def fpLEQ(a: FPRef, b: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpLEQ", a, b)


def fpLT(a: FPRef, b: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpLT", a, b)


def fpGEQ(a: FPRef, b: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpGEQ", a, b)


def fpGT(a: FPRef, b: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpGT", a, b)


def fpEQ(a: FPRef, b: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpEQ", a, b)


# FP predicates
def fpIsNaN(a: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpIsNaN", a)


def fpIsInf(a: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpIsInf", a)


def fpIsZero(a: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpIsZero", a)


def fpIsNormal(a: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpIsNormal", a)


def fpIsSubnormal(a: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpIsSubnormal", a)


def fpIsNegative(a: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpIsNegative", a)


def fpIsPositive(a: FPRef, ctx: Context | None = None) -> BoolRef:
    return _fp_pred("fpIsPositive", a)


# FP conversions
def fpToReal(a: FPRef, ctx: Context | None = None) -> ArithRef:
    return ArithRef(AppNode(_AstVar("fpToReal"), (a._ast,)), RealSort(), a._vars)


def fpToSBV(
    rm: FPRMRef, a: FPRef, sort: BitVecSortRef, ctx: Context | None = None
) -> BitVecRef:
    return BitVecRef(
        AppNode(_AstVar("fpToSBV"), (rm._ast, a._ast)), sort, _merge(rm._vars, a._vars)
    )


def fpToUBV(
    rm: FPRMRef, a: FPRef, sort: BitVecSortRef, ctx: Context | None = None
) -> BitVecRef:
    return BitVecRef(
        AppNode(_AstVar("fpToUBV"), (rm._ast, a._ast)), sort, _merge(rm._vars, a._vars)
    )


def fpToFP(
    rm: Any, a: Any, sort: FPSortRef | None = None, ctx: Context | None = None
) -> FPRef:
    if sort is None:
        sort = Float64()
    merged: frozenset[tuple[str, ASTSort]] = frozenset()
    args_ast: list[ASTNode] = []
    for x in (rm, a):
        if isinstance(x, ExprRef):
            merged = merged | x._vars
            args_ast.append(x._ast)
    return FPRef(AppNode(_AstVar("fpToFP"), tuple(args_ast)), sort, merged)


def fpBVToFP(a: BitVecRef, sort: FPSortRef, ctx: Context | None = None) -> FPRef:
    return FPRef(AppNode(_AstVar("fpBVToFP"), (a._ast,)), sort, a._vars)


def fpFPToFP(
    rm: FPRMRef, a: FPRef, sort: FPSortRef, ctx: Context | None = None
) -> FPRef:
    return FPRef(
        AppNode(_AstVar("fpFPToFP"), (rm._ast, a._ast)), sort, _merge(rm._vars, a._vars)
    )


def fpRealToFP(
    rm: FPRMRef, a: ArithRef, sort: FPSortRef, ctx: Context | None = None
) -> FPRef:
    return FPRef(
        AppNode(_AstVar("fpRealToFP"), (rm._ast, a._ast)),
        sort,
        _merge(rm._vars, a._vars),
    )


def fpSignedToFP(
    rm: FPRMRef, a: ExprRef, sort: FPSortRef, ctx: Context | None = None
) -> FPRef:
    return FPRef(
        AppNode(_AstVar("fpSignedToFP"), (rm._ast, a._ast)),
        sort,
        _merge(rm._vars, a._vars),
    )


def fpUnsignedToFP(
    rm: FPRMRef, a: ExprRef, sort: FPSortRef, ctx: Context | None = None
) -> FPRef:
    return FPRef(
        AppNode(_AstVar("fpUnsignedToFP"), (rm._ast, a._ast)),
        sort,
        _merge(rm._vars, a._vars),
    )


def fpNEQ(a: FPRef, b: FPRef, ctx: Context | None = None) -> BoolRef:
    """FP not-equal: Not(fpEQ(a, b))."""
    return Not(fpEQ(a, b))


def fpRoundToIntegral(rm: FPRMRef, a: FPRef, ctx: Context | None = None) -> FPRef:
    """Round FP value to integral."""
    return _fp_op("fpRoundToIntegral", rm, a)


def fpToIEEEBV(a: FPRef, ctx: Context | None = None) -> BitVecRef:
    """Convert FP to IEEE BV representation."""
    sort = a._sort
    if isinstance(sort, FPSortRef):
        w = sort.ebits() + sort.sbits()
    else:
        w = 64
    return BitVecRef(AppNode(_AstVar("fpToIEEEBV"), (a._ast,)), BitVecSort(w), a._vars)


def fpInfinity(sort: FPSortRef, negative: bool) -> FPNumRef:
    """Generalized infinity constructor."""
    if negative:
        return fpMinusInfinity(sort)
    return fpPlusInfinity(sort)


def fpZero(sort: FPSortRef, negative: bool) -> FPNumRef:
    """Generalized zero constructor."""
    if negative:
        return fpMinusZero(sort)
    return fpPlusZero(sort)


def fpFP(
    sgn: BitVecRef, exp: BitVecRef, sig: BitVecRef, ctx: Context | None = None
) -> FPRef:
    """Construct FP from sign/exponent/significand BitVecs."""
    exp_sort = exp._sort
    sig_sort = sig._sort
    ebits = exp_sort._width if isinstance(exp_sort, BitVecSortRef) else 11
    sbits = (sig_sort._width if isinstance(sig_sort, BitVecSortRef) else 52) + 1
    sort = FPSort(ebits, sbits)
    merged: frozenset[tuple[str, ASTSort]] = frozenset().union(
        sgn._vars, exp._vars, sig._vars
    )
    return FPRef(AppNode(_AstVar("fpFP"), (sgn._ast, exp._ast, sig._ast)), sort, merged)


def fpToFPUnsigned(
    rm: FPRMRef, a: ExprRef, sort: FPSortRef, ctx: Context | None = None
) -> FPRef:
    """Alias for fpUnsignedToFP."""
    return fpUnsignedToFP(rm, a, sort, ctx)


# FP sort aliases
FloatHalf = Float16
FloatSingle = Float32
FloatDouble = Float64
FloatQuadruple = Float128


# FP config
_default_rounding_mode: FPRMRef = RoundNearestTiesToEven()
_default_fp_sort: FPSortRef = Float64()


def get_default_rounding_mode() -> FPRMRef:
    """Return the current default rounding mode."""
    return _default_rounding_mode


def set_default_rounding_mode(rm: FPRMRef) -> None:
    """Set the default rounding mode."""
    global _default_rounding_mode
    _default_rounding_mode = rm


def get_default_fp_sort() -> FPSortRef:
    """Return the current default FP sort."""
    return _default_fp_sort


def set_default_fp_sort(sort: FPSortRef) -> None:
    """Set the default FP sort."""
    global _default_fp_sort
    _default_fp_sort = sort


# ---------------------------------------------------------------------------
# Set API (fully functional via arrays of Bool)
# ---------------------------------------------------------------------------


def SetSort(s: SortRef) -> ArraySortRef:
    """Set sort — implemented as Array(s, Bool)."""
    return ArraySort(s, BoolSort())


def EmptySet(s: SortRef) -> ArrayRef:
    """Empty set — constant array of False."""
    return K(s, BoolVal(False))


def FullSet(s: SortRef) -> ArrayRef:
    """Full set — constant array of True."""
    return K(s, BoolVal(True))


def IsMember(e: ExprRef, s: ArrayRef) -> BoolRef:
    """Set membership test."""
    result = Select(s, e)
    return BoolRef(result._ast, result._vars)


def SetAdd(s: ArrayRef, e: ExprRef) -> ArrayRef:
    """Add element to set."""
    return Store(s, e, BoolVal(True))


def SetDel(s: ArrayRef, e: ExprRef) -> ArrayRef:
    """Remove element from set."""
    return Store(s, e, BoolVal(False))


def SetUnion(a: ArrayRef, b: ArrayRef, ctx: Context | None = None) -> ArrayRef:
    """Set union via lambda."""
    sort = a._sort
    if not isinstance(sort, ArraySortRef):
        raise TypeError("SetUnion requires set (array) arguments")
    dom = sort.domain()
    i = Const("__su_i", dom)
    a_i = BoolRef(SelectNode(a._ast, i._ast), _merge(a._vars, i._vars))
    b_i = BoolRef(SelectNode(b._ast, i._ast), _merge(b._vars, i._vars))
    body = Or(a_i, b_i)
    lam = Lambda(i, body)
    merged = a._vars | b._vars
    return ArrayRef(lam._ast, sort, merged)


def SetIntersect(a: ArrayRef, b: ArrayRef, ctx: Context | None = None) -> ArrayRef:
    """Set intersection via lambda."""
    sort = a._sort
    if not isinstance(sort, ArraySortRef):
        raise TypeError("SetIntersect requires set (array) arguments")
    dom = sort.domain()
    i = Const("__si_i", dom)
    a_i = BoolRef(SelectNode(a._ast, i._ast), _merge(a._vars, i._vars))
    b_i = BoolRef(SelectNode(b._ast, i._ast), _merge(b._vars, i._vars))
    body = And(a_i, b_i)
    lam = Lambda(i, body)
    merged = a._vars | b._vars
    return ArrayRef(lam._ast, sort, merged)


def SetComplement(s: ArrayRef, ctx: Context | None = None) -> ArrayRef:
    """Set complement via lambda."""
    sort = s._sort
    if not isinstance(sort, ArraySortRef):
        raise TypeError("SetComplement requires set (array) argument")
    dom = sort.domain()
    i = Const("__sc_i", dom)
    s_i = BoolRef(SelectNode(s._ast, i._ast), _merge(s._vars, i._vars))
    body = Not(s_i)
    lam = Lambda(i, body)
    return ArrayRef(lam._ast, sort, s._vars)


def SetDifference(a: ArrayRef, b: ArrayRef, ctx: Context | None = None) -> ArrayRef:
    """Set difference: a \\ b."""
    return SetIntersect(a, SetComplement(b))


def IsSubset(a: ArrayRef, b: ArrayRef) -> BoolRef:
    """Check if a is a subset of b."""
    sort = a._sort
    if not isinstance(sort, ArraySortRef):
        raise TypeError("IsSubset requires set (array) arguments")
    dom = sort.domain()
    i = Const("__iss_i", dom)
    a_i = BoolRef(SelectNode(a._ast, i._ast), _merge(a._vars, i._vars))
    b_i = BoolRef(SelectNode(b._ast, i._ast), _merge(b._vars, i._vars))
    return ForAll([i], Implies(a_i, b_i))


def SetHasSize(s: ArrayRef, n: int) -> BoolRef:
    """Check if set has exactly n elements."""
    raise NotImplementedError("SetHasSize requires cardinality constraints")


# FiniteSet aliases (implemented via Set operations)
FiniteSetSort = SetSort
FiniteSetEmpty = EmptySet
FiniteSetUnion = SetUnion
FiniteSetIntersect = SetIntersect
FiniteSetDifference = SetDifference
FiniteSetMember = IsMember
FiniteSetSubset = IsSubset
In = IsMember


def Singleton(e: ExprRef, sort: SortRef | None = None) -> ArrayRef:
    """Create a singleton set containing e."""
    if sort is None:
        sort = e._sort
    return SetAdd(EmptySet(sort), e)


def FiniteSetSize(s: ArrayRef) -> ArithRef:
    """Set cardinality (not supported)."""
    raise NotImplementedError("FiniteSetSize (cardinality) is not supported")


def FiniteSetMap(f: FuncDeclRef, s: ArrayRef) -> ArrayRef:
    """Map function f over finite set s."""
    sort = s._sort
    if not isinstance(sort, ArraySortRef):
        raise TypeError("FiniteSetMap requires set (array) argument")
    dom = sort.domain()
    i = Const("__fsm_i", f._range)
    x = Const("__fsm_x", dom)
    # {f(x) | x in s} == {y | exists x, x in s /\ f(x) == y}
    # Simplified: use Lambda over the range
    fx = f(x)
    mem = BoolRef(SelectNode(s._ast, x._ast), _merge(s._vars, x._vars))
    body = And(mem, fx == i)
    exists_body = Exists([x], body)
    lam = Lambda(i, exists_body)
    result_sort = SetSort(f._range)
    return ArrayRef(
        lam._ast, result_sort, _merge(s._vars, frozenset([(f._name, f._ast_sort)]))
    )


def FiniteSetFilter(f: FuncDeclRef, s: ArrayRef) -> ArrayRef:
    """Filter finite set s with predicate f."""
    sort = s._sort
    if not isinstance(sort, ArraySortRef):
        raise TypeError("FiniteSetFilter requires set (array) argument")
    dom = sort.domain()
    i = Const("__fsf_i", dom)
    mem = BoolRef(SelectNode(s._ast, i._ast), _merge(s._vars, i._vars))
    pred = f(i)
    pred_bool = (
        BoolRef(pred._ast, pred._vars) if not isinstance(pred, BoolRef) else pred
    )
    body = And(mem, pred_bool)
    lam = Lambda(i, body)
    return ArrayRef(
        lam._ast, sort, _merge(s._vars, frozenset([(f._name, f._ast_sort)]))
    )


def FiniteSetRange(f: Any, lo: Any, hi: Any) -> ArrayRef:
    """Finite set range (not supported)."""
    raise NotImplementedError("FiniteSetRange is not supported")


def is_finite_set(a: object) -> bool:
    """True if a is a finite set (array with Bool range)."""
    if not isinstance(a, ExprRef):
        return False
    sort = a._sort
    return isinstance(sort, ArraySortRef) and isinstance(
        sort.range()._ast_sort, PropSort
    )


def is_finite_set_sort(s: object) -> bool:
    """True if s is a finite set sort (array sort with Bool range)."""
    return isinstance(s, ArraySortRef) and isinstance(s.range()._ast_sort, PropSort)


# ---------------------------------------------------------------------------
# Char sort and operations
# ---------------------------------------------------------------------------


class CharSortRef(SortRef):
    """Character sort."""

    pass


class CharRef(ExprRef):
    """Character expression."""

    __slots__ = ()

    def __init__(
        self,
        ast: ASTNode,
        vars: frozenset[tuple[str, ASTSort]] = frozenset(),
    ) -> None:
        super().__init__(ast, CharSortRef(CharASTSort()), vars)

    def to_int(self) -> ArithRef:
        """Convert char to integer (code point)."""
        return CharToInt(self)

    def to_bv(self) -> BitVecRef:
        """Convert char to 21-bit bitvector."""
        return CharToBv(self)

    def is_digit(self) -> BoolRef:
        """Check if char is a digit."""
        return CharIsDigit(self)

    def __le__(self, other: object) -> BoolRef:
        if isinstance(other, ExprRef):
            lhs = CharToNatNode(self._ast)
            rhs = CharToNatNode(other._ast)
            return BoolRef(
                BinOpNode(BinOp.LE, lhs, rhs),
                _merge(self._vars, other._vars),
            )
        return NotImplemented


def CharSort(ctx: Context | None = None) -> CharSortRef:
    return CharSortRef(CharASTSort())


def CharVal(ch: str | int, ctx: Context | None = None) -> CharRef:
    if isinstance(ch, str):
        ch = ord(ch[0]) if ch else 0
    return CharRef(CharLit(ch))


def CharFromBv(bv: BitVecRef, ctx: Context | None = None) -> CharRef:
    return CharRef(CharFromBvNode(bv._ast), bv._vars)


def CharToBv(ch: ExprRef, ctx: Context | None = None) -> BitVecRef:
    return BitVecRef(
        CharToNatNode(ch._ast), BitVecSort(21), ch._vars
    )


def CharToInt(ch: ExprRef, ctx: Context | None = None) -> ArithRef:
    return ArithRef(CharToNatNode(ch._ast), IntSort(), ch._vars)


def CharIsDigit(ch: ExprRef, ctx: Context | None = None) -> BoolRef:
    return BoolRef(CharIsDigitNode(ch._ast), ch._vars)


# ---------------------------------------------------------------------------
# Sequence API
# ---------------------------------------------------------------------------


class SeqSortRef(SortRef):
    """Sequence sort."""

    __slots__ = ("_elem",)

    def __init__(self, elem: SortRef) -> None:
        super().__init__(SeqASTSort(elem._ast_sort))
        self._elem = elem

    def basis(self) -> SortRef:
        """Return the element sort."""
        return self._elem

    def is_string(self) -> bool:
        """True if this is Seq(Char), i.e. String."""
        return isinstance(self._elem, CharSortRef)


class SeqRef(ExprRef):
    """Sequence expression."""

    __slots__ = ()

    def __init__(
        self,
        ast: ASTNode,
        sort: SeqSortRef,
        vars: frozenset[tuple[str, ASTSort]] = frozenset(),
    ) -> None:
        super().__init__(ast, sort, vars)

    def __add__(self, other: SeqRef) -> SeqRef:
        if not isinstance(other, SeqRef):
            return NotImplemented
        return SeqRef(
            SeqConcatNode(self._ast, other._ast),
            self._sort,  # type: ignore[arg-type]
            _merge(self._vars, other._vars),
        )

    def __getitem__(self, idx: ArithRef | int) -> ExprRef:
        if isinstance(idx, int):
            idx = IntVal(idx)
        sort = self._sort
        elem_sort = sort._elem if isinstance(sort, SeqSortRef) else IntSort()
        return ExprRef(
            SeqNthNode(self._ast, idx._ast),
            elem_sort,
            _merge(self._vars, idx._vars),
        )

    def at(self, idx: ArithRef | int) -> SeqRef:
        """Return a unit sequence at the given index."""
        elem = self[idx]
        return Unit(elem)

    def is_string(self) -> bool:
        sort = self._sort
        return isinstance(sort, SeqSortRef) and sort.is_string()


def SeqSort(s: SortRef) -> SeqSortRef | StringSortRef:
    """General sequence sort. For Char, returns StringSort."""
    if isinstance(s, CharSortRef):
        return StringSort()
    return SeqSortRef(s)


def Empty(s: SortRef) -> ExprRef:
    """Empty sequence / set."""
    if isinstance(s, StringSortRef):
        return StringVal("")
    if isinstance(s, ArraySortRef):
        return EmptySet(s.domain())
    if isinstance(s, SeqSortRef):
        return SeqRef(SeqEmptyNode(s._elem._ast_sort), s)
    return StringVal("")


def Full(s: SortRef) -> ExprRef:
    """Full sequence."""
    if isinstance(s, ArraySortRef):
        return FullSet(s.domain())
    raise NotImplementedError("Full not supported for this sort")


def Unit(e: ExprRef) -> ExprRef:
    """Single-element sequence."""
    if isinstance(e, StringRef):
        return e
    if isinstance(e, CharRef):
        return e
    return SeqRef(SeqUnitNode(e._ast), SeqSortRef(e._sort), e._vars)


def SubSeq(s: StringRef, lo: ArithRef | int, length: ArithRef | int) -> StringRef:
    """Extract subsequence (alias for SubString)."""
    return SubString(s, lo, length)


def SeqMap(f: FuncDeclRef, s: ExprRef) -> ExprRef:
    """Map function over sequence."""
    return ExprRef(
        AppNode(_AstVar("seq.map"), (_AstVar(f._name), s._ast)),
        s._sort,
        s._vars | frozenset([(f._name, f._ast_sort)]),
    )


def SeqMapI(f: FuncDeclRef, s: ExprRef) -> ExprRef:
    """Map indexed function over sequence."""
    return ExprRef(
        AppNode(_AstVar("seq.mapi"), (_AstVar(f._name), s._ast)),
        s._sort,
        s._vars | frozenset([(f._name, f._ast_sort)]),
    )


def SeqFoldLeft(f: FuncDeclRef, init: ExprRef, s: ExprRef) -> ExprRef:
    """Left fold over sequence."""
    merged = init._vars | s._vars | frozenset([(f._name, f._ast_sort)])
    return ExprRef(
        AppNode(_AstVar("seq.foldl"), (_AstVar(f._name), init._ast, s._ast)),
        init._sort,
        merged,
    )


def SeqFoldLeftI(f: FuncDeclRef, init: ExprRef, s: ExprRef) -> ExprRef:
    """Indexed left fold over sequence."""
    merged = init._vars | s._vars | frozenset([(f._name, f._ast_sort)])
    return ExprRef(
        AppNode(_AstVar("seq.foldli"), (_AstVar(f._name), init._ast, s._ast)),
        init._sort,
        merged,
    )


# ---------------------------------------------------------------------------
# Finite domain API
# ---------------------------------------------------------------------------


class _FiniteDomainSortRef(SortRef):
    """Finite domain sort with stored size."""

    __slots__ = ("_size",)

    def __init__(self, name: str, sz: int) -> None:
        super().__init__(FinDomainASTSort(sz))
        self._size = sz

    def size(self) -> int:
        return self._size


def FiniteDomainSort(
    name: str, sz: int, ctx: Context | None = None
) -> _FiniteDomainSortRef:
    return _FiniteDomainSortRef(name, sz)


def FiniteDomainVal(val: int, sort: SortRef, ctx: Context | None = None) -> ExprRef:
    if not isinstance(sort, _FiniteDomainSortRef):
        raise TypeError("Expected FiniteDomainSort")
    return ExprRef(FinDomainLit(val, sort._size), sort, frozenset())


def FiniteDomainSize(sort: SortRef, ctx: Context | None = None) -> int:
    """Return size of finite domain sort."""
    if isinstance(sort, _FiniteDomainSortRef):
        return sort.size()
    raise TypeError("Expected FiniteDomainSort")


# ---------------------------------------------------------------------------
# RecFunction / RecAddDefinition
# ---------------------------------------------------------------------------

_rec_definitions: dict[str, tuple[list[ExprRef], ExprRef]] = {}


def RecFunction(name: str, *sorts: SortRef) -> FuncDeclRef:
    """Declare a recursive function."""
    return Function(name, *sorts)


def RecAddDefinition(f: FuncDeclRef, args: list[ExprRef], body: ExprRef) -> None:
    """Add definition to a recursive function."""
    _rec_definitions[f._name] = (args, body)


# ---------------------------------------------------------------------------
# De Bruijn Var
# ---------------------------------------------------------------------------


def Var(idx: int, sort: SortRef) -> ExprRef:
    """Create a de Bruijn indexed variable.

    Since lean.py uses named variables, this creates a variable named
    ``__db_<idx>`` with the given sort.
    """
    return Const(f"__db_{idx}", sort)


def get_var_index(a: ExprRef) -> int:
    """Get de Bruijn index of a bound variable."""
    name = repr(a)
    if name.startswith("__db_"):
        return int(name[5:])
    raise TypeError("Not a de Bruijn variable")


# ---------------------------------------------------------------------------
# MultiPattern / DisjointSum
# ---------------------------------------------------------------------------


def MultiPattern(*args: ExprRef) -> ExprRef:
    """Quantifier multi-pattern."""
    if args:
        return args[0]
    return BoolVal(True)


def DisjointSum(name: str, sorts: list[SortRef], ctx: Any = None) -> tuple:
    """Create a disjoint sum datatype.

    z3py compat: sorts is list[SortRef], ctors named inject0/inject1/...,
    accessors named project0/project1/...
    Returns (sort, [(ctor, accessor), ...]).
    """
    b = _DatatypeBuilder(name)
    for i, s in enumerate(sorts):
        b.declare(f"inject{i}", (f"project{i}", s))
    sort = b.create()
    return sort, [(sort.constructor(i), sort.accessor(i, 0)) for i in range(len(sorts))]


# ---------------------------------------------------------------------------
# Additional predicates
# ---------------------------------------------------------------------------


def is_ast(a: object) -> bool:
    return isinstance(a, (ExprRef, SortRef, FuncDeclRef))


def is_fp(a: object) -> bool:
    return isinstance(a, FPRef)


def is_fprm(a: object) -> bool:
    return isinstance(a, FPRMRef)


def is_fp_value(a: object) -> bool:
    return isinstance(a, FPNumRef)


def is_seq(a: object) -> bool:
    return isinstance(a, StringRef)


def is_re(a: object) -> bool:
    return isinstance(a, ReRef)


def is_const_array(a: object) -> bool:
    return isinstance(a, ExprRef) and isinstance(a._ast, ConstArrayNode)


def is_K(a: object) -> bool:
    return is_const_array(a)


def is_map(a: object) -> bool:
    return (
        isinstance(a, ExprRef)
        and isinstance(a._ast, LambdaNode)
        and isinstance(a, ArrayRef)
    )


def is_select(a: object) -> bool:
    return isinstance(a, ExprRef) and isinstance(a._ast, SelectNode)


def is_store(a: object) -> bool:
    return isinstance(a, ExprRef) and isinstance(a._ast, StoreNode)


def is_to_real(a: object) -> bool:
    return isinstance(a, ExprRef) and isinstance(a._ast, ToRealNode)


def is_to_int(a: object) -> bool:
    return isinstance(a, ExprRef) and isinstance(a._ast, ToIntNode)


def is_is_int(a: object) -> bool:
    """Check if expression is IsInt (ToInt(a) == a)."""
    if isinstance(a, ExprRef) and isinstance(a._ast, BinOpNode):
        return a._ast.op == BinOp.EQ and isinstance(a._ast.lhs, ToIntNode)
    return False


def is_pattern(a: object) -> bool:
    return False


def is_arith_sort(s: object) -> bool:
    """True if s is an arithmetic sort."""
    return isinstance(s, ArithSortRef)


def is_bv_sort(s: object) -> bool:
    """True if s is a bit-vector sort."""
    return isinstance(s, BitVecSortRef)


def is_array_sort(s: object) -> bool:
    """True if s is an array sort."""
    return isinstance(s, ArraySortRef)


def is_fp_sort(s: object) -> bool:
    """True if s is a floating-point sort."""
    return isinstance(s, FPSortRef)


def is_fprm_sort(s: object) -> bool:
    """True if s is a rounding mode sort."""
    if isinstance(s, SortRef):
        return (
            isinstance(s._ast_sort, UninterpASTSort)
            and s._ast_sort.name == "RoundingMode"
        )
    return False


def is_fprm_value(a: object) -> bool:
    """True if a is a rounding mode value."""
    return isinstance(a, FPRMRef)


def is_algebraic_value(a: object) -> bool:
    """True if a is an algebraic value. Always False for lean.py."""
    return False


def is_default(a: object) -> bool:
    """True if expression is a Default application."""
    return (
        isinstance(a, ExprRef)
        and isinstance(a._ast, AppNode)
        and isinstance(a._ast.func, _AstVar)
        and a._ast.func.name == "default"
    )


def is_finite_domain(a: object) -> bool:
    """True if expression's sort is a finite domain."""
    return isinstance(a, ExprRef) and isinstance(a._sort, _FiniteDomainSortRef)


def is_finite_domain_sort(s: object) -> bool:
    """True if s is a finite domain sort."""
    return isinstance(s, _FiniteDomainSortRef)


def is_finite_domain_value(a: object) -> bool:
    """True if a is a finite domain value."""
    if isinstance(a, ExprRef) and isinstance(a._ast, _AstVar):
        return a._ast.name.startswith("fd_")
    return False


# ---------------------------------------------------------------------------
# Additional string / regex operations
# ---------------------------------------------------------------------------


def LastIndexOf(s: StringRef, substr: StringRef) -> ArithRef:
    """Find last index of substr in s."""
    return ArithRef(
        AppNode(_AstVar("str.last_indexof"), (s._ast, substr._ast)),
        IntSort(),
        _merge(s._vars, substr._vars),
    )


def StrToCode(s: StringRef) -> ArithRef:
    """Convert single-char string to character code."""
    return ArithRef(
        AppNode(_AstVar("str.to_code"), (s._ast,)),
        IntSort(),
        s._vars,
    )


def StrFromCode(c: ArithRef) -> StringRef:
    """Convert character code to single-char string."""
    return StringRef(
        AppNode(_AstVar("str.from_code"), (c._ast,)),
        c._vars,
    )


def At(s: StringRef, i: ArithRef | int) -> StringRef:
    """Character at index i as a single-char string."""
    if isinstance(i, int):
        i = IntVal(i)
    return SubString(s, i, IntVal(1))


def Diff(a: ReRef, b: ReRef) -> ReRef:
    """Regex difference."""
    return Intersect(a, Complement(b))


# ---------------------------------------------------------------------------
# Structural equality
# ---------------------------------------------------------------------------


def eq(a: Any, b: Any) -> bool:
    """Structural equality between AST nodes (not SMT equality)."""
    if isinstance(a, ExprRef) and isinstance(b, ExprRef):
        return a._ast == b._ast
    if isinstance(a, SortRef) and isinstance(b, SortRef):
        return a._ast_sort == b._ast_sort
    return a is b


# ---------------------------------------------------------------------------
# Update (alias for Store)
# ---------------------------------------------------------------------------


def Update(a: ArrayRef, i: ExprRef, v: ExprRef) -> ArrayRef:
    """Update array at index i with value v (alias for Store)."""
    return Store(a, i, v)


def Default(a: ExprRef) -> ExprRef:
    """Get the default value of a constant array. Otherwise build an AppNode."""
    if isinstance(a._ast, ConstArrayNode):
        # Return the value stored in the constant array
        sort = a._sort
        rng = sort.range() if isinstance(sort, ArraySortRef) else a._sort
        return ExprRef(a._ast.val, rng, a._vars)
    # Generic: build an application node
    return ExprRef(AppNode(_AstVar("default"), (a._ast,)), a._sort, a._vars)


def Ext(a: ExprRef, b: ExprRef) -> ExprRef:
    """Array extensionality: return an index where a and b differ."""
    sort = a._sort
    dom = sort.domain() if isinstance(sort, ArraySortRef) else IntSort()
    merged = _merge(a._vars, b._vars)
    return ExprRef(AppNode(_AstVar("ext"), (a._ast, b._ast)), dom, merged)


# ---------------------------------------------------------------------------
# Arithmetic extras: Cbrt
# ---------------------------------------------------------------------------


def Cbrt(a: ArithRef) -> ArithRef:
    """Cube root (represented as application)."""
    return ArithRef(
        AppNode(_AstVar("cbrt"), (a._ast,)),
        a._sort,  # type: ignore[arg-type]
        a._vars,
    )


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def enable_trace(tag: str) -> None:
    """Enable Z3 tracing (no-op — Lean has its own tracing)."""
    pass


def disable_trace(tag: str) -> None:
    """Disable Z3 tracing (no-op)."""
    pass


def open_log(filename: str) -> None:
    """Open Z3 log file (no-op)."""
    pass


def get_version() -> tuple[int, int, int, int]:
    """Return version tuple."""
    return (4, 0, 0, 0)


def get_version_string() -> str:
    """Return version string."""
    return "lean.py-z3compat-4.0.0.0"


def get_full_version() -> str:
    return get_version_string()


# ---------------------------------------------------------------------------
# Order sorts
# ---------------------------------------------------------------------------


def PartialOrder(name: str, ctx: Context | None = None) -> FuncDeclRef:
    """Declare a partial order relation."""
    s = DeclareSort(name)
    return FuncDeclRef(f"{name}_le", (s, s), BoolSort())


def LinearOrder(name: str, ctx: Context | None = None) -> FuncDeclRef:
    """Declare a linear (total) order relation."""
    s = DeclareSort(name)
    return FuncDeclRef(f"{name}_le", (s, s), BoolSort())


def TreeOrder(name: str, ctx: Context | None = None) -> FuncDeclRef:
    """Declare a tree order relation."""
    s = DeclareSort(name)
    return FuncDeclRef(f"{name}_le", (s, s), BoolSort())


def PiecewiseLinearOrder(name: str, ctx: Context | None = None) -> FuncDeclRef:
    """Declare a piecewise linear order relation."""
    s = DeclareSort(name)
    return FuncDeclRef(f"{name}_le", (s, s), BoolSort())


def TransitiveClosure(f: FuncDeclRef) -> FuncDeclRef:
    """Compute the transitive closure of a binary relation."""
    return FuncDeclRef(f"tc_{f._name}", f._domain, f._range)


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def DatatypeSort(name: str, ctx: Context | None = None) -> UninterpretedSortRef:
    """Create a datatype sort (alias for DeclareSort)."""
    return DeclareSort(name)


def CreatePolymorphicDatatype(name: str, num_params: int) -> _DatatypeBuilder:
    """Create a polymorphic datatype builder. Returns a Datatype builder."""
    return Datatype(name)


def substitute_vars(expr: ExprRef, *args: ExprRef) -> ExprRef:
    """Substitute de Bruijn variables in an expression.

    Replaces __db_0 with args[0], __db_1 with args[1], etc.
    """
    mapping: dict[str, ASTNode] = {}
    for i, a in enumerate(args):
        mapping[f"__db_{i}"] = a._ast
    new_ast = _substitute_ast(expr._ast, mapping)
    new_vars = expr._vars
    for a in args:
        new_vars = new_vars | a._vars
    if isinstance(expr, BoolRef):
        return BoolRef(new_ast, new_vars)
    return (
        type(expr)(new_ast, expr._sort, new_vars)
        if not isinstance(expr, BoolRef)
        else BoolRef(new_ast, new_vars)
    )


def substitute_funs(expr: ExprRef, *args: tuple[FuncDeclRef, ExprRef]) -> ExprRef:
    """Substitute function declarations in an expression."""
    mapping: dict[str, ASTNode] = {}
    for f, body in args:
        mapping[f._name] = body._ast
    new_ast = _substitute_ast(expr._ast, mapping)
    if isinstance(expr, BoolRef):
        return BoolRef(new_ast, expr._vars)
    return ExprRef(new_ast, expr._sort, expr._vars)


def deserialize(s: str) -> ExprRef:
    """Deserialize an expression from string."""
    raise NotImplementedError(
        "deserialize is not supported: Lean uses its own expression format"
    )


def to_symbol(s: Any, ctx: Context | None = None) -> str:
    """Convert to a symbol string."""
    return str(s)


class Numeral:
    """Wrapper around numeric ExprRef values for z3py compatibility."""

    def __init__(self, val: Any, sort: SortRef | None = None) -> None:
        if isinstance(val, int):
            if sort is not None and isinstance(sort._ast_sort, RealASTSort):
                self._expr: ArithRef = RealVal(val)
            else:
                self._expr = IntVal(val)
        elif isinstance(val, float):
            self._expr = RealVal(val)
        elif isinstance(val, str):
            if "/" in val:
                parts = val.split("/")
                self._expr = RatVal(int(parts[0]), int(parts[1]))
            else:
                self._expr = IntVal(int(val))
        elif isinstance(val, ArithRef):
            self._expr = val
        elif isinstance(val, ExprRef):
            self._expr = val  # type: ignore[assignment]
        else:
            self._expr = IntVal(int(val))

    def as_long(self) -> int:
        if isinstance(self._expr, IntNumRef):
            return self._expr.as_long()
        return int(repr(self._expr))

    def as_fraction(self):
        if isinstance(self._expr, RatNumRef):
            return self._expr.as_fraction()
        return Fraction(self.as_long())

    def sexpr(self) -> str:
        return self._expr.sexpr()

    def __repr__(self) -> str:
        return repr(self._expr)

    def __add__(self, other: Any) -> Numeral:
        return Numeral(
            self._expr + other._expr
            if isinstance(other, Numeral)
            else self._expr + other
        )

    def __sub__(self, other: Any) -> Numeral:
        return Numeral(
            self._expr - other._expr
            if isinstance(other, Numeral)
            else self._expr - other
        )

    def __mul__(self, other: Any) -> Numeral:
        return Numeral(
            self._expr * other._expr
            if isinstance(other, Numeral)
            else self._expr * other
        )

    def __lt__(self, other: Any) -> bool:
        return False  # Cannot compare symbolic values

    def __le__(self, other: Any) -> bool:
        return False

    def __gt__(self, other: Any) -> bool:
        return False

    def __ge__(self, other: Any) -> bool:
        return False

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Numeral):
            return repr(self._expr) == repr(other._expr)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(repr(self._expr))


_html_mode = False


def set_html_mode(flag: bool = True) -> None:
    """Set HTML output mode."""
    global _html_mode
    _html_mode = flag


def in_html_mode() -> bool:
    """Check if HTML output mode is enabled."""
    return _html_mode


def obj_to_string(obj: Any) -> str:
    """Convert any z3 object to string."""
    return repr(obj)


def append_log(s: str) -> None:
    """Append to Z3 log (no-op)."""
    pass


def help_simplify() -> str:
    """Return simplify help string."""
    return "lean.py simplify: returns expression unchanged. No tunable parameters."


def simplify_param_descrs() -> dict:
    """Return simplify parameter descriptions."""
    return {}


# ---------------------------------------------------------------------------
# Params
# ---------------------------------------------------------------------------


class ParamsRef:
    """Dict-like parameter container for z3py compatibility."""

    def __init__(self, ctx: Context | None = None) -> None:
        self._params: dict[str, Any] = {}

    def set(self, name: str, val: Any) -> None:
        """Set a parameter value."""
        self._params[name] = val

    def __setitem__(self, name: str, val: Any) -> None:
        self._params[name] = val

    def __getitem__(self, name: str) -> Any:
        return self._params[name]

    def __contains__(self, name: str) -> bool:
        return name in self._params

    def __repr__(self) -> str:
        return repr(self._params)


class ParamDescrsRef:
    """Parameter descriptions for z3py compatibility."""

    def __init__(self) -> None:
        self._descrs: dict[str, str] = {}

    def __len__(self) -> int:
        return len(self._descrs)

    def __getitem__(self, name: str) -> str:
        return self._descrs.get(name, "")

    def get_name(self, i: int) -> str:
        keys = list(self._descrs.keys())
        if i < len(keys):
            return keys[i]
        raise IndexError(f"Index {i} out of range")

    def __repr__(self) -> str:
        return repr(self._descrs)


def args2params(args: Any, keywords: Any, ctx: Context | None = None) -> ParamsRef:
    """Convert args and keywords to a ParamsRef."""
    p = ParamsRef(ctx)
    if isinstance(args, dict):
        for k, v in args.items():
            p.set(str(k), v)
    if isinstance(keywords, dict):
        for k, v in keywords.items():
            p.set(str(k), v)
    return p


# ---------------------------------------------------------------------------
# RCF (Real Closed Field)
# ---------------------------------------------------------------------------


class RCFNum:
    """Real closed field number (not natively supported)."""

    def __init__(self, val: Any = 0) -> None:
        self._val = val

    def __repr__(self) -> str:
        return f"RCFNum({self._val})"

    def __add__(self, other: Any) -> RCFNum:
        return RCFNum(f"({self._val} + {other})")

    def __mul__(self, other: Any) -> RCFNum:
        return RCFNum(f"({self._val} * {other})")


def Pi() -> ArithRef:
    """Mathematical constant pi."""
    return ArithRef(_AstVar("Real.pi"), RealSort(), frozenset())


def E() -> ArithRef:
    """Mathematical constant e (Euler's number)."""
    return ArithRef(_AstVar("Real.exp_one"), RealSort(), frozenset())


def MkInfinitesimal(name: str = "epsilon") -> ArithRef:
    """Create an infinitesimal value."""
    return ArithRef(_AstVar(name), RealSort(), frozenset([(name, RealASTSort())]))


def MkRoots(p: Any) -> list:
    """Return roots of polynomial (not supported)."""
    raise NotImplementedError("MkRoots is not supported")


# ---------------------------------------------------------------------------
# Polynomial
# ---------------------------------------------------------------------------


def subresultants(p: ArithRef, q: ArithRef, x: ArithRef) -> list:
    """Compute subresultant sequence (not supported)."""
    raise NotImplementedError("subresultants is not supported")


# ---------------------------------------------------------------------------
# User propagation
# ---------------------------------------------------------------------------


class UserPropagateBase:
    """Base class for user propagation (not natively supported)."""

    def __init__(self, s: Any = None, ctx: Context | None = None) -> None:
        self._solver = s

    def add_fixed(self, cb: Any) -> None:
        pass

    def add_final(self, cb: Any) -> None:
        pass

    def add_eq(self, cb: Any) -> None:
        pass

    def add_diseq(self, cb: Any) -> None:
        pass

    def add_created(self, cb: Any) -> None:
        pass

    def push(self) -> None:
        pass

    def pop(self, num_scopes: int) -> None:
        pass

    def add(self, expr: Any) -> None:
        pass

    def propagate(self, e: Any, ids: Any, eqs: Any = None) -> None:
        pass

    def conflict(self, ids: Any, eqs: Any = None) -> None:
        pass


class OnClause:
    """On-clause callback for user propagation."""

    def __init__(self, solver: Any, on_clause: Any) -> None:
        self._solver = solver
        self._on_clause = on_clause


class PropClosures:
    """Propagation closures for user propagation."""

    def __init__(self) -> None:
        self._closures: list[Any] = []

    def register(self, closure: Any) -> int:
        self._closures.append(closure)
        return len(self._closures) - 1

    def get(self, idx: int) -> Any:
        return self._closures[idx]


def PropagateFunction(name: str, *sorts: SortRef) -> FuncDeclRef:
    """Create a propagation function."""
    if len(sorts) < 2:
        raise TypeError("PropagateFunction needs at least domain and range sorts")
    return Function(name, *sorts)


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Sorts
    "SortRef",
    "BoolSortRef",
    "ArithSortRef",
    "UninterpretedSortRef",
    "DatatypeSortRef",
    "BitVecSortRef",
    "ArraySortRef",
    "StringSortRef",
    "ReSort",
    "CharSortRef",
    "CharRef",
    "SeqSortRef",
    "SeqRef",
    "BoolSort",
    "IntSort",
    "NatSort",
    "RealSort",
    "DeclareSort",
    "BitVecSort",
    "ArraySort",
    "StringSort",
    # Expressions
    "ExprRef",
    "DatatypeRef",
    "BoolRef",
    "ArithRef",
    "BitVecRef",
    "ArrayRef",
    "QuantifierRef",
    "StringRef",
    "ReRef",
    # Numeric references
    "IntNumRef",
    "RatNumRef",
    "BitVecNumRef",
    "AlgebraicNumRef",
    # Functions
    "FuncDeclRef",
    "Function",
    # Variable constructors
    "Int",
    "Ints",
    "Nat",
    "Real",
    "Reals",
    "Bool",
    "Bools",
    "BitVec",
    "BitVecs",
    "Array",
    "Const",
    "Consts",
    # Vector constructors
    "IntVector",
    "BoolVector",
    "RealVector",
    # Value constructors
    "IntVal",
    "NatVal",
    "RealVal",
    "BoolVal",
    "BitVecVal",
    # Array operations
    "Select",
    "Store",
    "K",
    "Map",
    "AsArray",
    "Default",
    "Ext",
    # Datatype
    "Datatype",
    "CreateDatatypes",
    "EnumSort",
    "TupleSort",
    "DatatypeSort",
    "CreatePolymorphicDatatype",
    # Operations
    "And",
    "Or",
    "Not",
    "Implies",
    "Xor",
    "If",
    "Distinct",
    # Quantifiers
    "ForAll",
    "Exists",
    # Substitute
    "substitute",
    "substitute_vars",
    "substitute_funs",
    # Bitvector functions
    "LShR",
    "ULE",
    "ULT",
    "UGE",
    "UGT",
    "UDiv",
    "URem",
    "Extract",
    "Concat",
    "ZeroExt",
    "SignExt",
    "BV2Int",
    "Int2BV",
    "RotateLeft",
    "RotateRight",
    "SDiv",
    "SRem",
    "AShr",
    # BV extras
    "RepeatBitVec",
    "BVRedAnd",
    "BVRedOr",
    "BvNand",
    "BvNor",
    "BvXnor",
    # BV overflow predicates
    "BVAddNoOverflow",
    "BVAddNoUnderflow",
    "BVSubNoOverflow",
    "BVSubNoUnderflow",
    "BVMulNoOverflow",
    "BVMulNoUnderflow",
    "BVSDivNoOverflow",
    "BVSNegNoOverflow",
    # Arithmetic functions
    "Abs",
    "ToReal",
    "ToInt",
    "Sum",
    "Product",
    "IsInt",
    "Sqrt",
    "Cbrt",
    # Rational
    "RatVal",
    "Q",
    # Pseudo-boolean
    "AtMost",
    "AtLeast",
    "PbEq",
    "PbLe",
    "PbGe",
    # Fresh
    "FreshConst",
    "FreshInt",
    "FreshBool",
    "FreshReal",
    # Lambda
    "Lambda",
    # String functions
    "String",
    "Strings",
    "StringVal",
    "Length",
    "Contains",
    "PrefixOf",
    "SuffixOf",
    "Replace",
    "SubString",
    "IndexOf",
    "StrConcat",
    "StrToInt",
    "IntToStr",
    # Regex functions
    "Re",
    "Star",
    "Plus",
    "Option",
    "Union",
    "Intersect",
    "Complement",
    "Range",
    "Loop",
    "InRe",
    "AllChar",
    # Predicates
    "is_expr",
    "is_true",
    "is_false",
    "is_int",
    "is_real",
    "is_bool",
    "is_bv",
    "is_array",
    "is_const",
    "is_var",
    "is_quantifier",
    "is_eq",
    "is_distinct",
    "is_and",
    "is_or",
    "is_not",
    "is_implies",
    "is_add",
    "is_mul",
    "is_sub",
    "is_div",
    "is_string",
    "is_string_value",
    "is_arith",
    "is_sort",
    "is_app",
    "is_func_decl",
    "is_int_value",
    "is_rational_value",
    "is_bv_value",
    "is_le",
    "is_lt",
    "is_ge",
    "is_gt",
    "is_mod",
    "is_idiv",
    # Sort predicates
    "is_arith_sort",
    "is_bv_sort",
    "is_array_sort",
    "is_fp_sort",
    "is_fprm_sort",
    "is_fprm_value",
    "is_algebraic_value",
    "is_default",
    # Finite domain predicates
    "is_finite_domain",
    "is_finite_domain_sort",
    "is_finite_domain_value",
    # Context
    "Context",
    "main_ctx",
    "get_ctx",
    # AstRef / AstVector / AstMap
    "AstRef",
    "AstVector",
    "AstMap",
    # FP sorts & types
    "FPSortRef",
    "FPRef",
    "FPNumRef",
    "FPRMRef",
    "FPSort",
    "Float16",
    "Float32",
    "Float64",
    "Float128",
    "FloatHalf",
    "FloatSingle",
    "FloatDouble",
    "FloatQuadruple",
    "FP",
    "FPs",
    "FPVal",
    "fpNaN",
    "fpPlusInfinity",
    "fpMinusInfinity",
    "fpPlusZero",
    "fpMinusZero",
    "fpInfinity",
    "fpZero",
    "fpFP",
    "fpToFPUnsigned",
    # FP rounding modes
    "RoundNearestTiesToEven",
    "RNE",
    "RoundNearestTiesToAway",
    "RNA",
    "RoundTowardPositive",
    "RTP",
    "RoundTowardNegative",
    "RTN",
    "RoundTowardZero",
    "RTZ",
    # FP config
    "_default_rounding_mode",
    "get_default_rounding_mode",
    "set_default_rounding_mode",
    "_default_fp_sort",
    "get_default_fp_sort",
    "set_default_fp_sort",
    # FP arithmetic
    "fpAdd",
    "fpSub",
    "fpMul",
    "fpDiv",
    "fpNeg",
    "fpAbs",
    "fpSqrt",
    "fpFMA",
    "fpRem",
    "fpMin",
    "fpMax",
    # FP comparisons
    "fpLEQ",
    "fpLT",
    "fpGEQ",
    "fpGT",
    "fpEQ",
    "fpNEQ",
    # FP predicates
    "fpIsNaN",
    "fpIsInf",
    "fpIsZero",
    "fpIsNormal",
    "fpIsSubnormal",
    "fpIsNegative",
    "fpIsPositive",
    # FP conversions
    "fpToReal",
    "fpToSBV",
    "fpToUBV",
    "fpToFP",
    "fpBVToFP",
    "fpFPToFP",
    "fpRealToFP",
    "fpSignedToFP",
    "fpUnsignedToFP",
    "fpRoundToIntegral",
    "fpToIEEEBV",
    # Sets
    "SetSort",
    "EmptySet",
    "FullSet",
    "IsMember",
    "SetAdd",
    "SetDel",
    "SetUnion",
    "SetIntersect",
    "SetComplement",
    "SetDifference",
    "IsSubset",
    "SetHasSize",
    # FiniteSet family
    "FiniteSetSort",
    "FiniteSetEmpty",
    "Singleton",
    "FiniteSetUnion",
    "FiniteSetIntersect",
    "FiniteSetDifference",
    "FiniteSetMember",
    "FiniteSetSize",
    "FiniteSetSubset",
    "FiniteSetMap",
    "FiniteSetFilter",
    "FiniteSetRange",
    "In",
    "is_finite_set",
    "is_finite_set_sort",
    # Sequences
    "SeqSort",
    "Empty",
    "Full",
    "Unit",
    "SubSeq",
    "SeqMap",
    "SeqMapI",
    "SeqFoldLeft",
    "SeqFoldLeftI",
    # Char
    "CharSort",
    "CharVal",
    "CharFromBv",
    "CharToBv",
    "CharToInt",
    "CharIsDigit",
    # Finite domain
    "FiniteDomainSort",
    "FiniteDomainVal",
    "FiniteDomainSize",
    # RecFunction
    "RecFunction",
    "RecAddDefinition",
    # De Bruijn
    "Var",
    "get_var_index",
    # MultiPattern / DisjointSum
    "MultiPattern",
    "DisjointSum",
    # Additional predicates
    "is_ast",
    "is_fp",
    "is_fprm",
    "is_fp_value",
    "is_seq",
    "is_re",
    "is_const_array",
    "is_K",
    "is_map",
    "is_select",
    "is_store",
    "is_to_real",
    "is_to_int",
    "is_is_int",
    "is_pattern",
    # String / regex extras
    "LastIndexOf",
    "StrToCode",
    "StrFromCode",
    "At",
    "Diff",
    # Structural equality
    "eq",
    # Update
    "Update",
    # Utilities
    "enable_trace",
    "disable_trace",
    "open_log",
    "get_version",
    "get_version_string",
    "get_full_version",
    # Order sorts
    "PartialOrder",
    "LinearOrder",
    "TreeOrder",
    "PiecewiseLinearOrder",
    "TransitiveClosure",
    # Misc
    "deserialize",
    "to_symbol",
    "Numeral",
    "set_html_mode",
    "in_html_mode",
    "obj_to_string",
    "append_log",
    "help_simplify",
    "simplify_param_descrs",
    # Params
    "ParamsRef",
    "ParamDescrsRef",
    "args2params",
    # RCF
    "RCFNum",
    "Pi",
    "E",
    "MkInfinitesimal",
    "MkRoots",
    # Polynomial
    "subresultants",
    # User propagation
    "UserPropagateBase",
    "OnClause",
    "PropClosures",
    "PropagateFunction",
]
