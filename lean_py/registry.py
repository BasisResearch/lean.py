"""
Python-side mirror of the Lean `LeanPy.TypeRepr` data model.

These dataclasses are constructed from JSON returned by the
`<prefix>_funcs_json` and `<prefix>_types_json` symbols that
`#export_python_registry "<prefix>"` produces in a Lean library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TypeRepr:
    """Structural description of a Lean type."""
    kind: str
    # Optional fields, depending on kind
    bits: int | None = None
    elem: "TypeRepr | None" = None
    a: "TypeRepr | None" = None
    b: "TypeRepr | None" = None
    e: "TypeRepr | None" = None
    name: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "TypeRepr":
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
        if k in ("unit", "bool", "nat", "int", "float", "float32", "char",
                 "string", "pyobject"):
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


@dataclass(frozen=True)
class CtorInfo:
    name: str
    tag: int
    fields: tuple[TypeRepr, ...]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "CtorInfo":
        return cls(
            name=data["name"],
            tag=int(data["tag"]),
            fields=tuple(TypeRepr.from_json(f) for f in data["fields"]),
        )


@dataclass(frozen=True)
class TypeInfo:
    name: str  # fully-qualified Lean name
    isStructure: bool
    isEnum: bool
    ctors: tuple[CtorInfo, ...]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "TypeInfo":
        return cls(
            name=data["name"],
            isStructure=bool(data.get("isStructure", False)),
            isEnum=bool(data.get("isEnum", False)),
            ctors=tuple(CtorInfo.from_json(c) for c in data["ctors"]),
        )


@dataclass(frozen=True)
class FuncInfo:
    declName: str
    exportName: str
    params: tuple[TypeRepr, ...]
    returnType: TypeRepr

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "FuncInfo":
        return cls(
            declName=data["declName"],
            exportName=data["exportName"],
            params=tuple(TypeRepr.from_json(p) for p in data["params"]),
            returnType=TypeRepr.from_json(data["returnType"]),
        )


@dataclass
class LibraryRegistry:
    """The complete registry returned by a Lean library at load time."""
    funcs: tuple[FuncInfo, ...] = field(default_factory=tuple)
    types: tuple[TypeInfo, ...] = field(default_factory=tuple)

    @classmethod
    def from_json_strings(cls, funcs_json: str, types_json: str) -> "LibraryRegistry":
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
