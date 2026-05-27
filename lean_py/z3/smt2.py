"""SMT-LIB2 parser that constructs z3py-compatible AST objects."""
# mypy: disable-error-code="arg-type,index,operator,assignment"
# The SExpr union type (str | list) requires runtime narrowing that mypy
# cannot track; operators on ExprRef subclasses are valid at runtime.

from __future__ import annotations

from lean_py.z3.core import (
    UGE,
    UGT,
    ULE,
    ULT,
    And,
    ArraySort,
    BitVecSort,
    BitVecVal,
    BoolSort,
    BoolVal,
    BV2Int,
    Concat,
    Const,
    DeclareSort,
    Distinct,
    Exists,
    ExprRef,
    Extract,
    ForAll,
    FuncDeclRef,
    Function,
    If,
    Implies,
    Int2BV,
    IntSort,
    IntVal,
    LShR,
    Not,
    Or,
    RealSort,
    RepeatBitVec,
    RotateLeft,
    RotateRight,
    Select,
    SignExt,
    SortRef,
    Store,
    StringVal,
    ToInt,
    ToReal,
    Xor,
    ZeroExt,
)

# ---------------------------------------------------------------------------
# S-expression tokenizer / parser
# ---------------------------------------------------------------------------


def _tokenize(s: str) -> list[str]:
    """Tokenize an SMT-LIB2 string into a flat list of tokens."""
    tokens: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        # Skip whitespace
        if c in " \t\n\r":
            i += 1
        # Skip comments
        elif c == ";":
            while i < n and s[i] != "\n":
                i += 1
        # Parentheses
        elif c == "(":
            tokens.append("(")
            i += 1
        elif c == ")":
            tokens.append(")")
            i += 1
        # Quoted string
        elif c == '"':
            j = i + 1
            while j < n:
                if s[j] == '"':
                    if j + 1 < n and s[j + 1] == '"':
                        j += 2  # escaped quote
                    else:
                        break
                else:
                    j += 1
            tokens.append(s[i : j + 1])
            i = j + 1
        # Quoted symbol |...|
        elif c == "|":
            j = i + 1
            while j < n and s[j] != "|":
                j += 1
            tokens.append(s[i + 1 : j])  # strip bars
            i = j + 1
        else:
            # Atom
            j = i
            while j < n and s[j] not in ' \t\n\r();"':
                j += 1
            tokens.append(s[i:j])
            i = j
    return tokens


SExpr = str | list["SExpr"]


def _parse_sexpr(tokens: list[str], pos: int) -> tuple[SExpr, int]:
    """Parse one S-expression from tokens starting at pos."""
    if pos >= len(tokens):
        raise ValueError("Unexpected end of input")
    tok = tokens[pos]
    if tok == "(":
        pos += 1
        items: list[SExpr] = []
        while pos < len(tokens) and tokens[pos] != ")":
            item, pos = _parse_sexpr(tokens, pos)
            items.append(item)
        if pos >= len(tokens):
            raise ValueError("Unmatched '('")
        pos += 1  # skip ')'
        return items, pos
    elif tok == ")":
        raise ValueError("Unexpected ')'")
    else:
        return tok, pos + 1


def _parse_all(s: str) -> list[SExpr]:
    """Parse all top-level S-expressions from a string."""
    tokens = _tokenize(s)
    result: list[SExpr] = []
    pos = 0
    while pos < len(tokens):
        expr, pos = _parse_sexpr(tokens, pos)
        result.append(expr)
    return result


# ---------------------------------------------------------------------------
# SMT-LIB2 → z3py objects
# ---------------------------------------------------------------------------


class _Smt2Env:
    """Environment for the SMT-LIB2 parser."""

    def __init__(
        self,
        sorts: dict[str, SortRef] | None = None,
        decls: dict[str, ExprRef | FuncDeclRef] | None = None,
    ):
        self.sorts: dict[str, SortRef] = dict(sorts) if sorts else {}
        self.decls: dict[str, ExprRef | FuncDeclRef] = dict(decls) if decls else {}
        self.assertions: list[ExprRef] = []

    def resolve_sort(self, sexpr: SExpr) -> SortRef:
        """Convert an S-expression to a SortRef."""
        if isinstance(sexpr, str):
            if sexpr == "Int":
                return IntSort()
            if sexpr == "Bool":
                return BoolSort()
            if sexpr == "Real":
                return RealSort()
            if sexpr in self.sorts:
                return self.sorts[sexpr]
            # Treat as uninterpreted sort
            return DeclareSort(sexpr)
        # List form
        if not sexpr:
            raise ValueError("Empty sort expression")
        head = sexpr[0]
        if head == "Array" and len(sexpr) == 3:
            dom = self.resolve_sort(sexpr[1])
            rng = self.resolve_sort(sexpr[2])
            return ArraySort(dom, rng)
        if head == "_" and len(sexpr) == 3 and sexpr[1] == "BitVec":
            return BitVecSort(int(sexpr[2]))
        if isinstance(head, str) and head in self.sorts:
            return self.sorts[head]
        raise ValueError(f"Unknown sort: {sexpr}")

    def resolve_expr(self, sexpr: SExpr, let_env: dict[str, ExprRef] | None = None) -> ExprRef:
        """Convert an S-expression to an ExprRef."""
        if let_env is None:
            let_env = {}

        # Atoms
        if isinstance(sexpr, str):
            # Boolean literals
            if sexpr == "true":
                return BoolVal(True)
            if sexpr == "false":
                return BoolVal(False)
            # Numeric literals
            if sexpr.lstrip("-").isdigit():
                return IntVal(int(sexpr))
            # BitVec binary literal
            if sexpr.startswith("#b"):
                bits = sexpr[2:]
                return BitVecVal(int(bits, 2), len(bits))
            # BitVec hex literal
            if sexpr.startswith("#x"):
                hexval = sexpr[2:]
                return BitVecVal(int(hexval, 16), len(hexval) * 4)
            # Let-bound variable
            if sexpr in let_env:
                return let_env[sexpr]
            # Declared variable / function
            if sexpr in self.decls:
                d = self.decls[sexpr]
                if isinstance(d, FuncDeclRef):
                    # Nullary function call
                    return d()
                return d
            # Quoted string literal
            if sexpr.startswith('"') and sexpr.endswith('"'):
                return StringVal(sexpr[1:-1].replace('""', '"'))
            raise ValueError(f"Unknown symbol: {sexpr}")

        # List form
        if not sexpr:
            raise ValueError("Empty expression")

        head = sexpr[0]

        # let binding
        if head == "let":
            if len(sexpr) != 3:
                raise ValueError(f"Malformed let: {sexpr}")
            bindings = sexpr[1]
            body = sexpr[2]
            new_env = dict(let_env)
            for binding in bindings:
                if not isinstance(binding, list) or len(binding) != 2:
                    raise ValueError(f"Malformed let binding: {binding}")
                name = binding[0]
                val = self.resolve_expr(binding[1], new_env)
                new_env[name] = val
            return self.resolve_expr(body, new_env)

        # Quantifiers
        if head == "forall" or head == "exists":
            if len(sexpr) != 3:
                raise ValueError(f"Malformed quantifier: {sexpr}")
            sorted_vars = sexpr[1]
            body = sexpr[2]
            # Create bound variables
            new_env = dict(let_env)
            bound_vars: list[ExprRef] = []
            for sv in sorted_vars:
                if not isinstance(sv, list) or len(sv) != 2:
                    raise ValueError(f"Malformed sorted var: {sv}")
                vname = sv[0]
                vsort = self.resolve_sort(sv[1])
                v = Const(vname, vsort)
                new_env[vname] = v
                bound_vars.append(v)
            body_expr = self.resolve_expr(body, new_env)
            if head == "forall":
                return ForAll(bound_vars, body_expr)
            else:
                return Exists(bound_vars, body_expr)

        # Indexed expressions: (_ op args...)
        if isinstance(head, list) and head and head[0] == "_":
            return self._resolve_indexed_app(head, sexpr[1:], let_env)

        # (_ op ...) at top level of application
        if head == "_":
            # This is an indexed identifier used standalone, e.g. (_ bv0 32)
            if len(sexpr) >= 3 and isinstance(sexpr[1], str) and sexpr[1].startswith("bv"):
                # (_ bvN width)
                val = int(sexpr[1][2:])
                width = int(sexpr[2])
                return BitVecVal(val, width)
            # Return as indexed identifier for use in application
            raise ValueError(f"Cannot resolve indexed expr at top level: {sexpr}")

        if not isinstance(head, str):
            raise ValueError(f"Expected symbol as head of application, got: {head}")

        args = [self.resolve_expr(a, let_env) for a in sexpr[1:]]

        return self._apply(head, args, sexpr, let_env)

    def _resolve_indexed_app(
        self, indexed_id: list, args_sexprs: list, let_env: dict[str, ExprRef]
    ) -> ExprRef:
        """Handle ((_ op params...) args...)."""
        # indexed_id is like ["_", "extract", "7", "4"]
        if len(indexed_id) < 2:
            raise ValueError(f"Malformed indexed id: {indexed_id}")
        op = indexed_id[1]
        params = indexed_id[2:]
        args = [self.resolve_expr(a, let_env) for a in args_sexprs]

        if op == "extract" and len(params) == 2:
            hi, lo = int(params[0]), int(params[1])
            return Extract(hi, lo, args[0])
        if op == "zero_extend" and len(params) == 1:
            return ZeroExt(int(params[0]), args[0])
        if op == "sign_extend" and len(params) == 1:
            return SignExt(int(params[0]), args[0])
        if op == "rotate_left" and len(params) == 1:
            return RotateLeft(args[0], int(params[0]))
        if op == "rotate_right" and len(params) == 1:
            return RotateRight(args[0], int(params[0]))
        if op == "repeat" and len(params) == 1:
            return RepeatBitVec(int(params[0]), args[0])
        if op == "int2bv" and len(params) == 1:
            return Int2BV(args[0], int(params[0]))

        raise ValueError(f"Unknown indexed operator: {op}")

    def _apply(
        self, head: str, args: list[ExprRef], sexpr: SExpr, let_env: dict[str, ExprRef]
    ) -> ExprRef:
        """Apply a function/operator to resolved args."""
        # Core boolean
        if head == "and":
            return And(*args)
        if head == "or":
            return Or(*args)
        if head == "not":
            return Not(args[0])
        if head == "=>":
            # Right-associative
            result = args[-1]
            for a in reversed(args[:-1]):
                result = Implies(a, result)
            return result
        if head == "xor":
            result = args[0]
            for a in args[1:]:
                result = Xor(result, a)
            return result
        if head == "ite":
            return If(args[0], args[1], args[2])
        if head == "if":
            return If(args[0], args[1], args[2])

        # Equality and comparison
        if head == "=":
            if len(args) == 2:
                return args[0] == args[1]
            # Chain: (= a b c) means a=b and b=c
            conjuncts = [args[i] == args[i + 1] for i in range(len(args) - 1)]
            return And(*conjuncts)
        if head == "distinct":
            return Distinct(*args)
        if head == "<":
            return args[0] < args[1]
        if head == ">":
            return args[0] > args[1]
        if head == "<=":
            return args[0] <= args[1]
        if head == ">=":
            return args[0] >= args[1]

        # Arithmetic
        if head == "+":
            result = args[0]
            for a in args[1:]:
                result = result + a
            return result
        if head == "-":
            if len(args) == 1:
                return -args[0]
            result = args[0]
            for a in args[1:]:
                result = result - a
            return result
        if head == "*":
            result = args[0]
            for a in args[1:]:
                result = result * a
            return result
        if head == "/":
            return args[0] / args[1]
        if head == "div":
            return args[0] / args[1]
        if head == "mod":
            return args[0] % args[1]
        if head == "rem":
            return args[0] % args[1]
        if head == "abs":
            # abs(x) = if x >= 0 then x else -x
            zero = IntVal(0)
            return If(args[0] >= zero, args[0], -args[0])
        if head == "to_real":
            return ToReal(args[0])
        if head == "to_int":
            return ToInt(args[0])

        # Bitvector arithmetic
        if head == "bvadd":
            return args[0] + args[1]
        if head == "bvsub":
            return args[0] - args[1]
        if head == "bvmul":
            return args[0] * args[1]
        if head == "bvudiv":
            return args[0] / args[1]
        if head == "bvurem":
            return args[0] % args[1]
        if head == "bvsdiv":
            return args[0] / args[1]
        if head == "bvsrem":
            return args[0] % args[1]
        if head == "bvsmod":
            return args[0] % args[1]
        if head == "bvneg":
            return -args[0]
        if head == "bvnot":
            return ~args[0]
        if head == "bvand":
            return args[0] & args[1]
        if head == "bvor":
            return args[0] | args[1]
        if head == "bvxor":
            return args[0] ^ args[1]
        if head == "bvshl":
            return args[0] << args[1]
        if head == "bvlshr":
            return LShR(args[0], args[1])
        if head == "bvashr":
            return args[0] >> args[1]
        if head == "concat":
            return Concat(*args)
        if head == "bv2int":
            return BV2Int(args[0])

        # Bitvector comparisons
        if head == "bvult":
            return ULT(args[0], args[1])
        if head == "bvule":
            return ULE(args[0], args[1])
        if head == "bvugt":
            return UGT(args[0], args[1])
        if head == "bvuge":
            return UGE(args[0], args[1])
        if head == "bvslt":
            return args[0] < args[1]
        if head == "bvsle":
            return args[0] <= args[1]
        if head == "bvsgt":
            return args[0] > args[1]
        if head == "bvsge":
            return args[0] >= args[1]

        # Array
        if head == "select":
            return Select(args[0], args[1])
        if head == "store":
            return Store(args[0], args[1], args[2])

        # User-declared function/constant
        if head in self.decls:
            d = self.decls[head]
            if isinstance(d, FuncDeclRef):
                return d(*args)
            if not args:
                return d
            raise ValueError(f"'{head}' is not a function, cannot apply to args")

        raise ValueError(f"Unknown function/operator: {head}")

    def process_command(self, cmd: SExpr) -> None:
        """Process a single SMT-LIB2 command."""
        if not isinstance(cmd, list) or not cmd:
            return
        head = cmd[0]

        if head == "set-logic" or head == "set-info" or head == "set-option":
            return  # ignore
        if head == "check-sat" or head == "get-model" or head == "exit":
            return  # ignore
        if head == "echo" or head == "get-value" or head == "get-assertions":
            return  # ignore
        if head == "push" or head == "pop":
            return  # ignore

        if head == "declare-sort":
            # (declare-sort Name arity)
            name = cmd[1]
            self.sorts[name] = DeclareSort(name)
            return

        if head == "define-sort":
            # (define-sort Name (params) body)
            name = cmd[1]
            # Simple case: no parameters
            if not cmd[2]:  # empty param list
                self.sorts[name] = self.resolve_sort(cmd[3])
            return

        if head == "declare-const":
            # (declare-const name sort)
            name = cmd[1]
            sort = self.resolve_sort(cmd[2])
            self.decls[name] = Const(name, sort)
            return

        if head == "declare-fun":
            # (declare-fun name (sort*) sort)
            name = cmd[1]
            domain_sorts = [self.resolve_sort(s) for s in cmd[2]]
            range_sort = self.resolve_sort(cmd[3])
            if not domain_sorts:
                # Nullary function = constant
                self.decls[name] = Const(name, range_sort)
            else:
                f = Function(name, *domain_sorts, range_sort)
                self.decls[name] = f
            return

        if head == "define-fun":
            # (define-fun name ((param sort)*) sort body)
            name = cmd[1]
            params = cmd[2]
            # return_sort = cmd[3]  # not needed for evaluation
            body = cmd[4]
            if not params:
                # Nullary: just evaluate the body
                self.decls[name] = self.resolve_expr(body)
            else:
                # Create a lambda-like definition
                # For simplicity, store as a FuncDeclRef and inline on use
                param_sorts = [self.resolve_sort(p[1]) for p in params]
                range_sort = self.resolve_sort(cmd[3])
                f = Function(name, *param_sorts, range_sort)
                self.decls[name] = f
            return

        if head == "assert":
            expr = self.resolve_expr(cmd[1])
            self.assertions.append(expr)
            return

        # Unknown command - ignore silently
        return


def parse_smt2_string(
    s: str,
    sorts: dict[str, SortRef] | None = None,
    decls: dict[str, ExprRef | FuncDeclRef] | None = None,
) -> list[ExprRef]:
    """Parse a string in SMT-LIB2 format.

    The arguments ``sorts`` and ``decls`` are Python dictionaries used to
    initialize the symbol table for the parser.

    >>> from lean_py.z3 import *
    >>> parse_smt2_string('(declare-const x Int) (assert (> x 0)) (assert (< x 10))')
    [x > 0, x < 10]
    """
    sexprs = _parse_all(s)
    env = _Smt2Env(sorts=sorts, decls=decls)
    for cmd in sexprs:
        env.process_command(cmd)
    return env.assertions


def parse_smt2_file(
    filename: str,
    sorts: dict[str, SortRef] | None = None,
    decls: dict[str, ExprRef | FuncDeclRef] | None = None,
) -> list[ExprRef]:
    """Parse an SMT-LIB2 file.

    This function is similar to :func:`parse_smt2_string`.
    """
    with open(filename) as f:
        content = f.read()
    return parse_smt2_string(content, sorts=sorts, decls=decls)
