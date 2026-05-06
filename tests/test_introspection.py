"""End-to-end tests for the bidirectional introspection layer.

Phase 3a: `derive_python` of Lean.Expr / Name / Level / etc. exposes the
Lean kernel ADTs as fully-typed Python values. Tests:

  - Lean returns a constructed value → Python sees a `LeanInductiveValue`
    with the right ctor and fields recursively.
  - Python builds a value via `lib.Name.str(parent, "x")` → Lean reads
    the structure correctly.
"""

from __future__ import annotations

import pytest


def test_name_returned_from_lean(example_lib):
    """`makeName` returns a Lean.Name that Python decodes to a structured
    `LeanInductiveValue` with field types as expected."""
    n = example_lib.py_make_name(None)
    # Should be Name.str (Name.str Name.anonymous "foo") "bar"
    assert n.ctor == "str"
    assert len(n.fields) == 2
    parent, leaf = n.fields
    assert leaf == "bar"
    assert parent.ctor == "str"
    assert parent.fields[1] == "foo"
    grand = parent.fields[0]
    assert grand.ctor == "anonymous"
    assert grand.fields == ()


def test_name_round_trip(example_lib):
    """Build a Lean.Name in Python, hand it to Lean, get back the
    rendered string. Verifies Python → Lean direction for inductives
    we don't own."""
    Name = example_lib.Name
    name = Name.str(Name.str(Name.anonymous, "Nat"), "succ")
    s = example_lib.py_name_to_string(name)
    assert s == "Nat.succ"


def test_expr_returned_from_lean(example_lib):
    """`makeAppExpr` returns `Expr.app (Expr.const Nat.succ []) (Expr.const Nat.zero [])`."""
    e = example_lib.py_make_app_expr(None)
    assert e.ctor == "app"
    assert len(e.fields) == 2
    f, x = e.fields
    assert f.ctor == "const"
    # f.fields[0] is the Name
    assert f.fields[0].ctor == "str"
    # The "Nat.succ" name's leaf
    assert f.fields[0].fields[1] == "succ"
    assert x.ctor == "const"
    assert x.fields[0].fields[1] == "zero"


def test_expr_built_in_python(example_lib):
    """Python constructs an Expr.app from raw constructors and Lean
    decodes its structure."""
    Name = example_lib.Name
    Expr = example_lib.Expr
    nat_lit_name = Name.str(Name.anonymous, "Nat")
    succ_name = Name.str(nat_lit_name, "succ")
    zero_name = Name.str(nat_lit_name, "zero")
    f = Expr.const(succ_name, [])     # Expr.const "Nat.succ" []
    x = Expr.const(zero_name, [])     # Expr.const "Nat.zero" []
    e = Expr.app(f, x)
    s = example_lib.py_expr_describe(e)
    assert s == "app (const Nat.succ) (const Nat.zero)"


def test_expr_lit_described(example_lib):
    """`Expr.lit (Literal.natVal 7)` round-trips."""
    Expr = example_lib.Expr
    Literal = example_lib.Literal
    e = Expr.lit(Literal.natVal(7))
    s = example_lib.py_expr_describe(e)
    assert s == "natLit 7"


def test_kernel_types_registered(example_lib):
    """Smoke test: every kernel ADT we promised to expose is present
    on the library."""
    for name in ("Name", "Level", "Expr", "Syntax", "Literal",
                 "BinderInfo", "MVarId", "FVarId", "LevelMVarId",
                 "SourceInfo"):
        assert hasattr(example_lib, name), f"missing {name}"
    # Constructors
    assert example_lib.Name.anonymous.ctor == "anonymous"
    # `default` is the first BinderInfo ctor (an enum, lookup by tag).
    assert example_lib.BinderInfo.default.ctor == "default"
    assert example_lib.Level.zero.ctor == "zero"


def test_inductive_value_repr(example_lib):
    """`LeanInductiveValue.__repr__` shows the constructor + fields
    for a recursively-decoded value, useful for diagnostics."""
    n = example_lib.py_make_name(None)
    s = repr(n)
    assert "Name.str" in s
    assert "foo" in s and "bar" in s


# Phase 3b: live Py round-trip


def test_py_round_trip_list(example_lib):
    """A `Py` returned from Lean is now a *live* Python value, not an
    opaque `LeanObj`. Verifies the new `pyobject` marshalling."""
    py_list = example_lib.makeList123(None)
    assert isinstance(py_list, list)
    assert py_list == [1, 2, 3]
