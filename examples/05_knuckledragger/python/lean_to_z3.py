"""
Convert Lean.Expr ADT trees (as ``LeanInductiveValue``) to Z3 expressions.

Two consumption paths:

**Path A** — pure Python.  Python already holds ``LeanInductiveValue`` Expr
trees built via ``lib.Expr.app(...)`` etc.  Call ``expr_to_z3()`` directly.

**Path B** — tactic.  Lean wraps an ``Expr`` via ``Py.ofLeanObj`` and calls a
Python function.  ``decode_and_check_prop()`` decodes the ``LeanObjHandle``
with the marshaller and then converts to Z3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import kdrag as kdr
import z3

from lean_py.marshal import LeanInductiveValue

if TYPE_CHECKING:
    from lean_py.marshal import Marshaller


# ---------------------------------------------------------------------------
#  Name helpers
# ---------------------------------------------------------------------------


def name_to_str(name: LeanInductiveValue) -> str:
    """Walk a ``Lean.Name`` ADT (anonymous / str / num) to a dot-separated string."""
    parts: list[str] = []
    cur = name
    while True:
        match cur:
            case LeanInductiveValue(ctor="anonymous"):
                break
            case LeanInductiveValue(ctor="str", fields=(parent, leaf)):
                parts.append(leaf)
                cur = parent
            case LeanInductiveValue(ctor="num", fields=(parent, n)):
                parts.append(str(n))
                cur = parent
            case _:
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
        args.append(cur._1)  # arg
        cur = cur._0  # fn
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
    "HPow.hPow": _binop(lambda a, b: a**b),
    "Eq": (2, lambda args: expr_to_z3(args[-2]) == expr_to_z3(args[-1])),
    "Neg.neg": _unop(lambda x: -x),
    "HNeg.hNeg": _unop(lambda x: -x),
    "Nat.succ": (1, lambda args: expr_to_z3(args[-1]) + 1),
    "Int.ofNat": (1, lambda args: expr_to_z3(args[-1])),
    "Int.negSucc": (1, lambda args: -(expr_to_z3(args[-1]) + 1)),
}


def _ofnat_build(args):
    """Handle ``OfNat.ofNat`` — args[1] is the nat literal."""
    if len(args) >= 2:
        return expr_to_z3(args[1])
    return expr_to_z3(args[-1])


def expr_to_z3(expr: LeanInductiveValue):
    """Convert a ``Lean.Expr`` (as ``LeanInductiveValue``) to a Z3 expression."""
    match expr:
        # --- Literal ---
        case LeanInductiveValue(ctor="lit", fields=(lit,)):
            match lit:
                case LeanInductiveValue(ctor="natVal", fields=(n,)):
                    return z3.IntVal(n)
                case _:
                    raise ValueError(f"unsupported Literal: {lit.ctor}")

        # --- Bound variable ---
        case LeanInductiveValue(ctor="bvar", fields=(idx,)):
            return _var(f"x{idx}")

        # --- Free variable ---
        case LeanInductiveValue(ctor="fvar", fields=(fvar_id,)):
            if hasattr(fvar_id, "fields") and fvar_id.fields:
                return _var(name_to_str(fvar_id._0))
            return _var(str(fvar_id))

        # --- mdata: unwrap transparently ---
        case LeanInductiveValue(ctor="mdata", fields=(_, inner)):
            return expr_to_z3(inner)

        # --- ForAll: forallE(name, type, body, binderInfo) ---
        case LeanInductiveValue(ctor="forallE", fields=(name_val, _, body, *_)):
            var_name = name_to_str(name_val)
            v = _var(var_name) if var_name else _var("_x")
            return z3.ForAll([v], expr_to_z3(body))

        # --- Application: uncurry and dispatch ---
        case LeanInductiveValue(ctor="app"):
            head, args = uncurry_app(expr)

            if head.ctor == "const":
                head_name = name_to_str(head._0)

                if head_name == "OfNat.ofNat":
                    return _ofnat_build(args)

                entry = _DISPATCH.get(head_name)
                if entry is not None:
                    min_args, builder = entry
                    if len(args) >= min_args:
                        return builder(args)

                # Fallback: unknown function as a Z3 variable
                return _var(head_name)

        # --- Constant (standalone) ---
        case LeanInductiveValue(ctor="const", fields=(name_val, _)):
            name = name_to_str(name_val)
            if name in ("Nat.zero", "Int.zero"):
                return z3.IntVal(0)
            return _var(name)

    raise ValueError(f"cannot convert Expr.{expr.ctor} to Z3: {expr!r}")


# ---------------------------------------------------------------------------
#  Proposition checkers
# ---------------------------------------------------------------------------


def check_prop(prop) -> bool:
    """Check a proposition via Knuckledragger (backed by Z3)."""
    try:
        kdr.lemma(prop)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
#  Tactic entry point
# ---------------------------------------------------------------------------

_marshaller: Marshaller | None = None


def setup(lib) -> None:
    """Store a reference to the library's marshaller for ``decode_and_check_prop``."""
    global _marshaller
    _marshaller = lib.marshaller


def decode_and_check_prop(lean_obj) -> bool:
    """Decode a ``LeanObjHandle`` wrapping a ``Lean.Expr`` and check if
    Knuckledragger / Z3 can discharge the proposition.

    Called from the Lean tactic via ``Py.ofLeanObj`` + ``@[python]``.
    """
    if _marshaller is None:
        raise RuntimeError("lean_to_z3.setup(lib) must be called before decode_and_check_prop")
    expr_tree = _marshaller.decode_lean_obj("Lean.Expr", lean_obj)
    prop = expr_to_z3(expr_tree)
    return check_prop(prop)
