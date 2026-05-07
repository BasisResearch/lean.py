"""Tests for Python 3.10+ pattern matching on Lean inductives."""

import pytest

from lean_py import LeanInductiveValue
from lean_py.marshal import _CtorMeta


# ============================================================================
# isinstance checks
# ============================================================================


def test_isinstance_payload_ctor(example_lib):
    """isinstance(mkCircle(5), Shape.circle) should be True."""
    c = example_lib.mkCircle(5)
    assert isinstance(c, example_lib.Shape.circle)


def test_isinstance_wrong_ctor(example_lib):
    """isinstance(mkCircle(5), Shape.square) should be False."""
    c = example_lib.mkCircle(5)
    assert not isinstance(c, example_lib.Shape.square)


def test_isinstance_cross_type(example_lib):
    """A Name value should not be isinstance of a Color ctor."""
    red = LeanInductiveValue("Color", "red", 0, ())
    name = LeanInductiveValue("Name", "str", 1, ("parent", "leaf"))
    assert isinstance(red, example_lib.Color.red)
    assert not isinstance(name, example_lib.Color.red)


# ============================================================================
# match/case
# ============================================================================


def test_match_enum(example_lib):
    """Match enum-like Color values."""
    Color = example_lib.Color

    for val, expected in [
        (Color.red, "red"),
        (Color.green, "green"),
        (Color.blue, "blue"),
    ]:
        match val:
            case x if isinstance(x, Color.red):
                result = "red"
            case x if isinstance(x, Color.green):
                result = "green"
            case x if isinstance(x, Color.blue):
                result = "blue"
            case _:
                result = "unknown"
        assert result == expected


def test_match_payload(example_lib):
    """Match Shape.circle(r) and extract radius."""
    Shape = example_lib.Shape
    c = example_lib.mkCircle(5)

    match c:
        case Shape.circle(r):
            assert r == 5
        case _:
            pytest.fail("Should have matched Shape.circle")


def test_match_multi_field(example_lib):
    """Match Shape.rect(w, h) with multiple fields."""
    Shape = example_lib.Shape
    rect = Shape.rect(3, 4)

    match rect:
        case Shape.rect(w, h):
            assert w == 3
            assert h == 4
        case _:
            pytest.fail("Should have matched Shape.rect")


def test_match_recursive(example_lib):
    """Nested matching on Name-like types."""
    # Build a Name.str value manually
    anon = LeanInductiveValue("Name", "anonymous", 0, ())
    name = LeanInductiveValue("Name", "str", 1, (anon, "hello"))

    # Create a simple stand-in for Name type ctors
    class _NameNs:
        pass

    NameNs = _NameNs()
    NameNs.str = _CtorMeta("str", (), {
        '_ctor_name': 'str',
        '_type_name': 'Name',
        '_tag': 1,
        '__match_args__': ('_0', '_1'),
    })
    NameNs.anonymous = _CtorMeta("anonymous", (), {
        '_ctor_name': 'anonymous',
        '_type_name': 'Name',
        '_tag': 0,
        '__match_args__': (),
    })

    match name:
        case NameNs.str(parent, leaf):
            assert leaf == "hello"
            assert isinstance(parent, NameNs.anonymous)
        case _:
            pytest.fail("Should have matched Name.str")


# ============================================================================
# Indexed field access
# ============================================================================


def test_indexed_field_access(example_lib):
    """value._0, value._1 should return fields by index."""
    rect = example_lib.Shape.rect(10, 20)
    assert rect._0 == 10
    assert rect._1 == 20


def test_indexed_field_out_of_range(example_lib):
    """Accessing an out-of-range index raises AttributeError."""
    c = example_lib.mkCircle(5)
    with pytest.raises(AttributeError, match="out of range"):
        _ = c._1


# ============================================================================
# Backward compatibility
# ============================================================================


def test_nullary_backward_compat(example_lib):
    """Nullary ctor classes still have .ctor, .tag, .fields, repr(), and work with colorId."""
    Color = example_lib.Color
    red = Color.red
    assert red.ctor == "red"
    assert red.tag == 0
    assert red.fields == ()
    assert repr(red) == "Color.red"
    # Should still work when passed to a Lean function
    assert example_lib.colorId(Color.red) == 0
    assert example_lib.colorId(Color.green) == 1
    assert example_lib.colorId(Color.blue) == 2


def test_payload_ctor_callable(example_lib):
    """Shape.circle(10) still creates a LeanInductiveValue."""
    Shape = example_lib.Shape
    c = Shape.circle(10)
    assert isinstance(c, LeanInductiveValue)
    assert c.ctor == "circle"
    assert c.fields == (10,)


def test_structure_callable(example_lib):
    """Point(3, 4) still works via _StructureType.__call__."""
    p = example_lib.Point(3, 4)
    assert isinstance(p, LeanInductiveValue)
    assert p.fields == (3, 4)
    assert example_lib.pointNormSq(p) == 25


# ============================================================================
# Equality
# ============================================================================


def test_nullary_equality(example_lib):
    """Color.red == LeanInductiveValue("Color", "red", 0, ())."""
    Color = example_lib.Color
    val = LeanInductiveValue("Color", "red", 0, ())
    assert Color.red == val
    assert val == Color.red
