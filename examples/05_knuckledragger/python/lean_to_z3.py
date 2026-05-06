"""
Convert Lean.Expr ADT trees (as ``LeanInductiveValue``) to Z3 expressions.

The Lean tactic wraps its goal ``Expr`` via ``Py.ofLeanObj`` (which decodes
registered ``derive_python`` types into ``LeanInductiveValue`` trees), then
calls ``decode_and_check_prop`` which converts to Z3 and checks the result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import z3

try:
    import kdrag as kdr
    HAS_KDR = True
except ImportError:
    kdr = None
    HAS_KDR = False

if TYPE_CHECKING:
    from lean_py.marshal import LeanInductiveValue


# ---------------------------------------------------------------------------
#  Name helpers
# ---------------------------------------------------------------------------

def name_to_str(name: LeanInductiveValue) -> str:
    """Walk a ``Lean.Name`` ADT (anonymous / str / num) to a dot-separated string."""
    parts: list[str] = []
    cur = name
    while True:
        if cur.ctor == "anonymous":
            break
        elif cur.ctor == "str":
            parts.append(cur.fields[1])
            cur = cur.fields[0]
        elif cur.ctor == "num":
            parts.append(str(cur.fields[1]))
            cur = cur.fields[0]
        else:
            parts.append(f"<{cur.ctor}>")
            break
    parts.reverse()
    return ".".join(parts) if parts else ""


# ---------------------------------------------------------------------------
#  Expr helpers
# ---------------------------------------------------------------------------

def uncurry_app(expr: LeanInductiveValue) -> tuple[LeanInductiveValue, list[LeanInductiveValue]]:
    """Flatten nested ``Expr.app(f, x)`` into ``(head, [arg0, arg1, ...])``."""
    args: list[LeanInductiveValue] = []
    cur = expr
    while cur.ctor == "app":
        args.append(cur.fields[1])
        cur = cur.fields[0]
    args.reverse()
    return cur, args


# ---------------------------------------------------------------------------
#  Z3 variable management
# ---------------------------------------------------------------------------

_VAR_CACHE: dict[str, z3.ArithRef] = {}


def _var(name: str) -> z3.ArithRef:
    if name not in _VAR_CACHE:
        _VAR_CACHE[name] = z3.Int(name)
    return _VAR_CACHE[name]


# ---------------------------------------------------------------------------
#  Main converter
# ---------------------------------------------------------------------------

def _binop(op):
    def build(args):
        return op(expr_to_z3(args[-2]), expr_to_z3(args[-1]))
    return 2, build


def _unop(op):
    def build(args):
        return op(expr_to_z3(args[-1]))
    return 1, build


_DISPATCH: dict[str, tuple[int, object]] = {
    "HAdd.hAdd": _binop(lambda a, b: a + b),
    "HSub.hSub": _binop(lambda a, b: a - b),
    "HMul.hMul": _binop(lambda a, b: a * b),
    "HDiv.hDiv": _binop(lambda a, b: a / b),
    "HPow.hPow": _binop(lambda a, b: a ** b),
    "Eq":        (2, lambda args: expr_to_z3(args[-2]) == expr_to_z3(args[-1])),
    "Neg.neg":   _unop(lambda x: -x),
    "HNeg.hNeg": _unop(lambda x: -x),
    "Nat.succ":  (1, lambda args: expr_to_z3(args[-1]) + 1),
    "Int.ofNat": (1, lambda args: expr_to_z3(args[-1])),
    "Int.negSucc": (1, lambda args: -(expr_to_z3(args[-1]) + 1)),
}


def _ofnat_build(args):
    """Handle ``OfNat.ofNat`` — args[1] is the nat literal."""
    if len(args) >= 2:
        return expr_to_z3(args[1])
    return expr_to_z3(args[-1])


def _forall_build(expr: LeanInductiveValue):
    """Handle ``Expr.forallE`` — ∀ x : α, body."""
    # forallE(name, type, body, binderInfo)
    var_name = name_to_str(expr.fields[0])
    body = expr.fields[2]
    # Introduce a fresh Z3 variable and convert the body
    v = _var(var_name) if var_name else _var(f"_x")
    body_z3 = expr_to_z3(body)
    return z3.ForAll([v], body_z3)


def expr_to_z3(expr: LeanInductiveValue):
    """Convert a ``Lean.Expr`` (as ``LeanInductiveValue``) to a Z3 expression."""
    ctor = expr.ctor

    # --- Literal ---
    if ctor == "lit":
        lit = expr.fields[0]
        if lit.ctor == "natVal":
            return z3.IntVal(lit.fields[0])
        raise ValueError(f"unsupported Literal: {lit.ctor}")

    # --- Bound variable ---
    if ctor == "bvar":
        idx = expr.fields[0]
        return _var(f"x{idx}")

    # --- Free variable ---
    if ctor == "fvar":
        fvar_id = expr.fields[0]
        if hasattr(fvar_id, "fields") and fvar_id.fields:
            return _var(name_to_str(fvar_id.fields[0]))
        return _var(str(fvar_id))

    # --- mdata: unwrap transparently ---
    if ctor == "mdata":
        return expr_to_z3(expr.fields[1])

    # --- ForAll ---
    if ctor == "forallE":
        return _forall_build(expr)

    # --- Application: uncurry and dispatch ---
    if ctor == "app":
        head, args = uncurry_app(expr)

        if head.ctor == "const":
            head_name = name_to_str(head.fields[0])

            if head_name == "OfNat.ofNat":
                return _ofnat_build(args)

            entry = _DISPATCH.get(head_name)
            if entry is not None:
                min_args, builder = entry
                if len(args) >= min_args:
                    return builder(args)

        # Fallback: unknown function as a Z3 variable
        if head.ctor == "const":
            return _var(name_to_str(head.fields[0]))

    # --- Constant (standalone) ---
    if ctor == "const":
        name = name_to_str(expr.fields[0])
        if name in ("Nat.zero", "Int.zero"):
            return z3.IntVal(0)
        return _var(name)

    raise ValueError(f"cannot convert Expr.{ctor} to Z3: {expr!r}")


# ---------------------------------------------------------------------------
#  Proposition checkers
# ---------------------------------------------------------------------------

def z3_proves(prop) -> bool:
    """Check if Z3 can discharge a proposition."""
    s = z3.Solver()
    s.add(z3.Not(prop))
    return s.check() == z3.unsat


def z3_eq_check(lhs, rhs) -> bool:
    """Check if lhs == rhs via Z3."""
    return z3_proves(lhs == rhs)


def check_prop(prop) -> bool:
    """Check a proposition via Knuckledragger (if available) or plain Z3."""
    if HAS_KDR:
        try:
            kdr.lemma(prop)
            return True
        except Exception:
            return False
    return z3_proves(prop)


# ---------------------------------------------------------------------------
#  Tactic entry point
# ---------------------------------------------------------------------------

def decode_and_check_prop(expr) -> bool:
    """Convert a ``Lean.Expr`` (as ``LeanInductiveValue``) to Z3 and check
    if Z3 / Knuckledragger can discharge the proposition.

    Called from the Lean tactic: ``Py.ofLeanObj`` decodes the ``Lean.Expr``
    into a ``LeanInductiveValue`` tree (thanks to ``derive_python``), which
    is passed directly to this function.
    """
    prop = expr_to_z3(expr)
    return check_prop(prop)
