"""z3py-compatible solver backed by Lean's ``grind`` tactic.

The solver constructs Lean Z3Expr AST values from z3-style expressions
and dispatches them through :class:`lean_py.kernel.Kernel`. The Lean
side compiles the AST to fully elaborated ``Lean.Expr`` via MetaM.

- **unsat** means the negation of the conjunction was proved (the
  constraints are contradictory).
- **sat** is never returned -- Lean cannot produce models.
- **unknown** means grind could not discharge the goal.

Typical usage::

    from lean_py.z3 import *
    x, y = Ints('x y')
    prove(Implies(And(x > 0, y > 0), x + y > 0))
"""

from __future__ import annotations

from typing import Any

from lean_py.kernel import Kernel
from lean_py.project import ManagedProject
from lean_py.z3._ast import (
    AppNode,
    ArrowASTSort,
    ASTNode,
    ASTSort,
    BinOpNode,
    BitvecASTSort,
    BoolLit,
    BvLit,
    CharASTSort,
    CharFromBvNode,
    CharIsDigitNode,
    CharLit,
    CharToNatNode,
    ConstArrayNode,
    DistinctNode,
    ExistsNode,
    ExtractNode,
    FinDomainASTSort,
    FinDomainLit,
    ForAllNode,
    FpASTSort,
    FpLitNode,
    FpOpNode,
    InductiveAccessorNode,
    InductiveASTSort,
    InductiveCtorNode,
    InductiveRecognizerNode,
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
    ReComplementNode,
    ReConcatNode,
    ReIntersectNode,
    ReLoopNode,
    ReOptionNode,
    RePlusNode,
    ReRangeNode,
    ReStarNode,
    ReUnionNode,
    SelectNode,
    SeqASTSort,
    SeqConcatNode,
    SeqContainsNode,
    SeqEmptyNode,
    SeqLenNode,
    SeqNthNode,
    SeqPrefixOfNode,
    SeqSuffixOfNode,
    SeqUnitNode,
    SignExtNode,
    StoreNode,
    StrConcatNode,
    StrContainsNode,
    StrIndexOfNode,
    StringASTSort,
    StringLit,
    StrLenNode,
    StrPrefixOfNode,
    StrReplaceNode,
    StrSubstrNode,
    StrSuffixOfNode,
    StrToIntNode,
    ToIntNode,
    ToRealNode,
    TypeASTSort,
    UninterpASTSort,
    UnOpNode,
    Var,
    ZeroExtNode,
)
from lean_py.z3.core import (
    And,
    BoolRef,
    BoolVal,
    ExprRef,
    ForAll,
    FuncDeclRef,
    Implies,
    Not,
    _ast_repr,
)
from lean_py.z3.smt2 import parse_smt2_file as _parse_smt2_file_impl
from lean_py.z3.smt2 import parse_smt2_string as _parse_smt2_string_impl

# ---------------------------------------------------------------------------
# CheckSatResult
# ---------------------------------------------------------------------------


class CheckSatResult:
    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return self._name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CheckSatResult) and self._name == other._name

    def __hash__(self) -> int:
        return hash(self._name)

    def __bool__(self) -> bool:
        raise TypeError("CheckSatResult cannot be used as bool; compare to sat/unsat/unknown")


sat = CheckSatResult("sat")
unsat = CheckSatResult("unsat")
unknown = CheckSatResult("unknown")


# ---------------------------------------------------------------------------
# Kernel management
# ---------------------------------------------------------------------------

_kernel: Kernel | None = None


def set_kernel(k: Kernel) -> None:
    """Set the global kernel used by solvers and ``prove()``."""
    global _kernel
    _kernel = k


def _get_kernel() -> Kernel:
    global _kernel
    if _kernel is not None:
        return _kernel
    mp = ManagedProject.get()
    _kernel = mp.kernel()
    return _kernel


# ---------------------------------------------------------------------------
# AST marshalling (Python AST → Lean Z3Sort/Z3BinOp/Z3UnOp/Z3Expr)
# ---------------------------------------------------------------------------


def _marshal_sort(lib: Any, sort: ASTSort) -> Any:
    """Convert a Python ASTSort to a Lean Z3Sort value."""
    Z3Sort = lib.Z3Sort
    if isinstance(sort, PropSort):
        return Z3Sort.prop
    if isinstance(sort, IntASTSort):
        return Z3Sort.int
    if isinstance(sort, NatASTSort):
        return Z3Sort.nat
    if isinstance(sort, RealASTSort):
        return Z3Sort.real
    if isinstance(sort, TypeASTSort):
        return Z3Sort.type
    if isinstance(sort, StringASTSort):
        return Z3Sort.string
    if isinstance(sort, BitvecASTSort):
        return Z3Sort.bitvec(sort.width)
    if isinstance(sort, UninterpASTSort):
        return Z3Sort.uninterp(sort.name)
    if isinstance(sort, FpASTSort):
        return Z3Sort.fp(sort.ebits, sort.sbits)
    if isinstance(sort, FinDomainASTSort):
        return Z3Sort.finDomain(sort.size)
    if isinstance(sort, ArrowASTSort):
        dom = _marshal_sort(lib, sort.dom)
        cod = _marshal_sort(lib, sort.cod)
        return Z3Sort.arrow(dom, cod)
    if isinstance(sort, InductiveASTSort):
        return Z3Sort.inductive_(sort.name)
    if isinstance(sort, CharASTSort):
        return Z3Sort.char
    if isinstance(sort, SeqASTSort):
        elem = _marshal_sort(lib, sort.elem)
        return Z3Sort.seq(elem)
    raise TypeError(f"Unknown ASTSort: {type(sort)}")


def _marshal_binop(lib: Any, op: str) -> Any:
    """Convert a BinOp string to a Lean Z3BinOp value."""
    Z3BinOp = lib.Z3BinOp
    return getattr(Z3BinOp, op)


def _marshal_unop(lib: Any, op: str) -> Any:
    """Convert a UnOp string to a Lean Z3UnOp value."""
    Z3UnOp = lib.Z3UnOp
    return getattr(Z3UnOp, op)


def _marshal_expr(lib: Any, node: ASTNode) -> Any:
    """Convert a Python ASTNode to a Lean Z3Expr value."""
    Z3Expr = lib.Z3Expr
    if isinstance(node, Var):
        return Z3Expr.var(node.name)
    if isinstance(node, IntLit):
        return Z3Expr.intLit(node.val)
    if isinstance(node, NatLit):
        return Z3Expr.natLit(node.val)
    if isinstance(node, BoolLit):
        return Z3Expr.boolLit(node.val)
    if isinstance(node, BvLit):
        return Z3Expr.bvLit(node.val, node.width)
    if isinstance(node, BinOpNode):
        op = _marshal_binop(lib, node.op)
        lhs = _marshal_expr(lib, node.lhs)
        rhs = _marshal_expr(lib, node.rhs)
        return Z3Expr.binop(op, lhs, rhs)
    if isinstance(node, UnOpNode):
        op = _marshal_unop(lib, node.op)
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.unop(op, arg)
    if isinstance(node, IteNode):
        cond = _marshal_expr(lib, node.cond)
        then_ = _marshal_expr(lib, node.then_)
        else_ = _marshal_expr(lib, node.else_)
        return Z3Expr.ite(cond, then_, else_)
    if isinstance(node, ForAllNode):
        sort = _marshal_sort(lib, node.sort)
        body = _marshal_expr(lib, node.body)
        return Z3Expr.forall_(node.name, sort, body)
    if isinstance(node, ExistsNode):
        sort = _marshal_sort(lib, node.sort)
        body = _marshal_expr(lib, node.body)
        return Z3Expr.exists_(node.name, sort, body)
    if isinstance(node, AppNode):
        func = _marshal_expr(lib, node.func)
        args = [_marshal_expr(lib, a) for a in node.args]
        return Z3Expr.app(func, args)
    if isinstance(node, DistinctNode):
        args = [_marshal_expr(lib, a) for a in node.args]
        return Z3Expr.distinct(args)
    if isinstance(node, SelectNode):
        arr = _marshal_expr(lib, node.arr)
        idx = _marshal_expr(lib, node.idx)
        return Z3Expr.select(arr, idx)
    if isinstance(node, StoreNode):
        arr = _marshal_expr(lib, node.arr)
        idx = _marshal_expr(lib, node.idx)
        val = _marshal_expr(lib, node.val)
        return Z3Expr.store(arr, idx, val)
    if isinstance(node, ConstArrayNode):
        dom_sort = _marshal_sort(lib, node.dom_sort)
        val = _marshal_expr(lib, node.val)
        return Z3Expr.constArray(dom_sort, val)
    if isinstance(node, ExtractNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.extract(node.hi, node.lo, arg)
    if isinstance(node, ZeroExtNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.zeroExt(node.bits, arg)
    if isinstance(node, SignExtNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.signExt(node.bits, arg)
    if isinstance(node, Int2BvNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.int2bv(node.width, arg)
    if isinstance(node, ToRealNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.toReal(arg)
    if isinstance(node, ToIntNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.toInt(arg)
    if isinstance(node, LambdaNode):
        sort = _marshal_sort(lib, node.sort)
        body = _marshal_expr(lib, node.body)
        return Z3Expr.lambda_(node.name, sort, body)
    # String nodes
    if isinstance(node, StringLit):
        return Z3Expr.stringLit(node.val)
    if isinstance(node, StrLenNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.strLen(arg)
    if isinstance(node, StrContainsNode):
        a = _marshal_expr(lib, node.haystack)
        b = _marshal_expr(lib, node.needle)
        return Z3Expr.strContains(a, b)
    if isinstance(node, StrPrefixOfNode):
        a = _marshal_expr(lib, node.prefix_)
        b = _marshal_expr(lib, node.s)
        return Z3Expr.strPrefixOf(a, b)
    if isinstance(node, StrSuffixOfNode):
        a = _marshal_expr(lib, node.suffix_)
        b = _marshal_expr(lib, node.s)
        return Z3Expr.strSuffixOf(a, b)
    if isinstance(node, StrReplaceNode):
        a = _marshal_expr(lib, node.s)
        b = _marshal_expr(lib, node.old)
        c = _marshal_expr(lib, node.new_)
        return Z3Expr.strReplace(a, b, c)
    if isinstance(node, StrConcatNode):
        a = _marshal_expr(lib, node.lhs)
        b = _marshal_expr(lib, node.rhs)
        return Z3Expr.strConcat(a, b)
    if isinstance(node, StrSubstrNode):
        a = _marshal_expr(lib, node.s)
        b = _marshal_expr(lib, node.offset)
        c = _marshal_expr(lib, node.length)
        return Z3Expr.strSubstr(a, b, c)
    if isinstance(node, StrIndexOfNode):
        a = _marshal_expr(lib, node.s)
        b = _marshal_expr(lib, node.substr)
        c = _marshal_expr(lib, node.offset)
        return Z3Expr.strIndexOf(a, b, c)
    if isinstance(node, StrToIntNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.strToInt(arg)
    if isinstance(node, IntToStrNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.intToStr(arg)
    # Regex nodes
    if isinstance(node, ReStarNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.reStar(arg)
    if isinstance(node, RePlusNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.rePlus(arg)
    if isinstance(node, ReOptionNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.reOption(arg)
    if isinstance(node, ReUnionNode):
        a = _marshal_expr(lib, node.a)
        b = _marshal_expr(lib, node.b)
        return Z3Expr.reUnion(a, b)
    if isinstance(node, ReIntersectNode):
        a = _marshal_expr(lib, node.a)
        b = _marshal_expr(lib, node.b)
        return Z3Expr.reIntersect(a, b)
    if isinstance(node, ReConcatNode):
        a = _marshal_expr(lib, node.a)
        b = _marshal_expr(lib, node.b)
        return Z3Expr.reConcat(a, b)
    if isinstance(node, ReRangeNode):
        return Z3Expr.reRange(node.lo, node.hi)
    if isinstance(node, ReComplementNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.reComplement(arg)
    if isinstance(node, ReLoopNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.reLoop(arg, node.lo, node.hi)
    if isinstance(node, InReNode):
        a = _marshal_expr(lib, node.s)
        b = _marshal_expr(lib, node.re)
        return Z3Expr.inRe(a, b)
    # Floating-point nodes
    if isinstance(node, FpLitNode):
        return Z3Expr.fpLit(node.bits, node.ebits, node.sbits)
    if isinstance(node, FpOpNode):
        args = [_marshal_expr(lib, a) for a in node.args]
        return Z3Expr.fpOp(node.op, args)
    # Finite domain
    if isinstance(node, FinDomainLit):
        return Z3Expr.finDomainLit(node.val, node.size)
    # Inductive datatypes
    if isinstance(node, InductiveCtorNode):
        args = [_marshal_expr(lib, a) for a in node.args]
        return Z3Expr.inductiveCtor(node.type_name, node.ctor_name, args)
    if isinstance(node, InductiveAccessorNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.inductiveAccessor(node.type_name, node.accessor_name, arg)
    if isinstance(node, InductiveRecognizerNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.inductiveRecognizer(node.type_name, node.recognizer_name, arg)
    # Char nodes
    if isinstance(node, CharLit):
        return Z3Expr.charLit(node.val)
    if isinstance(node, CharToNatNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.charToNat(arg)
    if isinstance(node, CharFromBvNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.charFromBv(arg)
    if isinstance(node, CharIsDigitNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.charIsDigit(arg)
    # Seq nodes
    if isinstance(node, SeqEmptyNode):
        elem_sort = _marshal_sort(lib, node.elem_sort)
        return Z3Expr.seqEmpty(elem_sort)
    if isinstance(node, SeqUnitNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.seqUnit(arg)
    if isinstance(node, SeqLenNode):
        arg = _marshal_expr(lib, node.arg)
        return Z3Expr.seqLen(arg)
    if isinstance(node, SeqConcatNode):
        lhs = _marshal_expr(lib, node.lhs)
        rhs = _marshal_expr(lib, node.rhs)
        return Z3Expr.seqConcat(lhs, rhs)
    if isinstance(node, SeqContainsNode):
        a = _marshal_expr(lib, node.haystack)
        b = _marshal_expr(lib, node.needle)
        return Z3Expr.seqContains(a, b)
    if isinstance(node, SeqPrefixOfNode):
        a = _marshal_expr(lib, node.prefix_)
        b = _marshal_expr(lib, node.s)
        return Z3Expr.seqPrefixOf(a, b)
    if isinstance(node, SeqSuffixOfNode):
        a = _marshal_expr(lib, node.suffix_)
        b = _marshal_expr(lib, node.s)
        return Z3Expr.seqSuffixOf(a, b)
    if isinstance(node, SeqNthNode):
        a = _marshal_expr(lib, node.s)
        b = _marshal_expr(lib, node.idx)
        return Z3Expr.seqNth(a, b)
    raise TypeError(f"Unknown ASTNode: {type(node)}")


# ---------------------------------------------------------------------------
# Variable sort key (for ordering free variables)
# ---------------------------------------------------------------------------


def _var_sort_key(var: tuple[str, ASTSort]) -> tuple[int, str]:
    """Sort ordering: Type vars (0), function sigs (1), values (2)."""
    name, sort = var
    if isinstance(sort, TypeASTSort):
        return (0, name)
    if isinstance(sort, ArrowASTSort):
        return (1, name)
    return (2, name)


# ---------------------------------------------------------------------------
# Core prove function
# ---------------------------------------------------------------------------


def _wrap_free_vars(expr: BoolRef) -> ASTNode:
    """Wrap the expression AST in ForAll nodes for its free variables.

    Sorts free vars: Type vars first, arrows (functions) second, values last.
    """
    free = sorted(expr._vars, key=_var_sort_key)
    ast: ASTNode = expr._ast
    for name, sort in reversed(free):
        ast = ForAllNode(name=name, sort=sort, body=ast)
    return ast


def _try_prove(expr: BoolRef) -> bool:
    """Compile AST to Lean.Expr, create goal, try tactics. Returns True if proved."""
    k = _get_kernel()
    lib = k._lib

    # Wrap free vars in ForAll
    ast = _wrap_free_vars(expr)

    # Marshal to Lean Z3Expr
    z3_expr = _marshal_expr(lib, ast)

    # Compile to Lean.Expr
    lean_expr = lib.z3_compile(z3_expr)

    # Create goal state from the Lean.Expr
    gs = k.goal_create_expr(lean_expr)

    # Try tactics
    for tac in _TACTICS:
        result = gs.try_tactic(tac)
        if result.ok and result.state is not None and result.state.is_solved():
            return True
    return False


# ---------------------------------------------------------------------------
# Tactic dispatch
# ---------------------------------------------------------------------------

_TACTICS = ["grind", "omega", "decide", "simp_all", "native_decide"]


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------


class ModelRef:
    """Placeholder — Lean is a proof checker, not an SMT solver."""

    def __getitem__(self, key: Any) -> Any:
        raise NotImplementedError(
            "Model extraction not supported: Lean cannot produce counter-models"
        )

    def eval(self, t: Any, model_completion: bool = False) -> Any:
        raise NotImplementedError(
            "Model extraction not supported: Lean cannot produce counter-models"
        )

    evaluate = eval

    def decls(self) -> list:
        return []

    def __len__(self) -> int:
        return 0

    def __contains__(self, key: Any) -> bool:
        return False

    def __iter__(self):
        return iter([])

    def sexpr(self) -> str:
        return "(model)"

    def __repr__(self) -> str:
        return "ModelRef(unsupported)"


class Solver:
    """z3py-compatible solver interface.

    ``check()`` builds the conjunction of all assertions, negates it,
    and tries to prove the negation via grind.  If proved, returns
    ``unsat`` (the constraints are contradictory).  Otherwise ``unknown``.
    """

    def __init__(self) -> None:
        self._assertions: list[BoolRef] = []
        self._stack: list[int] = []

    def add(self, *args: BoolRef) -> None:
        for a in args:
            self._assertions.append(a)

    # Aliases for add
    append = add
    insert = add

    def set(self, *args: Any, **keys: Any) -> None:
        """Set solver options (no-op — Lean solver has no tunable parameters)."""
        pass

    def push(self) -> None:
        self._stack.append(len(self._assertions))

    def pop(self, n: int = 1) -> None:
        for _ in range(n):
            if not self._stack:
                raise IndexError("pop from empty solver stack")
            self._assertions = self._assertions[: self._stack.pop()]

    def num_scopes(self) -> int:
        """Return number of push scopes."""
        return len(self._stack)

    def check(self, *assumptions: BoolRef) -> CheckSatResult:
        asserts = list(self._assertions)
        asserts.extend(assumptions)
        if not asserts:
            return sat
        conj = And(*asserts)
        # Try proving negation → unsat
        negated = Not(conj)
        if _try_prove(negated):
            return unsat
        # Try proving conjunction directly → sat (tautologically true)
        if _try_prove(conj):
            return sat
        return unknown

    def model(self) -> ModelRef:
        raise NotImplementedError(
            "Model extraction not supported: Lean is a proof checker, not an SMT solver"
        )

    def assertions(self) -> list[BoolRef]:
        return list(self._assertions)

    def assert_and_track(self, a: BoolRef, p: BoolRef | None = None) -> None:
        """Add assertion tracked by p (tracking ignored — no unsat core support)."""
        self._assertions.append(a)

    def unsat_core(self) -> list:
        """Return unsat core (not supported)."""
        raise NotImplementedError(
            "Unsat core not supported: Lean is a proof checker, not an SMT solver"
        )

    def reason_unknown(self) -> str:
        """Return reason for unknown result."""
        return "Lean proof tactics could not discharge the goal"

    def statistics(self) -> dict:
        """Return solver statistics."""
        return {}

    def sexpr(self) -> str:
        """Return S-expression representation of assertions."""
        if not self._assertions:
            return "()"
        parts = [_ast_repr(a._ast) for a in self._assertions]
        return "(" + " ".join(parts) + ")"

    def to_smt2(self) -> str:
        """Return SMT-LIB2 representation (approximate)."""
        lines = []
        for a in self._assertions:
            lines.append(f"(assert {_ast_repr(a._ast)})")
        lines.append("(check-sat)")
        return "\n".join(lines)

    def reset(self) -> None:
        self._assertions.clear()
        self._stack.clear()

    def __enter__(self) -> Solver:
        self.push()
        return self

    def __exit__(self, *exc) -> None:
        self.pop()

    def __repr__(self) -> str:
        return f"[{', '.join(repr(a) for a in self._assertions)}]"

    def __len__(self) -> int:
        return len(self._assertions)

    def __getitem__(self, i: int) -> BoolRef:
        return self._assertions[i]

    def __iter__(self):
        return iter(self._assertions)

    @staticmethod
    def from_file(filename: str) -> Solver:
        """Load solver from file (not supported)."""
        raise NotImplementedError("from_file not supported: Lean uses its own syntax, not SMT-LIB2")

    @staticmethod
    def from_string(s: str) -> Solver:
        """Load solver from string (not supported)."""
        raise NotImplementedError(
            "from_string not supported: Lean uses its own syntax, not SMT-LIB2"
        )

    def cube(self, vars: Any = None) -> list:
        """Generate cubes (not supported)."""
        return []

    def consequences(self, assumptions: list, variables: list) -> tuple:
        """Compute consequences (not supported)."""
        return (unknown, [])

    def help(self) -> str:
        """Return solver help string."""
        return "lean.py solver backed by Lean's grind tactic. No tunable parameters."

    def param_descrs(self) -> dict:
        """Return parameter descriptions."""
        return {}

    def non_units(self) -> list:
        """Return non-unit clauses."""
        return []

    def units(self) -> list:
        """Return unit clauses."""
        return []

    def trail(self) -> list:
        """Return the trail."""
        return []

    def trail_levels(self) -> list:
        """Return trail levels."""
        return []

    def proof(self) -> Any:
        """Return proof (not supported)."""
        raise NotImplementedError("Proof extraction not supported")

    def translate(self, ctx: Any) -> Solver:
        """Translate solver to another context (no-op)."""
        return self

    def reset_params(self) -> None:
        """Reset solver parameters (no-op)."""
        pass

    def get_param(self, name: str) -> Any:
        """Get solver parameter value (always None)."""
        return None

    def import_model_converter(self, other: Any) -> None:
        """Import model converter from another solver (no-op)."""
        pass


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def prove(claim: BoolRef) -> bool:
    """Prove a claim directly (no double-negation).

    Returns ``True`` if proved, ``False`` otherwise.
    Prints "proved" or "failed to prove" to match knuckledragger style.
    """
    result = _try_prove(claim)
    if result:
        print("proved")
    else:
        print("failed to prove")
    return result


def solve(*args: BoolRef) -> CheckSatResult:
    """Shorthand: create solver, add args, check."""
    s = Solver()
    s.add(*args)
    return s.check()


def simplify(expr: ExprRef) -> ExprRef:
    """Simplify an expression (placeholder — returns input unchanged)."""
    return expr


def set_param(*args: Any, **kws: Any) -> None:
    """Set global Z3 parameters (no-op — Lean has no tunable Z3 parameters)."""
    pass


set_option = set_param


def SolverFor(logic: str) -> Solver:
    """Create a solver for a specific logic (returns standard Solver)."""
    return Solver()


def SimpleSolver() -> Solver:
    """Create a simple solver (returns standard Solver)."""
    return Solver()


def solve_using(s: Solver, *args: BoolRef) -> CheckSatResult:
    """Solve using a specific solver instance."""
    s.add(*args)
    return s.check()


def parse_smt2_string(s: str, sorts: dict | None = None, decls: dict | None = None) -> list:
    """Parse a string in SMT-LIB2 format using the given sorts and decls.

    Returns a list of assertions (z3py ``ExprRef`` objects).
    """
    return _parse_smt2_string_impl(s, sorts=sorts, decls=decls)


def parse_smt2_file(filename: str, sorts: dict | None = None, decls: dict | None = None) -> list:
    """Parse an SMT-LIB2 file using the given sorts and decls.

    Returns a list of assertions (z3py ``ExprRef`` objects).
    """
    return _parse_smt2_file_impl(filename, sorts=sorts, decls=decls)


# ---------------------------------------------------------------------------
# Optimize
# ---------------------------------------------------------------------------


class Optimize:
    """Optimization solver.

    Lean is a proof checker, not an optimization solver, so optimization
    queries return ``unknown``. Programs that build Optimize expressions
    will work; solving requires an SMT backend.
    """

    def __init__(self) -> None:
        self._assertions: list[BoolRef] = []
        self._objectives: list[tuple[str, ExprRef]] = []

    def add(self, *args: BoolRef) -> None:
        for a in args:
            self._assertions.append(a)

    def maximize(self, expr: ExprRef) -> int:
        """Add maximization objective (returns handle index)."""
        self._objectives.append(("max", expr))
        return len(self._objectives) - 1

    def minimize(self, expr: ExprRef) -> int:
        """Add minimization objective (returns handle index)."""
        self._objectives.append(("min", expr))
        return len(self._objectives) - 1

    def check(self) -> CheckSatResult:
        """Check satisfiability (always returns unknown for optimization)."""
        return unknown

    def model(self) -> ModelRef:
        raise NotImplementedError(
            "Model extraction not supported: Lean is a proof checker, not an optimization solver"
        )

    def push(self) -> None:
        pass

    def pop(self) -> None:
        pass

    def assertions(self) -> list[BoolRef]:
        return list(self._assertions)

    def objectives(self) -> list[tuple[str, ExprRef]]:
        return list(self._objectives)

    def assert_soft(self, expr: BoolRef, weight: Any = None, id: Any = None) -> int:
        """Add a soft constraint with optional weight and group id."""
        self._assertions.append(expr)
        return len(self._assertions) - 1

    def set(self, *args: Any, **keys: Any) -> None:
        pass

    def __repr__(self) -> str:
        return f"Optimize({len(self._assertions)} assertions, {len(self._objectives)} objectives)"


# ---------------------------------------------------------------------------
# Fixedpoint
# ---------------------------------------------------------------------------


class Fixedpoint:
    """Fixedpoint (Datalog) solver backed by Lean's ``grind`` tactic.

    Encodes facts as hypotheses and rules as universally-quantified
    implications, then proves the query via the kernel's tactic engine.
    """

    def __init__(self, ctx: Any = None) -> None:
        self._decls: list[FuncDeclRef] = []
        self._declared_vars: list[ExprRef] = []
        self._premises: list[BoolRef] = []
        self._rules: list[BoolRef] = []
        self._last_result: CheckSatResult = unknown

    # -- declarations --------------------------------------------------------

    def register_relation(self, *decls: Any) -> None:
        for d in decls:
            if isinstance(d, FuncDeclRef):
                self._decls.append(d)

    def declare_var(self, *args: Any) -> None:
        for v in args:
            if isinstance(v, ExprRef):
                self._declared_vars.append(v)

    def set(self, *args: Any, **kws: Any) -> None:
        pass

    # -- helpers -------------------------------------------------------------

    def _abstract(self, expr: BoolRef) -> BoolRef:
        """Wrap *expr* in ForAll over declared vars that appear in it."""
        var_names = {name for name, _ in expr._vars}
        used = [
            v for v in self._declared_vars if isinstance(v._ast, Var) and v._ast.name in var_names
        ]
        if used:
            return ForAll(used, expr)
        return expr

    # -- add_rule / fact / rule ----------------------------------------------

    def add_rule(self, head: Any, body: Any = None, name: str | None = None) -> None:
        if body is not None and not isinstance(body, str):
            # Explicit head/body split: head :- body
            if not isinstance(body, (list, tuple)):
                body = [body]
            if len(body) == 1:
                rule: BoolRef = Implies(body[0], head)
            else:
                rule = Implies(And(*body), head)
            rule = self._abstract(rule)
            self._premises.append(rule)
            self._rules.append(rule)
            return

        # body is None (or a name string) -- head is the full formula
        if isinstance(head, BoolRef):
            self._premises.append(self._abstract(head))
            self._rules.append(head)

    def rule(self, head: Any, body: Any = None, name: str | None = None) -> None:
        self.add_rule(head, body, name)

    def fact(self, head: Any, name: str | None = None) -> None:
        self.add_rule(head, None, name)

    # -- query ---------------------------------------------------------------

    def query(self, *query: Any) -> CheckSatResult:
        q: Any = query[0] if len(query) == 1 else query
        if isinstance(q, FuncDeclRef) or not isinstance(q, BoolRef):
            self._last_result = unknown
            return unknown

        # Build: (premise₁ ∧ … ∧ premiseₙ) → query
        goal: BoolRef
        if self._premises:
            conj = And(*self._premises) if len(self._premises) > 1 else self._premises[0]
            goal = Implies(conj, q)
        else:
            goal = q

        if _try_prove(goal):
            self._last_result = sat
            return sat
        self._last_result = unknown
        return unknown

    # -- introspection -------------------------------------------------------

    def get_answer(self) -> ExprRef:
        return BoolVal(self._last_result == sat)

    def get_ground_sat_answer(self) -> ExprRef:
        return BoolVal(self._last_result == sat)

    def get_rules(self) -> list:
        return list(self._rules)

    def get_rules_along_trace(self) -> list:
        return []

    def get_assertions(self) -> list:
        return list(self._premises)

    def parse_string(self, s: str) -> None:
        raise NotImplementedError("Fixedpoint SMT-LIB parsing not supported")

    def parse_file(self, path: str) -> None:
        raise NotImplementedError("Fixedpoint SMT-LIB parsing not supported")

    def __repr__(self) -> str:
        return f"Fixedpoint({len(self._rules)} rules)"


# ---------------------------------------------------------------------------
# FuncInterp / FuncEntry (model introspection)
# ---------------------------------------------------------------------------


class FuncEntry:
    """A single entry in a function interpretation."""

    def __init__(self) -> None:
        pass

    def num_args(self) -> int:
        return 0

    def arg_value(self, i: int) -> Any:
        raise NotImplementedError(
            "Model extraction not supported: Lean cannot produce counter-models"
        )

    def value(self) -> Any:
        raise NotImplementedError(
            "Model extraction not supported: Lean cannot produce counter-models"
        )

    def as_list(self) -> list:
        return []


class FuncInterp:
    """Function interpretation in a model."""

    def __init__(self) -> None:
        pass

    def else_value(self) -> Any:
        raise NotImplementedError(
            "Model extraction not supported: Lean cannot produce counter-models"
        )

    def num_entries(self) -> int:
        return 0

    def entry(self, i: int) -> FuncEntry:
        raise NotImplementedError(
            "Model extraction not supported: Lean cannot produce counter-models"
        )

    def arity(self) -> int:
        return 0

    def as_list(self) -> list:
        return []


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class Statistics:
    """Solver statistics."""

    def __init__(self, data: dict | None = None) -> None:
        self._data = data or {}

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key, 0)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> list[str]:
        return list(self._data.keys())

    def get_key_value(self, key: str) -> Any:
        return self._data.get(key, 0)

    def __repr__(self) -> str:
        return repr(self._data)


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------


def Model(ctx: Any = None) -> ModelRef:
    """Create a new (empty) model."""
    return ModelRef()


# ---------------------------------------------------------------------------
# Model introspection predicates
# ---------------------------------------------------------------------------


def is_as_array(a: Any) -> bool:
    """Check if expression is an as-array."""
    return False


def get_as_array_func(a: Any) -> Any:
    """Get FuncDeclRef from as-array expression."""
    raise NotImplementedError("get_as_array_func not supported: Lean cannot produce counter-models")


def get_map_func(a: Any) -> Any:
    """Get FuncDeclRef from mapped array expression."""
    raise NotImplementedError("get_map_func not supported: Lean cannot produce counter-models")


# ---------------------------------------------------------------------------
# OptimizeObjective
# ---------------------------------------------------------------------------


class OptimizeObjective:
    """Represents an optimization objective handle."""

    def __init__(self, opt: Any, is_max: bool, idx: int) -> None:
        self._opt = opt
        self._is_max = is_max
        self._idx = idx

    def lower(self) -> Any:
        raise NotImplementedError("OptimizeObjective.lower not supported: Lean is a proof checker")

    def upper(self) -> Any:
        raise NotImplementedError("OptimizeObjective.upper not supported: Lean is a proof checker")

    def value(self) -> Any:
        raise NotImplementedError("OptimizeObjective.value not supported: Lean is a proof checker")

    def __repr__(self) -> str:
        kind = "maximize" if self._is_max else "minimize"
        return f"OptimizeObjective({kind}, {self._idx})"


# ---------------------------------------------------------------------------
# ParserContext
# ---------------------------------------------------------------------------


class ParserContext:
    """SMT-LIB2 parser context (limited support)."""

    def __init__(self, ctx: Any = None) -> None:
        self._sorts: dict[str, Any] = {}
        self._decls: dict[str, Any] = {}

    def add_sort(self, sort: Any) -> None:
        """Add a sort to the parser context."""
        if hasattr(sort, "name"):
            self._sorts[sort.name()] = sort

    def add_decl(self, decl: Any) -> None:
        """Add a declaration to the parser context."""
        if hasattr(decl, "name"):
            self._decls[decl.name()] = decl

    def from_string(self, s: str) -> list:
        """Parse SMT-LIB2 string (not supported)."""
        raise NotImplementedError(
            "ParserContext.from_string not supported: Lean uses its own syntax"
        )

    def __repr__(self) -> str:
        return f"ParserContext({len(self._sorts)} sorts, {len(self._decls)} decls)"


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "CheckSatResult",
    "sat",
    "unsat",
    "unknown",
    "ModelRef",
    "Model",
    "Solver",
    "Optimize",
    "set_kernel",
    "prove",
    "solve",
    "simplify",
    "set_param",
    "set_option",
    "SolverFor",
    "SimpleSolver",
    "solve_using",
    "parse_smt2_string",
    "parse_smt2_file",
    "Fixedpoint",
    "FuncInterp",
    "FuncEntry",
    "Statistics",
    "is_as_array",
    "get_as_array_func",
    "get_map_func",
    "OptimizeObjective",
    "ParserContext",
]
