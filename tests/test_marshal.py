"""End-to-end tests for the Lean→Python marshalling pipeline."""

import pytest

from lean_py import LeanInductiveValue


def test_int_to_int(example_lib):
    assert example_lib.bar(0) == 1
    assert example_lib.bar(1) == 2
    assert example_lib.bar(-5) == -4
    assert example_lib.bar(100_000) == 100_001


def test_io_int(example_lib):
    # py_foo prints + returns x+1
    assert example_lib.foo(7) == 8


def test_string_arg_and_return(example_lib):
    assert example_lib.greet("world") == "Hello, world!"


def test_array_arg(example_lib):
    assert example_lib.sumList([1, 2, 3, 4, 5]) == 15
    assert example_lib.sumList([]) == 0
    assert example_lib.sumList([-1, -2, -3]) == -6
    # Also accessible by C export name.
    assert example_lib.py_sum_list([1, 2, 3]) == 6


def test_structure_round_trip(example_lib):
    p = example_lib.Point(3, 4)
    assert isinstance(p, LeanInductiveValue)
    assert example_lib.pointNormSq(p) == 25


def test_origin(example_lib):
    o = example_lib.origin(None)
    assert isinstance(o, LeanInductiveValue)
    assert o.fields == (0, 0)


def test_inductive_with_payload(example_lib):
    c = example_lib.mkCircle(5)
    assert isinstance(c, LeanInductiveValue)
    assert c.ctor == "circle"
    assert c.fields == (5,)
    # Pattern-match through Lean
    assert example_lib.shapePerimeter(c) == 30


def test_inductive_other_branches(example_lib):
    sq = example_lib.Shape.square(7)
    assert example_lib.shapePerimeter(sq) == 28
    rect = example_lib.Shape.rect(3, 4)
    assert example_lib.shapePerimeter(rect) == 14


def test_enum_inductive(example_lib):
    assert example_lib.colorId(example_lib.Color.red) == 0
    assert example_lib.colorId(example_lib.Color.green) == 1
    assert example_lib.colorId(example_lib.Color.blue) == 2


def test_repr(example_lib):
    p = example_lib.Point(1, 2)
    assert repr(p) == "Point.mk(1, 2)"
    assert repr(example_lib.Color.red) == "Color.red"


def test_registry_introspection(example_lib):
    # We registered at least one type and many functions.
    func_names = {f.exportName for f in example_lib.registry.funcs}
    assert "py_bar" in func_names
    assert "py_foo" in func_names
    assert "py_sum_list" in func_names
    type_names = {t.name for t in example_lib.registry.types}
    assert "Point" in type_names
    assert "Color" in type_names
    assert "Shape" in type_names
