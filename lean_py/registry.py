"""
Python-side mirror of the Lean `LeanPy.TypeRepr` data model.

These dataclasses are constructed from JSON returned by the
`<prefix>_funcs_json` and `<prefix>_types_json` symbols that
`#export_python_registry "<prefix>"` produces in a Lean library.
"""

from __future__ import annotations

import json
import keyword
from dataclasses import dataclass, field
from typing import Any


def py_ident(name: str) -> str:
    """A short Lean name made into a valid, non-keyword Python identifier."""
    short = name.split(".")[-1]
    if not short.isidentifier() or keyword.iskeyword(short):
        return short + "_"
    return short


@dataclass(frozen=True)
class TypeRepr:
    """Structural description of a Lean type as it appears in the registry.

    Each ``kind`` value corresponds to a Lean type family:

    - ``"unit"``, ``"bool"``, ``"nat"``, ``"int"``, ``"float"``,
      ``"char"``, ``"string"`` — primitive scalar types.
    - ``"uint"`` / ``"sint"`` — fixed-width integers (``bits`` gives width).
    - ``"array"``, ``"list"``, ``"option"`` — generic containers (``elem``
      holds the element type).
    - ``"prod"`` — product/pair (``a``, ``b``).
    - ``"io"`` — ``IO α`` (``elem`` holds ``α``).
    - ``"named"`` — a user-defined inductive registered via ``derive_python``
      (``name`` is the fully-qualified Lean name).
    - ``"pyobject"`` — the ``LeanPy.Python.Py`` opaque wrapper.
    - ``"opaque"`` — any type that lean-py cannot introspect.
    """

    kind: str
    # Optional fields, depending on kind
    bits: int | None = None
    elem: TypeRepr | None = None
    a: TypeRepr | None = None
    b: TypeRepr | None = None
    e: TypeRepr | None = None
    name: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TypeRepr:
        kind = data["kind"]
        kw: dict[str, Any] = {"kind": kind}
        if "bits" in data:
            kw["bits"] = int(data["bits"])
        if "elem" in data:
            kw["elem"] = cls.from_json(data["elem"])
        if "a" in data:
            kw["a"] = cls.from_json(data["a"])
        if "b" in data:
            kw["b"] = cls.from_json(data["b"])
        if "e" in data:
            kw["e"] = cls.from_json(data["e"])
        if "name" in data:
            kw["name"] = data["name"]
        return cls(**kw)

    def __repr__(self) -> str:
        return f"<TypeRepr {self.short()}>"

    def short(self) -> str:
        """A compact pseudo-Lean rendering for diagnostics."""
        k = self.kind
        if k in (
            "unit",
            "bool",
            "nat",
            "int",
            "float",
            "float32",
            "char",
            "string",
            "pyobject",
        ):
            return k.capitalize() if k != "string" else "String"
        if k == "uint":
            return f"UInt{self.bits}"
        if k == "sint":
            return f"Int{self.bits}"
        if k in ("array", "list", "option"):
            return f"{k.capitalize()} {self.elem.short()}"  # type: ignore[union-attr]
        if k == "prod":
            return f"({self.a.short()} × {self.b.short()})"  # type: ignore[union-attr]
        if k == "sum":
            return f"({self.a.short()} ⊕ {self.b.short()})"  # type: ignore[union-attr]
        if k == "io":
            return f"IO {self.elem.short()}"  # type: ignore[union-attr]
        if k == "except":
            return f"Except {self.e.short()} {self.a.short()}"  # type: ignore[union-attr]
        if k in ("named", "opaque"):
            return self.name or "?"
        return f"<{k}>"

    # -- unified type interpretation ------------------------------------------
    #
    # A ``TypeRepr`` is the single source of truth for a Lean type's Python
    # face. From it we derive both the *static* annotation (used by the stub
    # generator) and a *runtime* predicate over Python values (used for
    # argument validation). This mirrors nerodia's ``Typing = Py.Raw → Prop``,
    # where one description drives static hints and runtime checks alike —
    # adapted to lean.py's registry-driven design.

    def python_annotation(self, known_types: set[str] | None = None, named_prefix: str = "") -> str:
        """Render this type as a Python type-annotation string.

        ``known_types`` is the set of derived-type short names the caller has
        classes for; a ``named`` reference resolves to ``named_prefix + short``
        when known, else ``Any``. When ``known_types`` is ``None``, every named
        type is assumed present (used for diagnostics).
        """

        def rec(x: TypeRepr | None) -> str:
            return x.python_annotation(known_types, named_prefix) if x else "Any"

        k = self.kind
        if k == "unit":
            return "None"
        if k == "bool":
            return "bool"
        if k in ("nat", "int", "uint", "sint"):
            return "int"
        if k == "char":
            return "str"
        if k in ("float", "float32"):
            return "float"
        if k == "string":
            return "str"
        if k == "pyobject":
            return "Any"
        if k in ("array", "list"):
            return f"list[{rec(self.elem)}]" if self.elem else "list[Any]"
        if k == "option":
            return f"{rec(self.elem)} | None" if self.elem else "Any | None"
        if k == "prod":
            return f"tuple[{rec(self.a)}, {rec(self.b)}]"
        if k == "sum":
            return f"{rec(self.a)} | {rec(self.b)}"
        if k == "io":
            return rec(self.elem) if self.elem else "None"
        if k == "except":
            return rec(self.a) if self.a else "Any"
        if k in ("named", "opaque"):
            short = py_ident(self.name) if self.name else ""
            if not short:
                return "Any"
            if known_types is None or short in known_types:
                return f"{named_prefix}{short}"
            return "Any"
        return "Any"

    def matches(self, value: Any) -> bool:
        """Return True if ``value`` is a plausible Python value for this type.

        The runtime half of the unified interpretation: a structural predicate
        used to validate arguments before marshalling. Scalars and containers
        are checked precisely; ``named`` types are checked by identity when the
        value is a Lean inductive value and accepted leniently otherwise (the
        marshaller also accepts tuple/constructor spellings)."""
        k = self.kind
        if k == "unit":
            return value is None
        if k == "bool":
            return isinstance(value, bool)
        if k == "nat":
            return isinstance(value, int) and not isinstance(value, bool) and value >= 0
        if k in ("int", "sint"):
            return isinstance(value, int) and not isinstance(value, bool)
        if k == "uint":
            return isinstance(value, int) and not isinstance(value, bool) and value >= 0
        if k in ("float", "float32"):
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if k == "char":
            return isinstance(value, str) and len(value) == 1
        if k == "string":
            return isinstance(value, str)
        if k == "pyobject":
            return True
        if k in ("array", "list"):
            if not isinstance(value, (list, tuple)):
                return False
            return self.elem is None or all(self.elem.matches(v) for v in value)
        if k == "option":
            return value is None or (self.elem is not None and self.elem.matches(value))
        if k == "prod":
            return (
                isinstance(value, tuple)
                and len(value) == 2
                and self.a is not None
                and self.a.matches(value[0])
                and self.b is not None
                and self.b.matches(value[1])
            )
        if k == "sum":
            return (self.a is not None and self.a.matches(value)) or (
                self.b is not None and self.b.matches(value)
            )
        if k == "io":
            return self.elem is None or self.elem.matches(value)
        if k == "except":
            return self.a is None or self.a.matches(value)
        if k in ("named", "opaque"):
            return self._matches_named(value)
        return True

    def _matches_named(self, value: Any) -> bool:
        # A Lean inductive value/constructor carries its own type name; if so,
        # require it to match. Anything else (tuple spellings, opaque handles)
        # is accepted leniently.
        type_name = getattr(value, "_type_name", None)
        if type_name is None:
            type_name = getattr(type(value), "_type_name", None)
        if type_name is None:
            return True
        return self.name is None or py_ident(type_name) == py_ident(self.name)

    def check(self, value: Any, name: str = "value") -> None:
        """Raise ``TypeError`` if ``value`` does not match this type."""
        if not self.matches(value):
            raise TypeError(
                f"{name}: expected a value of Lean type `{self.short()}` "
                f"(Python {self.python_annotation()}), got {type(value).__name__} {value!r}"
            )


@dataclass(frozen=True)
class CtorInfo:
    """Metadata for a single constructor of a Lean inductive type.

    Attributes:
        name: Unqualified constructor name (e.g. ``"cons"`` for ``List.cons``).
        tag: Runtime integer tag (index in constructor order, starting at 0).
        fields: Tuple of :class:`TypeRepr` describing each positional field.
    """

    name: str
    tag: int
    fields: tuple[TypeRepr, ...]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> CtorInfo:
        return cls(
            name=data["name"],
            tag=int(data["tag"]),
            fields=tuple(TypeRepr.from_json(f) for f in data["fields"]),
        )


@dataclass(frozen=True)
class TypeInfo:
    """Registry entry for a Lean inductive type exposed via ``derive_python``.

    Attributes:
        name: Fully-qualified Lean name (e.g. ``"Lean.Expr"``).
        isStructure: True if the type is a single-constructor structure.
        isEnum: True if all constructors are nullary (enum-like).
        ctors: Constructors in declaration order.
    """

    name: str
    isStructure: bool
    isEnum: bool
    ctors: tuple[CtorInfo, ...]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TypeInfo:
        return cls(
            name=data["name"],
            isStructure=bool(data.get("isStructure", False)),
            isEnum=bool(data.get("isEnum", False)),
            ctors=tuple(CtorInfo.from_json(c) for c in data["ctors"]),
        )


@dataclass(frozen=True)
class FuncInfo:
    """Registry entry for a Lean function annotated with ``@[python]``.

    Attributes:
        declName: Fully-qualified Lean declaration name.
        exportName: C symbol name (the ``@[export ...]`` name).
        params: Positional parameter types in declaration order.
        returnType: Return type (may be wrapped in ``IO``).
    """

    declName: str
    exportName: str
    params: tuple[TypeRepr, ...]
    returnType: TypeRepr

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> FuncInfo:
        return cls(
            declName=data["declName"],
            exportName=data["exportName"],
            params=tuple(TypeRepr.from_json(p) for p in data["params"]),
            returnType=TypeRepr.from_json(data["returnType"]),
        )


@dataclass
class LibraryRegistry:
    """The complete type and function registry returned by a Lean library at load time.

    Built from JSON exported by the ``#export_python_registry`` command in Lean.

    Attributes:
        funcs: All ``@[python]``-annotated functions.
        types: All types registered via ``derive_python``.
    """

    funcs: tuple[FuncInfo, ...] = field(default_factory=tuple)
    types: tuple[TypeInfo, ...] = field(default_factory=tuple)

    @classmethod
    def from_json_strings(cls, funcs_json: str, types_json: str) -> LibraryRegistry:
        farr = json.loads(funcs_json) if funcs_json else []
        tarr = json.loads(types_json) if types_json else []
        # Dedupe types by name. `derive_python` for recursive inductives
        # adds two entries: a name-only placeholder (so self-references
        # resolve to `.named`), and the real `TypeInfo` with the full
        # constructor list. The order in the JSON depends on whether
        # the type comes from the importing module or a downstream
        # derive_python — both orderings can occur. To handle both
        # cases we keep the entry with the most constructors.
        best: dict[str, TypeInfo] = {}
        order: list[str] = []
        for raw in tarr:
            ti = TypeInfo.from_json(raw)
            if ti.name not in best:
                order.append(ti.name)
                best[ti.name] = ti
            elif len(ti.ctors) > len(best[ti.name].ctors):
                best[ti.name] = ti
        deduped_types: list[TypeInfo] = [best[n] for n in order]

        seen_fn: set[str] = set()
        deduped_funcs: list[FuncInfo] = []
        for raw in farr:
            fi = FuncInfo.from_json(raw)
            if fi.exportName in seen_fn:
                continue
            seen_fn.add(fi.exportName)
            deduped_funcs.append(fi)

        return cls(
            funcs=tuple(deduped_funcs),
            types=tuple(deduped_types),
        )

    def find_type(self, name: str) -> TypeInfo | None:
        for t in self.types:
            if t.name == name:
                return t
        return None

    def find_func(self, export_name: str) -> FuncInfo | None:
        for f in self.funcs:
            if f.exportName == export_name:
                return f
        return None
