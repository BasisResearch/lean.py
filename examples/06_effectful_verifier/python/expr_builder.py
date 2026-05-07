"""
Lean.Expr construction helpers for building fully-elaborated Int propositions.

All builders operate on ``LeanInductiveValue`` trees via the loaded library's
constructor classes (``lib.Expr``, ``lib.Name``, etc.).

The marshaller uses the C smart constructors (``lean_name_mk_string``,
``lean_expr_mk_*``, etc.) to produce runtime objects with correct hash and
data fields, so Lean's environment lookups work correctly.
"""

from __future__ import annotations


class ExprBuilder:
    """Lean.Expr construction helpers bound to a loaded LeanLibrary."""

    def __init__(self, lib):
        self.Name = lib.Name
        self.Expr = lib.Expr
        self.Level = lib.Level
        self.Literal = lib.Literal
        self.BinderInfo = lib.BinderInfo
        self._z = self.Level.zero

    # -- Name helpers ---------------------------------------------------------

    def mk_name(self, s: str):
        """``"HAdd.hAdd"`` -> nested ``Name.str``."""
        n = self.Name.anonymous
        for part in s.split("."):
            n = self.Name.str(n, part)
        return n

    # -- Core Expr builders ---------------------------------------------------

    def mk_const(self, name: str, levels=None):
        return self.Expr.const(self.mk_name(name), levels or [])

    def mk_app(self, fn, arg):
        return self.Expr.app(fn, arg)

    def mk_apps(self, fn, *args):
        e = fn
        for a in args:
            e = self.Expr.app(e, a)
        return e

    def mk_bvar(self, idx: int):
        return self.Expr.bvar(idx)

    def mk_forall(self, name: str, ty, body, binder_info=None):
        bi = binder_info if binder_info is not None else self.BinderInfo.default
        return self.Expr.forallE(self.mk_name(name), ty, body, bi)

    def mk_nat_lit(self, n: int):
        return self.Expr.lit(self.Literal.natVal(n))

    def mk_sort(self, level):
        return self.Expr.sort(level)

    # -- Int-specific helpers -------------------------------------------------

    @property
    def INT(self):
        return self.mk_const("Int")

    def mk_int(self, n: int):
        if n >= 0:
            return self.mk_apps(self.mk_const("Int.ofNat"), self.mk_nat_lit(n))
        else:
            return self.mk_apps(self.mk_const("Int.negSucc"), self.mk_nat_lit(-n - 1))

    def _mk_int_binop(self, cls_name, h_inst_name, base_inst_name, a, b):
        z = self._z
        I = self.INT
        inst = self.mk_apps(self.mk_const(h_inst_name, [z]), I, self.mk_const(base_inst_name))
        return self.mk_apps(self.mk_const(cls_name, [z, z, z]), I, I, I, inst, a, b)

    def _mk_int_rel(self, cls_name, inst_name, a, b):
        z = self._z
        return self.mk_apps(self.mk_const(cls_name, [z]), self.INT, self.mk_const(inst_name), a, b)

    def mk_int_add(self, a, b):
        return self._mk_int_binop("HAdd.hAdd", "instHAdd", "Int.instAdd", a, b)

    def mk_int_sub(self, a, b):
        return self._mk_int_binop("HSub.hSub", "instHSub", "Int.instSub", a, b)

    def mk_int_mul(self, a, b):
        return self._mk_int_binop("HMul.hMul", "instHMul", "Int.instMul", a, b)

    def mk_int_gt(self, a, b):
        return self._mk_int_rel("GT.gt", "Int.instLTInt", a, b)

    def mk_int_ge(self, a, b):
        return self._mk_int_rel("GE.ge", "Int.instLEInt", a, b)

    def mk_int_lt(self, a, b):
        return self._mk_int_rel("LT.lt", "Int.instLTInt", a, b)

    def mk_int_le(self, a, b):
        return self._mk_int_rel("LE.le", "Int.instLEInt", a, b)
