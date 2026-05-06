"""
Convert Lean.Expr ADT trees (as ``LeanInductiveValue``) to SymPy expressions.

Two consumption paths:

**Path A** — pure Python.  Python already holds ``LeanInductiveValue`` Expr
trees built via ``lib.Expr.app(...)`` etc.  Call ``expr_to_sympy()`` directly.

**Path B** — tactic.  Lean wraps an ``Expr`` via ``Py.ofLeanObj`` and calls a
Python function.  ``decode_and_check_prop()`` decodes the ``LeanObjHandle``
with the marshaller and then converts to SymPy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sympy
from sympy import Integer, Symbol, Eq, simplify

if TYPE_CHECKING:
    from lean_py.marshal import LeanInductiveValue, Marshaller


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
            parts.append(cur.fields[1])   # (parent, string)
            cur = cur.fields[0]
        elif cur.ctor == "num":
            parts.append(str(cur.fields[1]))  # (parent, nat)
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
#  Main converter
# ---------------------------------------------------------------------------

# Dispatch table: head constant name -> (number of meaningful trailing args, builder)
# For elaborated Lean expressions, the first few args are type/instance params;
# we only look at the *last N* arguments.

def _binop(op):
    """Return a builder for a binary operation (last 2 args)."""
    def build(args):
        a = expr_to_sympy(args[-2])
        b = expr_to_sympy(args[-1])
        return op(a, b)
    return 2, build


def _unop(op):
    """Return a builder for a unary operation (last 1 arg)."""
    def build(args):
        return op(expr_to_sympy(args[-1]))
    return 1, build


_DISPATCH: dict[str, tuple[int, object]] = {
    "HAdd.hAdd": _binop(lambda a, b: a + b),
    "HSub.hSub": _binop(lambda a, b: a - b),
    "HMul.hMul": _binop(lambda a, b: a * b),
    "HDiv.hDiv": _binop(lambda a, b: a / b),
    "HPow.hPow": _binop(lambda a, b: a ** b),
    "Eq":        (2, lambda args: Eq(expr_to_sympy(args[-2]), expr_to_sympy(args[-1]))),
    "Neg.neg":   _unop(lambda x: -x),
    "HNeg.hNeg": _unop(lambda x: -x),
    "Nat.succ":  (1, lambda args: expr_to_sympy(args[-1]) + 1),
    "Int.ofNat": (1, lambda args: expr_to_sympy(args[-1])),
    "Int.negSucc": (1, lambda args: -(expr_to_sympy(args[-1]) + 1)),
}


def _ofnat_build(args):
    """Handle ``OfNat.ofNat`` — args[1] is the nat literal."""
    # OfNat.ofNat {α} (n : Nat) [inst : OfNat α n] : α
    # In the elaborated app chain the meaningful arg is index 1 (the Nat).
    if len(args) >= 2:
        return expr_to_sympy(args[1])
    return expr_to_sympy(args[-1])


def expr_to_sympy(expr: LeanInductiveValue) -> sympy.Basic:
    """Convert a ``Lean.Expr`` (as ``LeanInductiveValue``) to a SymPy expression.

    Handles the elaborated forms that Lean's kernel produces (with type and
    instance parameters baked in).
    """
    ctor = expr.ctor

    # --- Literal ---
    if ctor == "lit":
        lit = expr.fields[0]  # Lean.Literal
        if lit.ctor == "natVal":
            return Integer(lit.fields[0])
        raise ValueError(f"unsupported Literal: {lit.ctor}")

    # --- Bound variable ---
    if ctor == "bvar":
        return Symbol(f"x{expr.fields[0]}")

    # --- Free variable ---
    if ctor == "fvar":
        fvar_id = expr.fields[0]  # FVarId (single-ctor struct wrapping Name)
        if hasattr(fvar_id, "fields") and fvar_id.fields:
            return Symbol(name_to_str(fvar_id.fields[0]))
        return Symbol(str(fvar_id))

    # --- mdata: unwrap transparently ---
    if ctor == "mdata":
        # mdata(kvmap, expr)
        return expr_to_sympy(expr.fields[1])

    # --- Application: uncurry and dispatch ---
    if ctor == "app":
        head, args = uncurry_app(expr)

        if head.ctor == "const":
            head_name = name_to_str(head.fields[0])

            # OfNat.ofNat special case
            if head_name == "OfNat.ofNat":
                return _ofnat_build(args)

            entry = _DISPATCH.get(head_name)
            if entry is not None:
                min_args, builder = entry
                if len(args) >= min_args:
                    return builder(args)

        # Fallback: try to convert as a SymPy Symbol
        if head.ctor == "const":
            head_name = name_to_str(head.fields[0])
            return Symbol(head_name)

    # --- Constant (standalone, no args) ---
    if ctor == "const":
        name = name_to_str(expr.fields[0])
        # Common constants
        if name in ("Nat.zero", "Int.zero"):
            return Integer(0)
        return Symbol(name)

    raise ValueError(f"cannot convert Expr.{ctor} to SymPy: {expr!r}")


# ---------------------------------------------------------------------------
#  Proposition checkers
# ---------------------------------------------------------------------------

def sympy_prop_check(prop: sympy.Basic) -> bool:
    """Check if a SymPy proposition is identically true."""
    s = simplify(prop)
    return s is sympy.true or s == True  # noqa: E712


def sympy_eq_check(lhs: sympy.Basic, rhs: sympy.Basic) -> bool:
    """Check if ``simplify(lhs - rhs) == 0``."""
    return simplify(lhs - rhs) == 0


# ---------------------------------------------------------------------------
#  Tactic path (Path B): decode LeanObjHandle and check
# ---------------------------------------------------------------------------

_marshaller: Marshaller | None = None


def setup(lib) -> None:
    """Store a reference to the library's marshaller for ``decode_and_check_prop``."""
    global _marshaller
    _marshaller = lib.marshaller


def decode_and_check_prop(lean_obj) -> bool:
    """Decode a ``LeanObjHandle`` wrapping a ``Lean.Expr`` and check if the
    proposition it represents is identically true according to SymPy.

    Called from the Lean tactic via ``Py.ofLeanObj`` + ``@[python]``.
    """
    if _marshaller is None:
        raise RuntimeError(
            "lean_to_sympy.setup(lib) must be called before decode_and_check_prop"
        )
    expr_tree = _marshaller.decode_lean_obj("Lean.Expr", lean_obj)
    prop = expr_to_sympy(expr_tree)
    return sympy_prop_check(prop)
