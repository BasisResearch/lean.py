"""z3py-compatible expression AST backed by Lean syntax strings.

Each expression node carries:
- ``_lean``: a Lean-syntax fragment
- ``_sort``: the expression's sort
- ``_vars``: free variables as ``frozenset[tuple[str, str]]`` (name, lean_sort)

The tree is purely structural -- no Lean kernel interaction is needed
to build expressions. Lean interaction only happens at proof time
(see :mod:`lean_py.z3.solver`).
"""

from __future__ import annotations

from typing import Sequence

# ---------------------------------------------------------------------------
# Sorts
# ---------------------------------------------------------------------------


class SortRef:
    """Base sort."""

    __slots__ = ("_lean",)

    def __init__(self, lean: str) -> None:
        self._lean = lean

    def to_lean(self) -> str:
        return self._lean

    def __repr__(self) -> str:
        return self._lean

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SortRef) and self._lean == other._lean

    def __hash__(self) -> int:
        return hash(self._lean)


class BoolSortRef(SortRef):
    pass


class ArithSortRef(SortRef):
    pass


class UninterpretedSortRef(SortRef):
    """Declared via ``DeclareSort``."""
    pass


def BoolSort() -> BoolSortRef:
    return BoolSortRef("Prop")


def IntSort() -> ArithSortRef:
    return ArithSortRef("Int")


def NatSort() -> ArithSortRef:
    return ArithSortRef("Nat")


def RealSort() -> ArithSortRef:
    return ArithSortRef("Real")


def DeclareSort(name: str) -> UninterpretedSortRef:
    return UninterpretedSortRef(name)


class BitVecSortRef(SortRef):
    """Fixed-width bit-vector sort, maps to Lean's ``BitVec n``."""

    __slots__ = ("_width",)

    def __init__(self, width: int) -> None:
        super().__init__(f"(BitVec {width})")
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
        super().__init__(f"({domain.to_lean()} \u2192 {range_sort.to_lean()})")
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

    __slots__ = ("_lean", "_sort", "_vars")

    def __init__(
        self,
        lean: str,
        sort: SortRef,
        vars: frozenset[tuple[str, str]] = frozenset(),
    ) -> None:
        self._lean = lean
        self._sort = sort
        self._vars = vars

    def to_lean(self) -> str:
        return self._lean

    def sort(self) -> SortRef:
        return self._sort

    def __repr__(self) -> str:
        return self._lean

    def __eq__(self, other: object) -> BoolRef | NotImplemented:  # type: ignore[override]
        if isinstance(other, (int, float)):
            other = _coerce_val(other, self._sort)
        if not isinstance(other, ExprRef):
            return NotImplemented
        return BoolRef(
            f"({self._lean} = {other._lean})",
            _merge(self._vars, other._vars),
        )

    def __ne__(self, other: object) -> BoolRef | NotImplemented:  # type: ignore[override]
        if isinstance(other, (int, float)):
            other = _coerce_val(other, self._sort)
        if not isinstance(other, ExprRef):
            return NotImplemented
        return BoolRef(
            f"({self._lean} \u2260 {other._lean})",
            _merge(self._vars, other._vars),
        )

    def __hash__(self) -> int:
        return hash(self._lean)


class BoolRef(ExprRef):
    """Boolean / Prop expression."""

    __slots__ = ()

    def __init__(
        self,
        lean: str,
        vars: frozenset[tuple[str, str]] = frozenset(),
    ) -> None:
        super().__init__(lean, BoolSort(), vars)

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
        lean: str,
        sort: ArithSortRef,
        vars: frozenset[tuple[str, str]] = frozenset(),
    ) -> None:
        super().__init__(lean, sort, vars)

    def _binop(self, op: str, other: ArithRef | int | float) -> ArithRef:
        other = _coerce_arith(other, self._sort)
        return ArithRef(
            f"({self._lean} {op} {other._lean})",
            self._sort,  # type: ignore[arg-type]
            _merge(self._vars, other._vars),
        )

    def __add__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop("+", other)

    def __radd__(self, other: int | float) -> ArithRef:
        return _coerce_arith(other, self._sort)._binop("+", self)

    def __sub__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop("-", other)

    def __rsub__(self, other: int | float) -> ArithRef:
        return _coerce_arith(other, self._sort)._binop("-", self)

    def __mul__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop("*", other)

    def __rmul__(self, other: int | float) -> ArithRef:
        return _coerce_arith(other, self._sort)._binop("*", self)

    def __truediv__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop("/", other)

    def __mod__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop("%", other)

    def __pow__(self, other: ArithRef | int | float) -> ArithRef:
        return self._binop("^", other)

    def __neg__(self) -> ArithRef:
        return ArithRef(
            f"(-{self._lean})",
            self._sort,  # type: ignore[arg-type]
            self._vars,
        )

    def __lt__(self, other: ArithRef | int | float) -> BoolRef:
        other = _coerce_arith(other, self._sort)
        return BoolRef(
            f"({self._lean} < {other._lean})",
            _merge(self._vars, other._vars),
        )

    def __le__(self, other: ArithRef | int | float) -> BoolRef:
        other = _coerce_arith(other, self._sort)
        return BoolRef(
            f"({self._lean} \u2264 {other._lean})",
            _merge(self._vars, other._vars),
        )

    def __gt__(self, other: ArithRef | int | float) -> BoolRef:
        other = _coerce_arith(other, self._sort)
        return BoolRef(
            f"({self._lean} > {other._lean})",
            _merge(self._vars, other._vars),
        )

    def __ge__(self, other: ArithRef | int | float) -> BoolRef:
        other = _coerce_arith(other, self._sort)
        return BoolRef(
            f"({self._lean} \u2265 {other._lean})",
            _merge(self._vars, other._vars),
        )


class BitVecRef(ExprRef):
    """Bit-vector expression, maps to Lean's ``BitVec n``."""

    __slots__ = ()

    def __init__(
        self,
        lean: str,
        sort: BitVecSortRef,
        vars: frozenset[tuple[str, str]] = frozenset(),
    ) -> None:
        super().__init__(lean, sort, vars)

    def _binop(self, op: str, other: BitVecRef | int) -> BitVecRef:
        other = _coerce_bv(other, self._sort)
        return BitVecRef(
            f"({self._lean} {op} {other._lean})",
            self._sort,  # type: ignore[arg-type]
            _merge(self._vars, other._vars),
        )

    # Arithmetic
    def __add__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop("+", other)

    def __radd__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop("+", self)

    def __sub__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop("-", other)

    def __rsub__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop("-", self)

    def __mul__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop("*", other)

    def __rmul__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop("*", self)

    def __neg__(self) -> BitVecRef:
        return BitVecRef(
            f"(-{self._lean})",
            self._sort,  # type: ignore[arg-type]
            self._vars,
        )

    # Bitwise — Lean uses &&&, |||, ^^^, ~~~, <<<, >>>
    def __and__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop("&&&", other)

    def __rand__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop("&&&", self)

    def __or__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop("|||", other)

    def __ror__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop("|||", self)

    def __xor__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop("^^^", other)

    def __rxor__(self, other: int) -> BitVecRef:
        return _coerce_bv(other, self._sort)._binop("^^^", self)

    def __invert__(self) -> BitVecRef:
        return BitVecRef(
            f"(~~~{self._lean})",
            self._sort,  # type: ignore[arg-type]
            self._vars,
        )

    def __lshift__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop("<<<", other)

    def __rshift__(self, other: BitVecRef | int) -> BitVecRef:
        return self._binop(">>>", other)

    # Comparisons (unsigned in Lean by default)
    def __lt__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            f"({self._lean} < {other._lean})",
            _merge(self._vars, other._vars),
        )

    def __le__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            f"({self._lean} \u2264 {other._lean})",
            _merge(self._vars, other._vars),
        )

    def __gt__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            f"({self._lean} > {other._lean})",
            _merge(self._vars, other._vars),
        )

    def __ge__(self, other: BitVecRef | int) -> BoolRef:
        other = _coerce_bv(other, self._sort)
        return BoolRef(
            f"({self._lean} \u2265 {other._lean})",
            _merge(self._vars, other._vars),
        )


class ArrayRef(ExprRef):
    """SMT array expression, maps to Lean function type."""

    __slots__ = ()

    def __init__(
        self,
        lean: str,
        sort: ArraySortRef,
        vars: frozenset[tuple[str, str]] = frozenset(),
    ) -> None:
        super().__init__(lean, sort, vars)


class QuantifierRef(BoolRef):
    """Quantified expression (ForAll / Exists)."""

    __slots__ = ("_quantifier", "_bound", "_body")

    def __init__(
        self,
        quantifier: str,
        bound: list[ExprRef],
        body: BoolRef,
    ) -> None:
        binders = " ".join(
            f"({v._lean} : {v._sort.to_lean()})" for v in bound
        )
        bound_names = frozenset((v._lean, v._sort.to_lean()) for v in bound)
        free = body._vars - bound_names
        lean = f"({quantifier} {binders}, {body._lean})"
        super().__init__(lean, free)
        self._quantifier = quantifier
        self._bound = bound
        self._body = body


# ---------------------------------------------------------------------------
# Function declarations
# ---------------------------------------------------------------------------


class FuncDeclRef:
    """Uninterpreted function declaration, created via ``Function(...)``."""

    __slots__ = ("_name", "_domain", "_range", "_lean_type")

    def __init__(
        self,
        name: str,
        domain: tuple[SortRef, ...],
        range_sort: SortRef,
    ) -> None:
        self._name = name
        self._domain = domain
        self._range = range_sort
        self._lean_type = " \u2192 ".join(
            s.to_lean() for s in (*domain, range_sort)
        )

    def __call__(self, *args: ExprRef) -> ExprRef:
        if len(args) != len(self._domain):
            raise TypeError(
                f"{self._name} expects {len(self._domain)} args, got {len(args)}"
            )
        arg_strs = " ".join(a._lean for a in args)
        lean = f"({self._name} {arg_strs})" if args else self._name
        merged = frozenset().union(*(a._vars for a in args))
        # The function itself is a free variable (its signature must be bound)
        merged = merged | frozenset([(self._name, self._lean_type)])
        # Uninterpreted sorts used by the function are also free
        for s in (*self._domain, self._range):
            if isinstance(s, UninterpretedSortRef):
                merged = merged | frozenset([(s._lean, "Type")])
        return ExprRef(lean, self._range, merged)

    def __repr__(self) -> str:
        return f"{self._name} : {self._lean_type}"


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
    return ArithRef(name, s, frozenset([(name, s.to_lean())]))


def Ints(names: str) -> tuple[ArithRef, ...]:
    return tuple(Int(n) for n in names.split())


def Nat(name: str) -> ArithRef:
    s = NatSort()
    return ArithRef(name, s, frozenset([(name, s.to_lean())]))


def Real(name: str) -> ArithRef:
    s = RealSort()
    return ArithRef(name, s, frozenset([(name, s.to_lean())]))


def Reals(names: str) -> tuple[ArithRef, ...]:
    return tuple(Real(n) for n in names.split())


def Bool(name: str) -> BoolRef:
    return BoolRef(name, frozenset([(name, "Prop")]))


def Bools(names: str) -> tuple[BoolRef, ...]:
    return tuple(Bool(n) for n in names.split())


def BitVec(name: str, width: int) -> BitVecRef:
    s = BitVecSort(width)
    return BitVecRef(name, s, frozenset([(name, s.to_lean())]))


def BitVecs(names: str, width: int) -> tuple[BitVecRef, ...]:
    return tuple(BitVec(n, width) for n in names.split())


def Array(name: str, domain: SortRef, range_sort: SortRef) -> ArrayRef:
    s = ArraySort(domain, range_sort)
    return ArrayRef(name, s, frozenset([(name, s.to_lean())]))


def Const(name: str, sort: SortRef) -> ExprRef:
    v = frozenset([(name, sort.to_lean())])
    if isinstance(sort, BoolSortRef):
        return BoolRef(name, v)
    if isinstance(sort, ArithSortRef):
        return ArithRef(name, sort, v)
    if isinstance(sort, BitVecSortRef):
        return BitVecRef(name, sort, v)
    if isinstance(sort, ArraySortRef):
        return ArrayRef(name, sort, v)
    return ExprRef(name, sort, v)


def Consts(names: str, sort: SortRef) -> tuple[ExprRef, ...]:
    return tuple(Const(n, sort) for n in names.split())


# ---------------------------------------------------------------------------
# Value constructors
# ---------------------------------------------------------------------------


def IntVal(n: int) -> ArithRef:
    lean = f"({n} : Int)" if n < 0 else f"({n} : Int)"
    return ArithRef(lean, IntSort())


def NatVal(n: int) -> ArithRef:
    return ArithRef(f"({n} : Nat)", NatSort())


def RealVal(n: int | float | str) -> ArithRef:
    return ArithRef(f"({n} : Real)", RealSort())


def BoolVal(b: bool) -> BoolRef:
    return BoolRef("True" if b else "False")


def BitVecVal(val: int, width: int) -> BitVecRef:
    s = BitVecSort(width)
    return BitVecRef(f"({val} : BitVec {width})", s)


# ---------------------------------------------------------------------------
# Array operations (SMT theory of arrays → Lean function types)
# ---------------------------------------------------------------------------


def Select(a: ArrayRef, idx: ExprRef) -> ExprRef:
    """Read from array. Maps to function application in Lean."""
    sort = a._sort
    if not isinstance(sort, ArraySortRef):
        raise TypeError(f"Select requires ArrayRef, got {type(a)}")
    return ExprRef(
        f"({a._lean} {idx._lean})",
        sort.range(),
        _merge(a._vars, idx._vars),
    )


def Store(a: ArrayRef, idx: ExprRef, val: ExprRef) -> ArrayRef:
    """Write to array: ``(fun x => if x = i then v else a x)``."""
    sort = a._sort
    if not isinstance(sort, ArraySortRef):
        raise TypeError(f"Store requires ArrayRef, got {type(a)}")
    merged = frozenset().union(a._vars, idx._vars, val._vars)
    dom = sort._domain.to_lean()
    return ArrayRef(
        f"(fun (_idx : {dom}) => if _idx = {idx._lean} then {val._lean} else {a._lean} _idx)",
        sort,
        merged,
    )


def K(domain: SortRef, val: ExprRef) -> ArrayRef:
    """Constant array (all indices map to ``val``).
    Maps to ``fun (_ : dom) => val`` in Lean."""
    sort = ArraySort(domain, val._sort)
    return ArrayRef(
        f"(fun (_ : {domain.to_lean()}) => {val._lean})",
        sort,
        val._vars,
    )


# ---------------------------------------------------------------------------
# Datatype builder
# ---------------------------------------------------------------------------


class _DatatypeBuilder:
    """Build an algebraic datatype.

    The resulting sort is uninterpreted, with constructor functions
    generated as ``FuncDeclRef`` instances.  Mirrors the z3py
    ``Datatype`` / ``create()`` pattern.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._ctors: list[tuple[str, tuple[tuple[str, SortRef], ...]]] = []

    def declare(self, ctor_name: str, *fields: tuple[str, SortRef]) -> None:
        self._ctors.append((ctor_name, tuple(fields)))

    def create(self) -> UninterpretedSortRef:
        sort = UninterpretedSortRef(self._name)
        for ctor_name, fields in self._ctors:
            if fields:
                domain = tuple(f[1] for f in fields)
                func = FuncDeclRef(ctor_name, domain, sort)
                setattr(sort, ctor_name, func)
                # Accessor functions
                for field_name, field_sort in fields:
                    acc = FuncDeclRef(field_name, (sort,), field_sort)
                    setattr(sort, field_name, acc)
            else:
                # Nullary constructor: a constant of this sort
                val = ExprRef(ctor_name, sort, frozenset([
                    (ctor_name, sort.to_lean()),
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
    merged = frozenset().union(*(a._vars for a in args))
    lean = " \u2227 ".join(a._lean for a in args)
    return BoolRef(f"({lean})", merged)


def Or(*args: BoolRef) -> BoolRef:
    if len(args) == 0:
        return BoolVal(False)
    if len(args) == 1:
        return args[0]
    merged = frozenset().union(*(a._vars for a in args))
    lean = " \u2228 ".join(a._lean for a in args)
    return BoolRef(f"({lean})", merged)


def Not(a: BoolRef) -> BoolRef:
    return BoolRef(f"(\u00ac{a._lean})", a._vars)


def Implies(a: BoolRef, b: BoolRef) -> BoolRef:
    return BoolRef(f"({a._lean} \u2192 {b._lean})", _merge(a._vars, b._vars))


def Xor(a: BoolRef, b: BoolRef) -> BoolRef:
    return BoolRef(f"(Xor' {a._lean} {b._lean})", _merge(a._vars, b._vars))


def If(c: BoolRef, t: ExprRef, e: ExprRef) -> ExprRef:
    merged = frozenset().union(c._vars, t._vars, e._vars)
    return ExprRef(
        f"(if {c._lean} then {t._lean} else {e._lean})",
        t._sort,
        merged,
    )


def Distinct(*args: ExprRef) -> BoolRef:
    if len(args) <= 1:
        return BoolVal(True)
    merged = frozenset().union(*(a._vars for a in args))
    clauses = []
    for i in range(len(args)):
        for j in range(i + 1, len(args)):
            clauses.append(f"({args[i]._lean} \u2260 {args[j]._lean})")
    lean = " \u2227 ".join(clauses)
    return BoolRef(f"({lean})", merged)


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
    a: frozenset[tuple[str, str]],
    b: frozenset[tuple[str, str]],
) -> frozenset[tuple[str, str]]:
    return a | b


def _coerce_arith(v: ArithRef | int | float, sort: SortRef) -> ArithRef:
    if isinstance(v, ArithRef):
        return v
    if isinstance(v, (int, float)):
        return ArithRef(f"({v} : {sort.to_lean()})", sort)  # type: ignore[arg-type]
    raise TypeError(f"Cannot coerce {type(v)} to ArithRef")


def _coerce_bv(v: BitVecRef | int, sort: SortRef) -> BitVecRef:
    if isinstance(v, BitVecRef):
        return v
    if isinstance(v, int) and isinstance(sort, BitVecSortRef):
        return BitVecRef(f"({v} : BitVec {sort._width})", sort)
    raise TypeError(f"Cannot coerce {type(v)} to BitVecRef")


def _coerce_val(v: int | float, sort: SortRef) -> ExprRef:
    if isinstance(sort, ArithSortRef):
        return ArithRef(f"({v} : {sort.to_lean()})", sort)
    if isinstance(sort, BitVecSortRef):
        return BitVecRef(f"({v} : BitVec {sort._width})", sort)
    return ExprRef(str(v), sort)


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
