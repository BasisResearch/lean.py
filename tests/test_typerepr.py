"""Tests for the unified `TypeRepr` interpretation: one representation drives
the static annotation *and* the runtime value predicate."""

import pytest

from lean_py.registry import TypeRepr


def _t(kind, **kw):
    return TypeRepr(kind=kind, **kw)


# --- static annotation (shared with the stub generator) -------------------


def test_python_annotation_matches_stub_mapping():
    assert _t("unit").python_annotation() == "None"
    assert _t("nat").python_annotation() == "int"
    assert _t("char").python_annotation() == "str"
    assert _t("list", elem=_t("int")).python_annotation() == "list[int]"
    assert _t("option", elem=_t("string")).python_annotation() == "str | None"
    assert _t("prod", a=_t("int"), b=_t("bool")).python_annotation() == "tuple[int, bool]"
    assert _t("io", elem=_t("unit")).python_annotation() == "None"
    # named resolution honours known_types + prefix.
    named = _t("named", name="My.Point")
    assert named.python_annotation({"Point"}, "_ty_") == "_ty_Point"
    assert named.python_annotation(set()) == "Any"
    assert named.python_annotation() == "Point"  # None => assume present


# --- runtime predicate ----------------------------------------------------


def test_matches_scalars():
    assert _t("unit").matches(None)
    assert not _t("unit").matches(0)
    assert _t("bool").matches(True)
    assert not _t("bool").matches(1)  # bool is not an int here
    assert _t("int").matches(5)
    assert not _t("int").matches(True)  # and int is not a bool
    assert _t("nat").matches(0)
    assert not _t("nat").matches(-1)
    assert _t("float").matches(3)
    assert _t("float").matches(3.5)
    assert _t("char").matches("a")
    assert not _t("char").matches("ab")
    assert _t("string").matches("hello")
    assert not _t("string").matches(5)
    assert _t("pyobject").matches(object())  # accepts anything


def test_matches_containers():
    assert _t("list", elem=_t("int")).matches([1, 2, 3])
    assert not _t("list", elem=_t("int")).matches([1, "x"])
    assert not _t("list", elem=_t("int")).matches(5)
    assert _t("option", elem=_t("int")).matches(None)
    assert _t("option", elem=_t("int")).matches(7)
    assert not _t("option", elem=_t("int")).matches("x")
    prod = _t("prod", a=_t("int"), b=_t("string"))
    assert prod.matches((1, "a"))
    assert not prod.matches((1, 2))
    assert not prod.matches((1,))


def test_matches_named_by_identity():
    class FakeInductive:
        _type_name = "Demo.Shape"

    shape = _t("named", name="Demo.Shape")
    point = _t("named", name="Demo.Point")
    assert shape.matches(FakeInductive())
    assert not point.matches(FakeInductive())
    # A value with no Lean identity is accepted leniently (tuple spellings etc).
    assert shape.matches(("circle", 5))


def test_check_raises_with_helpful_message():
    with pytest.raises(TypeError) as exc:
        _t("int").check("not an int", name="x")
    msg = str(exc.value)
    assert "x" in msg and "Int" in msg and "str" in msg
    # No error on a match.
    _t("int").check(5, name="x")


# --- opt-in end-to-end validation through a real library ------------------


def test_argument_typechecking_toggle(example_lib):
    from lean_py import set_argument_typechecking

    # bar : Int -> Int
    assert example_lib.bar(21) == 22
    set_argument_typechecking(True)
    try:
        with pytest.raises(TypeError):
            example_lib.bar("not an int")
        # A valid call still works with checking on.
        assert example_lib.bar(41) == 42
    finally:
        set_argument_typechecking(False)
    # With checking off again, the marshaller's own error path handles it.
    assert example_lib.bar(1) == 2
