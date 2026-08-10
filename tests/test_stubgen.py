"""Tests for the `.pyi` stub generator (`lean_py.stubgen`)."""

import ast

from lean_py.registry import (
    CtorInfo,
    FuncInfo,
    LibraryRegistry,
    TypeInfo,
    TypeRepr,
)
from lean_py.stubgen import _annotation, generate_stub


def _t(kind, **kw):
    return TypeRepr(kind=kind, **kw)


# --- pure type-mapping unit tests (no Lean build required) ----------------

def test_annotation_scalars():
    known: set[str] = set()
    assert _annotation(_t("unit"), known) == "None"
    assert _annotation(_t("bool"), known) == "bool"
    assert _annotation(_t("nat"), known) == "int"
    assert _annotation(_t("int"), known) == "int"
    assert _annotation(_t("uint", bits=8), known) == "int"
    assert _annotation(_t("float"), known) == "float"
    assert _annotation(_t("float32"), known) == "float"
    assert _annotation(_t("char"), known) == "str"
    assert _annotation(_t("string"), known) == "str"
    assert _annotation(_t("pyobject"), known) == "Any"


def test_annotation_containers():
    known: set[str] = set()
    assert _annotation(_t("list", elem=_t("int")), known) == "list[int]"
    assert _annotation(_t("array", elem=_t("string")), known) == "list[str]"
    assert _annotation(_t("option", elem=_t("bool")), known) == "bool | None"
    assert _annotation(_t("prod", a=_t("int"), b=_t("string")), known) == "tuple[int, str]"
    assert _annotation(_t("sum", a=_t("int"), b=_t("bool")), known) == "int | bool"


def test_annotation_io_and_except_unwrap():
    known: set[str] = set()
    assert _annotation(_t("io", elem=_t("int")), known) == "int"
    assert _annotation(_t("io", elem=_t("unit")), known) == "None"
    assert _annotation(_t("except", e=_t("string"), a=_t("bool")), known) == "bool"


def test_annotation_named_resolution():
    # A named type that the stub defines resolves to its class; otherwise Any.
    assert _annotation(_t("named", name="My.Point"), {"Point"}) == "Point"
    assert _annotation(_t("named", name="Lean.Expr"), set()) == "Any"
    assert _annotation(_t("opaque", name="Foo.Bar"), set()) == "Any"


# --- end-to-end generation over a synthetic registry ----------------------

def _sample_registry() -> LibraryRegistry:
    point = TypeInfo(
        name="Demo.Point",
        isStructure=True,
        isEnum=False,
        ctors=(CtorInfo(name="mk", tag=0, fields=(_t("int"), _t("int"))),),
    )
    color = TypeInfo(
        name="Demo.Color",
        isStructure=False,
        isEnum=True,
        ctors=(
            CtorInfo(name="red", tag=0, fields=()),
            CtorInfo(name="green", tag=1, fields=()),
        ),
    )
    shape = TypeInfo(
        name="Demo.Shape",
        isStructure=False,
        isEnum=False,
        ctors=(
            CtorInfo(name="circle", tag=0, fields=(_t("float"),)),
            CtorInfo(name="rect", tag=1, fields=(_t("float"), _t("float"))),
        ),
    )
    add = FuncInfo(
        declName="Demo.add",
        exportName="demo_add",
        params=(_t("int"), _t("int")),
        returnType=_t("int"),
    )
    origin = FuncInfo(
        declName="Demo.origin",
        exportName="demo_origin",
        params=(_t("unit"),),
        returnType=_t("io", elem=_t("named", name="Demo.Point")),
    )
    return LibraryRegistry(funcs=(add, origin), types=(point, color, shape))


def test_generate_stub_is_valid_python():
    stub = generate_stub(_sample_registry(), "Demo")
    ast.parse(stub)  # raises on syntax error


def test_generate_stub_contents():
    stub = generate_stub(_sample_registry(), "Demo")
    # Structure: callable directly.
    assert "class Point(LeanInductiveValue):" in stub
    assert "def __init__(self, a0: int, a1: int, /) -> None: ..." in stub
    # Enum + inductive constructors.
    assert "class Color:" in stub
    assert "class red(LeanInductiveValue): ..." in stub
    assert "class circle(LeanInductiveValue):" in stub
    # Library class with typed methods and named-type resolution (via alias).
    assert "class DemoLibrary(LeanLibrary):" in stub
    assert "def add(self, a0: int, a1: int, /) -> int: ..." in stub
    assert "def origin(self, a0: None, /) -> _ty_Point: ..." in stub
    # Type classes live at module scope (column 0) so recursive/sibling refs
    # resolve; the library class references them through aliases.
    assert "\nclass Point(LeanInductiveValue):" in stub
    assert "_ty_Point = Point" in stub
    assert "Point: type[_ty_Point]" in stub


def test_generate_stub_empty_registry():
    stub = generate_stub(LibraryRegistry(), "Empty")
    ast.parse(stub)
    assert "class EmptyLibrary(LeanLibrary):" in stub
    assert "    pass" in stub


def test_write_stub_roundtrip(tmp_path):
    from lean_py import stubgen  # noqa: F401 — ensure importable

    stub = generate_stub(_sample_registry(), "Demo")
    out = tmp_path / "Demo.pyi"
    out.write_text(stub)
    ast.parse(out.read_text())
