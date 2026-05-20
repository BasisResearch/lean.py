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

from typing import Sequence

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
    ForAllNode,
    IntASTSort,
    IntLit,
    IteNode,
    NatASTSort,
    NatLit,
    PropSort,
    RealASTSort,
    SelectNode,
    StoreNode,
    UnOp,
    TypeASTSort,
    UnOpNode,
    UninterpASTSort,
    Var,
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


class BoolSortRef(SortRef):
    pass


class ArithSortRef(SortRef):
    pass


class UninterpretedSortRef(SortRef):
    """Declared via ``DeclareSort``."""
    pass


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

    def __eq__(self, other: object) -> BoolRef | NotImplemented:  # type: ignore[override]
        if isinstance(other, (int, float)):
            other = _coerce_val(other, self._sort)
        if not isinstance(other, ExprRef):
            return NotImplemented
        return BoolRef(
            BinOpNode(BinOp.EQ, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __ne__(self, other: object) -> BoolRef | NotImplemented:  # type: ignore[override]
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
        return self._binop(BinOp.DIV, other)

    def __mod__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop(BinOp.MOD, other)

    def __pow__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop(BinOp.MUL, other)  # placeholder

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
        return self._binop(BinOp.BSHR, other)

    # Comparisons
    def __lt__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.LT, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __le__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.LE, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __gt__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.GT, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )

    def __ge__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            BinOpNode(BinOp.GE, self._ast, other._ast),
            _merge(self._vars, other._vars),
        )


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
        bound_names = frozenset((v._ast.name, v._sort._ast_sort) for v in bound if isinstance(v._ast, Var))
        free = body._vars - bound_names

        # Build the nested AST node
        node_cls = ForAllNode if quantifier == "\u2200" else ExistsNode
        ast: ASTNode = body._ast
        for v in reversed(bound):
            ast = node_cls(
                name=v._ast.name if isinstance(v._ast, Var) else str(v._ast),
                sort=v._sort._ast_sort,
                body=ast,
            )

        super().__init__(ast, free)
        self._quantifier = quantifier
        self._bound = bound
        self._body = body


# ---------------------------------------------------------------------------
# Function declarations
# ---------------------------------------------------------------------------


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
        merged: frozenset[tuple[str, ASTSort]] = frozenset().union(*(a._vars for a in args))
        # The function itself is a free variable
        merged = merged | frozenset([(self._name, self._ast_sort)])
        # Uninterpreted sorts used by the function are also free
        for s in (*self._domain, self._range):
            if isinstance(s, UninterpretedSortRef) and isinstance(s._ast_sort, UninterpASTSort):
                merged = merged | frozenset([(s._ast_sort.name, TypeASTSort())])
        func_ast = Var(self._name)
        args_ast = tuple(a._ast for a in args)
        ast = AppNode(func_ast, args_ast) if args else func_ast
        return ExprRef(ast, self._range, merged)

    def __repr__(self) -> str:
        return f"{self._name} : {_sort_repr(self._ast_sort)}"


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
    return ArithRef(Var(name), s, frozenset([(name, s._ast_sort)]))


def Ints(names: str) -> tuple[ArithRef, ...]:
    return tuple(Int(n) for n in names.split())


def Nat(name: str) -> ArithRef:
    s = NatSort()
    return ArithRef(Var(name), s, frozenset([(name, s._ast_sort)]))


def Real(name: str) -> ArithRef:
    s = RealSort()
    return ArithRef(Var(name), s, frozenset([(name, s._ast_sort)]))


def Reals(names: str) -> tuple[ArithRef, ...]:
    return tuple(Real(n) for n in names.split())


def Bool(name: str) -> BoolRef:
    return BoolRef(Var(name), frozenset([(name, PropSort())]))


def Bools(names: str) -> tuple[BoolRef, ...]:
    return tuple(Bool(n) for n in names.split())


def BitVec(name: str, width: int) -> BitVecRef:
    s = BitVecSort(width)
    return BitVecRef(Var(name), s, frozenset([(name, s._ast_sort)]))


def BitVecs(names: str, width: int) -> tuple[BitVecRef, ...]:
    return tuple(BitVec(n, width) for n in names.split())


def Array(name: str, domain: SortRef, range_sort: SortRef) -> ArrayRef:
    s = ArraySort(domain, range_sort)
    return ArrayRef(Var(name), s, frozenset([(name, s._ast_sort)]))


def Const(name: str, sort: SortRef) -> ExprRef:
    v: frozenset[tuple[str, ASTSort]] = frozenset([(name, sort._ast_sort)])
    # If the sort is uninterpreted, also track it as a free type variable.
    if isinstance(sort, UninterpretedSortRef) and isinstance(sort._ast_sort, UninterpASTSort):
        v = v | frozenset([(sort._ast_sort.name, TypeASTSort())])
    if isinstance(sort, BoolSortRef):
        return BoolRef(Var(name), v)
    if isinstance(sort, ArithSortRef):
        return ArithRef(Var(name), sort, v)
    if isinstance(sort, BitVecSortRef):
        return BitVecRef(Var(name), sort, v)
    if isinstance(sort, ArraySortRef):
        return ArrayRef(Var(name), sort, v)
    return ExprRef(Var(name), sort, v)


def Consts(names: str, sort: SortRef) -> tuple[ExprRef, ...]:
    return tuple(Const(n, sort) for n in names.split())


# ---------------------------------------------------------------------------
# Value constructors
# ---------------------------------------------------------------------------


def IntVal(n: int) -> ArithRef:
    return ArithRef(IntLit(n), IntSort())


def NatVal(n: int) -> ArithRef:
    return ArithRef(NatLit(n), NatSort())


def RealVal(n: int | float | str) -> ArithRef:
    # For now, treat as int literal on Real sort
    return ArithRef(IntLit(int(n)), RealSort())


def BoolVal(b: bool) -> BoolRef:
    return BoolRef(BoolLit(b))


def BitVecVal(val: int, width: int) -> BitVecRef:
    s = BitVecSort(width)
    return BitVecRef(BvLit(val, width), s)


# ---------------------------------------------------------------------------
# Array operations (SMT theory of arrays → Lean function types)
# ---------------------------------------------------------------------------


def Select(a: ArrayRef, idx: ExprRef) -> ExprRef:
    """Read from array. Maps to function application in Lean."""
    sort = a._sort
    if not isinstance(sort, ArraySortRef):
        raise TypeError(f"Select requires ArrayRef, got {type(a)}")
    return ExprRef(
        SelectNode(a._ast, idx._ast),
        sort.range(),
        _merge(a._vars, idx._vars),
    )


def Store(a: ArrayRef, idx: ExprRef, val: ExprRef) -> ArrayRef:
    """Write to array."""
    sort = a._sort
    if not isinstance(sort, ArraySortRef):
        raise TypeError(f"Store requires ArrayRef, got {type(a)}")
    merged: frozenset[tuple[str, ASTSort]] = frozenset().union(a._vars, idx._vars, val._vars)
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
    """Build an algebraic datatype."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._ctors: list[tuple[str, tuple[tuple[str, SortRef], ...]]] = []

    def declare(self, ctor_name: str, *fields: tuple[str, SortRef]) -> None:
        self._ctors.append((ctor_name, tuple(fields)))

    def create(self) -> UninterpretedSortRef:
        sort = UninterpretedSortRef(UninterpASTSort(self._name))
        for ctor_name, fields in self._ctors:
            if fields:
                domain = tuple(f[1] for f in fields)
                func = FuncDeclRef(ctor_name, domain, sort)
                setattr(sort, ctor_name, func)
                for field_name, field_sort in fields:
                    acc = FuncDeclRef(field_name, (sort,), field_sort)
                    setattr(sort, field_name, acc)
            else:
                val = ExprRef(Var(ctor_name), sort, frozenset([
                    (ctor_name, sort._ast_sort),
                ]))
                setattr(sort, ctor_name, val)
        return sort


def Datatype(name: str) -> _DatatypeBuilder:
    return _DatatypeBuilder(name)


# ---------------------------------------------------------------------------
# Boolean combinators
# ---------------------------------------------------------------------------


def And(*args: BoolRef) -> BoolRef:
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
    merged: frozenset[tuple[str, ASTSort]] = frozenset().union(c._vars, t._vars, e._vars)
    return ExprRef(
        IteNode(c._ast, t._ast, e._ast),
        t._sort,
        merged,
    )


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
        else:
            return ArithRef(IntLit(int(v)), sort)  # type: ignore[arg-type]
    raise TypeError(f"Cannot coerce {type(v)} to ArithRef")


def _coerce_bv(v: BitVecRef | int, sort: SortRef) -> BitVecRef:
    if isinstance(v, BitVecRef):
        return v
    if isinstance(v, int) and isinstance(sort, BitVecSortRef):
        return BitVecRef(BvLit(v, sort._width), sort)
    raise TypeError(f"Cannot coerce {type(v)} to BitVecRef")


def _coerce_val(v: int | float, sort: SortRef) -> ExprRef:
    if isinstance(sort, ArithSortRef):
        return _coerce_arith(v, sort)
    if isinstance(sort, BitVecSortRef):
        return BitVecRef(BvLit(int(v), sort._width), sort)
    return ExprRef(IntLit(int(v)), sort)


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
    if isinstance(s, UninterpASTSort):
        return s.name
    if isinstance(s, ArrowASTSort):
        return f"({_sort_repr(s.dom)} \u2192 {_sort_repr(s.cod)})"
    return str(s)


def _ast_repr(node: ASTNode) -> str:
    """Human-readable string for an ASTNode (for debugging)."""
    if isinstance(node, Var):
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
        return f"(store {_ast_repr(node.arr)} {_ast_repr(node.idx)} {_ast_repr(node.val)})"
    if isinstance(node, ConstArrayNode):
        return f"(const-array {_ast_repr(node.val)})"
    return str(node)


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Sorts
    "SortRef", "BoolSortRef", "ArithSortRef", "UninterpretedSortRef",
    "BitVecSortRef", "ArraySortRef",
    "BoolSort", "IntSort", "NatSort", "RealSort", "DeclareSort",
    "BitVecSort", "ArraySort",
    # Expressions
    "ExprRef", "BoolRef", "ArithRef", "BitVecRef", "ArrayRef",
    "QuantifierRef",
    # Functions
    "FuncDeclRef", "Function",
    # Variable constructors
    "Int", "Ints", "Nat", "Real", "Reals", "Bool", "Bools",
    "BitVec", "BitVecs", "Array",
    "Const", "Consts",
    # Value constructors
    "IntVal", "NatVal", "RealVal", "BoolVal", "BitVecVal",
    # Array operations
    "Select", "Store", "K",
    # Datatype
    "Datatype",
    # Operations
    "And", "Or", "Not", "Implies", "Xor", "If", "Distinct",
    # Quantifiers
    "ForAll", "Exists",
]
