"""
Marshalling between Python values and Lean runtime objects.

The shape of Lean's runtime is documented in `lean.h`. The key facts we
rely on here:

  - Small Nats / Bools / enum-like inductive constructors are unboxed
    (boxed scalars: `(value << 1) | 1`).
  - Large Nats are pointers to MPZ objects.
  - Strings are pointers to `lean_string_object` with a UTF-8 NUL-terminated
    payload.
  - Inductive types are pointers to `lean_ctor_object` with a runtime tag
    in `m_tag` and N child object pointers in `m_objs[]`. Constructors with
    only enum-like cases (no payloads) are encoded as boxed scalars whose
    value is the constructor index.
  - `IO α` is encoded the same way as `Except IO.Error α`: a ctor with
    `m_tag == 0` for Ok (one field) and `m_tag == 1` for Error.

All marshalling routines operate over the dynamic FFI built in `_runtime`.
"""

from __future__ import annotations

import ctypes
from ctypes import (
    POINTER, c_char_p, c_double, c_int8, c_int16, c_int32, c_int64,
    c_size_t, c_uint8, c_uint16, c_uint32, c_uint64, c_void_p,
)
from typing import Any, Callable

from lean_py._runtime import _ptr_as_int, get_lean_ffi, get_structs
from lean_py.registry import CtorInfo, FuncInfo, LibraryRegistry, TypeInfo, TypeRepr


# ============================================================================
#  Owned wrapper around a lean_object*
# ============================================================================


class LeanObj:
    """Owned Python-side handle to a Lean object pointer.

    On construction the object's reference count is *not* incremented —
    we assume the caller passes ownership of one reference to us. On
    destruction `lean_dec_ref` is called.

    Use `LeanObj.borrow(ptr)` to wrap a pointer without taking ownership
    (e.g. when the lean_object is stored elsewhere); the wrapper will
    `lean_inc` on construction.
    """

    __slots__ = ("_ptr", "_owned")

    def __init__(self, ptr: Any, *, owned: bool = True) -> None:
        self._ptr = ptr
        self._owned = owned

    @classmethod
    def borrow(cls, ptr: Any) -> "LeanObj":
        ffi = get_lean_ffi()
        if ptr:
            ffi.lean_inc(ptr)
        return cls(ptr, owned=True)

    @property
    def ptr(self) -> Any:
        return self._ptr

    def release(self) -> Any:
        """Return the raw pointer and stop owning it."""
        p = self._ptr
        self._ptr = None
        self._owned = False
        return p

    def __del__(self) -> None:
        if not self._owned or not self._ptr:
            return
        try:
            ffi = get_lean_ffi()
        except Exception:
            return
        try:
            ffi.lean_dec(self._ptr)
        except Exception:
            pass


# ============================================================================
#  Constructor-tag inspection
# ============================================================================


def _ctor_tag(ffi: Any, ptr: Any) -> int:
    """Tag of a Lean object — works for both scalar (enum) and pointer (ctor) forms."""
    if ffi.lean_is_scalar(ptr):
        return ffi.lean_unbox(ptr)
    return ffi.lean_ptr_tag(ptr)


def _ctor_get(ffi: Any, ptr: Any, i: int) -> Any:
    """The i-th ctor field as a raw lean_object pointer."""
    return ffi.lean_ctor_get(ptr, i)


# ============================================================================
#  Lean ↔ Python conversion (single value)
# ============================================================================


class TypeWrapper:
    """A pair of py↔lean conversion functions for a particular `TypeRepr`."""

    __slots__ = ("repr", "from_lean", "to_lean", "ctype")

    def __init__(
        self,
        type_repr: TypeRepr,
        from_lean: Callable[[Any], Any],
        to_lean: Callable[[Any], Any],
        ctype: Any,
    ) -> None:
        self.repr = type_repr
        self.from_lean = from_lean
        self.to_lean = to_lean
        self.ctype = ctype

    def __repr__(self) -> str:
        return f"<TypeWrapper {self.repr.short()}>"


def _is_enum_tag_only(ti: TypeInfo) -> bool:
    """Constructors with no payload are encoded as boxed scalars (the tag)."""
    return ti.isEnum or all(len(c.fields) == 0 for c in ti.ctors)


# ----------------------------------------------------------------------------
# Wrapper for a registered user inductive (`derive_python`)
# ----------------------------------------------------------------------------

class _CtorMeta(type):
    """Metaclass for constructor pattern-match classes.

    Overrides ``isinstance`` so that ``isinstance(value, Name.str)``
    returns True when ``value`` is a ``LeanInductiveValue`` with the
    matching constructor name and type name.  Also provides
    ``__match_args__`` for Python 3.10+ structural pattern matching.
    """

    def __call__(cls, *args):
        n_fields = len(cls.__match_args__) if hasattr(cls, '__match_args__') else 0
        if len(args) != n_fields:
            raise TypeError(
                f"{cls._type_name}.{cls._ctor_name} expects {n_fields} args, "
                f"got {len(args)}")
        return LeanInductiveValue(cls._type_name, cls._ctor_name, cls._tag, tuple(args))

    def __instancecheck__(cls, instance):
        if isinstance(instance, LeanInductiveValue):
            return instance.ctor == cls._ctor_name and instance._type_name == cls._type_name
        if type(instance) is _CtorMeta:
            # Allow isinstance(Color.red, Color.red) — both are _CtorMeta classes
            return instance._ctor_name == cls._ctor_name and instance._type_name == cls._type_name
        return False

    def __repr__(cls):
        return f"{cls._type_name}.{cls._ctor_name}"

    def __eq__(cls, other):
        if isinstance(other, LeanInductiveValue):
            return (other._type_name == cls._type_name
                    and other.ctor == cls._ctor_name
                    and other.fields == ())
        if isinstance(other, _CtorMeta):
            return cls._type_name == other._type_name and cls._ctor_name == other._ctor_name
        return NotImplemented

    def __hash__(cls):
        return hash((cls._type_name, cls._ctor_name))


class LeanInductiveValue:
    """A Python representation of a Lean inductive constructor.

    Attributes:
        ctor:   the constructor name (unqualified).
        tag:    integer tag.
        fields: tuple of decoded Python field values in declaration order.

    Supports Python 3.10+ structural pattern matching::

        match name_value:
            case Name.str(parent, leaf):
                print(f"name: {leaf}")
            case Name.anonymous():
                print("anonymous")

    Fields can also be accessed by index (``value._0``, ``value._1``, etc.).
    """

    __slots__ = ("ctor", "tag", "fields", "_type_name")

    def __init__(self, type_name: str, ctor: str, tag: int, fields: tuple) -> None:
        self._type_name = type_name
        self.ctor = ctor
        self.tag = tag
        self.fields = fields

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") and name[1:].isdigit():
            idx = int(name[1:])
            if idx < len(self.fields):
                return self.fields[idx]
            raise AttributeError(
                f"field index {idx} out of range (have {len(self.fields)} fields)")
        raise AttributeError(name)

    def __repr__(self) -> str:
        if not self.fields:
            return f"{self._type_name}.{self.ctor}"
        return f"{self._type_name}.{self.ctor}({', '.join(repr(f) for f in self.fields)})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LeanInductiveValue):
            return (self._type_name, self.tag, self.fields) == (
                other._type_name, other.tag, other.fields,
            )
        if type(other) is _CtorMeta:
            return (self._type_name == other._type_name
                    and self.ctor == other._ctor_name
                    and self.fields == ())
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._type_name, self.tag, self.fields))


# ============================================================================
#  Smart constructors for types with @[extern] ctor annotations
# ============================================================================


def _build_smart_ctors(ffi) -> dict[tuple[str, str], Callable]:
    """Register C smart constructors for Lean kernel types.

    ``Lean.Name``, ``Lean.Level``, and ``Lean.Expr`` constructors use
    ``@[extern]`` annotations in the Lean source that compute internal
    hash / data scalar fields.  Using bare ``lean_alloc_ctor`` for these
    types produces objects with missing scalar data, breaking environment
    lookups and other runtime operations.  We call the real C functions
    instead.

    Each entry maps ``(type_name, ctor_name)`` to a callable
    ``(ffi, ObjPtr, encoded_children: list) -> lean_object*``.
    The ``ObjPtr`` is a ctypes pointer type for casting the result.

    **Ownership**: despite the ``@&`` (borrowed) annotation in Lean source,
    these C constructors store child pointers directly **without**
    ``lean_inc``.  The Lean compiler's codegen relies on this: it never
    emits a ``lean_dec`` for arguments that are stored into the new ctor.
    From Python we must therefore **not** ``lean_dec`` the children after
    calling the smart constructor — the new object takes ownership of the
    one reference we pass in.
    """
    ctors: dict[tuple[str, str], Callable] = {}
    lib = ffi.lib

    def _sym(name):
        try:
            return getattr(lib, name)
        except AttributeError:
            return None

    def _call(fn, obj_args, ObjPtr):
        """Call *fn* with ``c_void_p`` args, cast result to *ObjPtr*."""
        fn.restype = c_void_p
        fn.argtypes = [c_void_p] * len(obj_args)
        raw = fn(*[_ptr_as_int(a) for a in obj_args])
        return ctypes.cast(c_void_p(raw), ObjPtr)

    # -- Lean.Name ----------------------------------------------------------
    _nmks = _sym("lean_name_mk_string")
    if _nmks:
        def _name_str(ffi, ObjPtr, ch):
            return _call(_nmks, ch, ObjPtr)
        ctors[("Lean.Name", "str")] = _name_str

    _nmkn = _sym("lean_name_mk_numeral")
    if _nmkn:
        def _name_num(ffi, ObjPtr, ch):
            return _call(_nmkn, ch, ObjPtr)
        ctors[("Lean.Name", "num")] = _name_num

    # -- Lean.Level ---------------------------------------------------------
    _lvl = {n: _sym(n) for n in [
        "lean_level_mk_zero", "lean_level_mk_succ", "lean_level_mk_max",
        "lean_level_mk_imax", "lean_level_mk_param", "lean_level_mk_mvar",
    ]}
    for cname, sym, nargs in [
        ("zero", "lean_level_mk_zero", 0),
        ("succ", "lean_level_mk_succ", 1),
        ("max",  "lean_level_mk_max",  2),
        ("imax", "lean_level_mk_imax", 2),
        ("param","lean_level_mk_param",1),
        ("mvar", "lean_level_mk_mvar", 1),
    ]:
        fn = _lvl.get(sym)
        if fn:
            def _mk(ffi, ObjPtr, ch, _fn=fn, _n=nargs):
                return _call(_fn, ch[:_n], ObjPtr)
            ctors[("Lean.Level", cname)] = _mk

    # -- Lean.Expr ----------------------------------------------------------
    # BinderInfo / Bool trailing args are passed as uint8 (the unboxed
    # scalar value), NOT as lean_object*.
    _expr = {
        "bvar":    (_sym("lean_expr_mk_bvar"),    1, False),
        "fvar":    (_sym("lean_expr_mk_fvar"),    1, False),
        "mvar":    (_sym("lean_expr_mk_mvar"),    1, False),
        "sort":    (_sym("lean_expr_mk_sort"),    1, False),
        "const":   (_sym("lean_expr_mk_const"),   2, False),
        "app":     (_sym("lean_expr_mk_app"),     2, False),
        "lam":     (_sym("lean_expr_mk_lambda"),  4, True),
        "forallE": (_sym("lean_expr_mk_forall"),  4, True),
        "letE":    (_sym("lean_expr_mk_let"),     5, True),
        "lit":     (_sym("lean_expr_mk_lit"),     1, False),
        "mdata":   (_sym("lean_expr_mk_mdata"),   2, False),
        "proj":    (_sym("lean_expr_mk_proj"),    3, False),
    }
    for cname, (fn, nargs, scalar_tail) in _expr.items():
        if fn is None:
            continue

        def _mk(ffi, ObjPtr, ch, _fn=fn, _n=nargs, _st=scalar_tail):
            c_args = []
            for i, c in enumerate(ch[:_n]):
                if _st and i == _n - 1:
                    # Trailing BinderInfo / Bool — unbox to uint8.
                    c_args.append(ffi.lean_unbox(c) if ffi.lean_is_scalar(c)
                                  else _ptr_as_int(c))
                else:
                    c_args.append(_ptr_as_int(c))
            _fn.restype = c_void_p
            _fn.argtypes = [c_void_p] * len(c_args)
            raw = _fn(*c_args)
            return ctypes.cast(c_void_p(raw), ObjPtr)
        ctors[("Lean.Expr", cname)] = _mk

    return ctors


# ============================================================================
#  Marshaller: builds wrappers from a registry
# ============================================================================


class Marshaller:
    """Builds and caches `TypeWrapper`s for a `LibraryRegistry`."""

    def __init__(self, registry: LibraryRegistry):
        self.registry = registry
        self.ffi = get_lean_ffi()
        self._structs = get_structs()
        self._lean_object_ptr = self._structs["_LeanObjectPtr"]
        self._cache: dict[str, TypeWrapper] = {}
        self._smart_ctors = _build_smart_ctors(self.ffi)

    # -- helpers -------------------------------------------------------------

    def _key(self, t: TypeRepr) -> str:
        # Stable key for caching — based on the json-style structural form.
        return repr(t)

    def _lean_string_to_py(self, ptr: Any) -> str:
        """Decode a Lean string object pointer into a Python str."""
        size = self.ffi.lean_string_size(ptr)
        if size <= 1:
            return ""
        cs = self.ffi.lean_string_cstr(ptr)
        raw = cs.value if isinstance(cs, ctypes.c_char_p) else cs
        return (raw or b"").decode("utf-8")

    def _py_to_lean_string(self, s: str) -> Any:
        """Build a Lean string object from a Python str. Returns owned ptr."""
        if not isinstance(s, str):
            raise TypeError(f"expected str, got {type(s).__name__}")
        return self.ffi.mk_string(s)

    def _lean_array_to_py(self, ptr: Any, elem_w: "TypeWrapper") -> list:
        n = self.ffi.lean_array_size(ptr)
        out = []
        for i in range(n):
            e_ptr = self.ffi.lean_array_get_core(ptr, i)
            # lean_array_get_core returns a borrowed pointer.
            # Most decoders expect an owned pointer — bump the refcount.
            self.ffi.lean_inc(e_ptr)
            out.append(elem_w.from_lean(e_ptr))
        return out

    def _py_to_lean_array(self, xs, elem_w: "TypeWrapper") -> Any:
        """Build a Lean Array from a Python iterable. Returns owned ptr."""
        items = list(xs)
        arr = self.ffi.lean_alloc_array(len(items), len(items))
        # arr's m_data[i] holds owned pointers.
        for i, x in enumerate(items):
            child = elem_w.to_lean(x)
            # Use lean_array_set_core (sets without bumping refcounts).
            self.ffi.lean_array_set_core(arr, i, child)
        return arr

    def _decode_inductive(self, ti: TypeInfo, ptr: Any) -> LeanInductiveValue:
        # Determine the constructor.
        tag = _ctor_tag(self.ffi, ptr)
        ctor = next((c for c in ti.ctors if c.tag == tag), None)
        if ctor is None:
            raise RuntimeError(
                f"unknown ctor tag {tag} for {ti.name}; expected one of "
                f"{[(c.tag, c.name) for c in ti.ctors]}"
            )
        # Decode fields.
        if not ctor.fields:
            return LeanInductiveValue(ti.name, ctor.name, tag, ())
        fields = []
        for i, ftype in enumerate(ctor.fields):
            fwrap = self.wrapper_for(ftype)
            child = _ctor_get(self.ffi, ptr, i)
            self.ffi.lean_inc(child)
            fields.append(fwrap.from_lean(child))
        return LeanInductiveValue(ti.name, ctor.name, tag, tuple(fields))

    def _encode_inductive(self, ti: TypeInfo, value: Any) -> Any:
        # Accept LeanInductiveValue, _CtorMeta classes, or (ctor_name, *args) tuple.
        if type(value) is _CtorMeta:
            ctor = next((c for c in ti.ctors if c.name == value._ctor_name), None)
            if ctor is None:
                raise ValueError(f"unknown ctor {value._ctor_name} for {ti.name}")
            field_values = ()
        elif isinstance(value, LeanInductiveValue):
            ctor = next((c for c in ti.ctors if c.name == value.ctor), None)
            if ctor is None:
                raise ValueError(f"unknown ctor {value.ctor} for {ti.name}")
            field_values = value.fields
        elif isinstance(value, tuple) and value and isinstance(value[0], str):
            ctor = next((c for c in ti.ctors if c.name == value[0]), None)
            if ctor is None:
                raise ValueError(f"unknown ctor {value[0]} for {ti.name}")
            field_values = value[1:]
        else:
            raise TypeError(f"cannot encode {value!r} as {ti.name}")
        if len(field_values) != len(ctor.fields):
            raise ValueError(
                f"{ti.name}.{ctor.name}: expected {len(ctor.fields)} fields, "
                f"got {len(field_values)}"
            )
        if not ctor.fields:
            # Check for nullary smart constructors (e.g. Level.zero).
            smart = self._smart_ctors.get((ti.name, ctor.name))
            if smart is not None:
                return smart(self.ffi, self._lean_object_ptr, [])
            return self.ffi.lean_box(ctor.tag)

        # Encode child values first (each returns an owned pointer).
        children = []
        for ftype, fv in zip(ctor.fields, field_values):
            fwrap = self.wrapper_for(ftype)
            children.append(fwrap.to_lean(fv))

        # If a smart constructor exists, use it (handles internal scalar
        # fields like Name hashes and Expr Data).  The smart ctor borrows
        # the children and decrements them; it returns an owned result.
        smart = self._smart_ctors.get((ti.name, ctor.name))
        if smart is not None:
            return smart(self.ffi, self._lean_object_ptr, children)

        # Default: allocate a plain ctor object.
        obj = self.ffi.lean_alloc_ctor(ctor.tag, len(ctor.fields), 0)
        for i, child in enumerate(children):
            self.ffi.lean_ctor_set(obj, i, child)
        return obj

    # -- public --------------------------------------------------------------

    def decode_lean_obj(self, type_name: str, lean_obj: "LeanObj") -> LeanInductiveValue:
        """Decode a ``LeanObj`` (raw ``lean_object*``) as a registered inductive.

        This is the entry point for Path B (tactic): Lean wraps an ``Expr``
        via ``Py.ofLeanObj``, Python receives a ``LeanObj``, and this method
        walks the runtime representation using the type's registry metadata.
        """
        ti = self.registry.find_type(type_name)
        if ti is None:
            raise ValueError(f"Type {type_name!r} not found in registry")
        # Borrow: _decode_inductive reads fields via lean_ctor_get (borrowed
        # pointers) and lean_inc's each child, so we don't consume the handle.
        self.ffi.lean_inc(lean_obj.ptr)
        return self._decode_inductive(ti, lean_obj.ptr)

    def wrapper_for(self, t: TypeRepr) -> TypeWrapper:
        key = self._key(t)
        if key in self._cache:
            return self._cache[key]
        w = self._build_wrapper(t)
        self._cache[key] = w
        return w

    def _build_wrapper(self, t: TypeRepr) -> TypeWrapper:
        k = t.kind
        ffi = self.ffi
        ObjPtr = self._lean_object_ptr

        if k == "unit":
            # Unit is encoded as the boxed scalar 0 (the `()` ctor).
            def from_lean(p):
                return None
            def to_lean(_):
                return ffi.lean_box(0)
            return TypeWrapper(t, from_lean, to_lean, ObjPtr)

        if k == "bool":
            def from_lean(p):
                return _ctor_tag(ffi, p) == 1
            def to_lean(b):
                return ffi.lean_box(1 if b else 0)
            return TypeWrapper(t, from_lean, to_lean, c_uint8)

        if k == "nat":
            # Small values are boxed scalars; use lean_uint64_of_nat at the FFI level.
            def from_lean(p):
                v = ffi.lean_uint64_of_nat(p)
                ffi.lean_dec(p)
                return v
            def to_lean(n):
                if n < 0:
                    raise ValueError("Nat must be ≥ 0")
                return ffi.lean_unsigned_to_nat(ctypes.c_uint(n & 0xFFFFFFFF).value) \
                    if n < (1 << 32) else ffi.lean_uint64_to_nat(ctypes.c_uint64(n).value)
            return TypeWrapper(t, from_lean, to_lean, ObjPtr)

        if k == "int":
            def from_lean(p):
                # Use lean_scalar_to_int / lean_int_to_int64 round-trip.
                if ffi.lean_is_scalar(p):
                    v = ffi.lean_scalar_to_int(p)
                else:
                    v = ffi.lean_int64_of_int(p)
                ffi.lean_dec(p)
                return v
            def to_lean(n):
                return ffi.lean_int64_to_int(ctypes.c_int64(n).value)
            return TypeWrapper(t, from_lean, to_lean, ObjPtr)

        if k == "string":
            def from_lean(p):
                s = self._lean_string_to_py(p)
                ffi.lean_dec(p)
                return s
            def to_lean(s):
                return self._py_to_lean_string(s)
            return TypeWrapper(t, from_lean, to_lean, ObjPtr)

        if k == "float":
            def from_lean(p):
                # IEEE doubles are passed by value, not pointer; this path is
                # only used when float appears in a generic context (boxed).
                v = ffi.lean_unbox_float(p)
                ffi.lean_dec(p)
                return v
            def to_lean(f):
                return ffi.lean_box_float(c_double(f).value)
            return TypeWrapper(t, from_lean, to_lean, c_double)

        if k == "uint":
            bits = t.bits or 64
            ct = {8: c_uint8, 16: c_uint16, 32: c_uint32, 64: c_uint64}[bits]
            return TypeWrapper(t, lambda v: int(v), lambda v: ct(int(v)).value, ct)

        if k == "sint":
            bits = t.bits or 64
            ct = {8: c_int8, 16: c_int16, 32: c_int32, 64: c_int64}[bits]
            return TypeWrapper(t, lambda v: int(v), lambda v: ct(int(v)).value, ct)

        if k == "char":
            # Char is a UInt32 codepoint at the runtime ABI.
            def from_lean(p):
                if ffi.lean_is_scalar(p):
                    n = ffi.lean_unbox(p)
                    return chr(n)
                ffi.lean_dec(p)
                raise RuntimeError("Char value was not scalar")
            def to_lean(c):
                if isinstance(c, str) and len(c) == 1:
                    c = ord(c)
                return ffi.lean_box(int(c))
            return TypeWrapper(t, from_lean, to_lean, c_uint32)

        if k == "array":
            inner = self.wrapper_for(t.elem)  # type: ignore[arg-type]
            def from_lean(p):
                xs = self._lean_array_to_py(p, inner)
                ffi.lean_dec(p)
                return xs
            def to_lean(xs):
                return self._py_to_lean_array(xs, inner)
            return TypeWrapper(t, from_lean, to_lean, ObjPtr)

        if k == "list":
            inner = self.wrapper_for(t.elem)  # type: ignore[arg-type]
            def from_lean(p):
                # List α: ctor 0 is `nil`, ctor 1 is `cons head tail`.
                out = []
                cur = p
                while True:
                    tag = _ctor_tag(ffi, cur)
                    if tag == 0:
                        break
                    head = _ctor_get(ffi, cur, 0)
                    ffi.lean_inc(head)
                    out.append(inner.from_lean(head))
                    cur = _ctor_get(ffi, cur, 1)
                ffi.lean_dec(p)
                return out
            def to_lean(xs):
                items = list(xs)
                # Build right-to-left.
                acc = ffi.lean_box(0)  # nil
                for x in reversed(items):
                    cell = ffi.lean_alloc_ctor(1, 2, 0)
                    ffi.lean_ctor_set(cell, 0, inner.to_lean(x))
                    ffi.lean_ctor_set(cell, 1, acc)
                    acc = cell
                return acc
            return TypeWrapper(t, from_lean, to_lean, ObjPtr)

        if k == "option":
            inner = self.wrapper_for(t.elem)  # type: ignore[arg-type]
            def from_lean(p):
                tag = _ctor_tag(ffi, p)
                if tag == 0:
                    ffi.lean_dec(p)
                    return None
                inner_ptr = _ctor_get(ffi, p, 0)
                ffi.lean_inc(inner_ptr)
                v = inner.from_lean(inner_ptr)
                ffi.lean_dec(p)
                return v
            def to_lean(v):
                if v is None:
                    return ffi.lean_box(0)
                cell = ffi.lean_alloc_ctor(1, 1, 0)
                ffi.lean_ctor_set(cell, 0, inner.to_lean(v))
                return cell
            return TypeWrapper(t, from_lean, to_lean, ObjPtr)

        if k == "prod":
            wa = self.wrapper_for(t.a)  # type: ignore[arg-type]
            wb = self.wrapper_for(t.b)  # type: ignore[arg-type]
            def from_lean(p):
                a_ptr = _ctor_get(ffi, p, 0)
                b_ptr = _ctor_get(ffi, p, 1)
                ffi.lean_inc(a_ptr); ffi.lean_inc(b_ptr)
                a = wa.from_lean(a_ptr); b = wb.from_lean(b_ptr)
                ffi.lean_dec(p)
                return (a, b)
            def to_lean(pr):
                a, b = pr
                cell = ffi.lean_alloc_ctor(0, 2, 0)
                ffi.lean_ctor_set(cell, 0, wa.to_lean(a))
                ffi.lean_ctor_set(cell, 1, wb.to_lean(b))
                return cell
            return TypeWrapper(t, from_lean, to_lean, ObjPtr)

        if k == "io":
            inner = self.wrapper_for(t.elem)  # type: ignore[arg-type]
            # IO is encoded as Except IO.Error α (where the second field
            # is the new RealWorld state). On Ok, m_objs[0] holds the
            # value (owned by the IO ctor); we inc to take ownership and
            # then let inner decode + drop it.
            def from_lean(p):
                tag = _ctor_tag(ffi, p)
                if tag == 0:
                    val_ptr = _ctor_get(ffi, p, 0)
                    ffi.lean_inc(val_ptr)   # +1 (now we share ownership)
                    ffi.lean_dec(p)          # drop the IO ctor → val_ptr's
                                             #   shared ownership stays at 1
                    return inner.from_lean(val_ptr)  # consumes val_ptr
                # error case: decode the IO.Error ctor and raise a typed
                # exception (LeanError or LeanPyCallbackError).
                err_ptr = _ctor_get(ffi, p, 0)
                ffi.lean_inc(err_ptr)
                exc = self._build_io_exception(err_ptr)
                ffi.lean_dec(p)
                raise exc
            def to_lean(v):
                # Wrap a value as an IO Ok result.
                cell = ffi.lean_alloc_ctor(0, 2, 0)
                ffi.lean_ctor_set(cell, 0, inner.to_lean(v))
                ffi.lean_ctor_set(cell, 1, ffi.lean_box(0))
                return cell
            return TypeWrapper(t, from_lean, to_lean, ObjPtr)

        if k == "named":
            ti = self.registry.find_type(t.name or "")
            if ti is None:
                return self._opaque_wrapper(t)
            # Enum-like inductives (all ctors are nullary) are unboxed
            # by the Lean compiler and passed across the C ABI as a small
            # unsigned integer (typically `uint8_t` if there are ≤ 256
            # ctors). Mirror that ABI on the Python side.
            is_enum = all(len(c.fields) == 0 for c in ti.ctors)
            if is_enum and len(ti.ctors) <= 256:
                # The Lean compiler unboxes payload-free inductives. At the
                # top-level C ABI a value-typed `MyEnum` parameter/return is
                # `uint8_t`; when nested as a `lean_object*` field of an
                # outer ctor it is a boxed scalar `(tag << 1) | 1`. The
                # wrapper produces both forms and the call-site picks the
                # right one based on `ctype`.
                def from_lean(tag):
                    if isinstance(tag, int):
                        n = tag
                    elif ffi.lean_is_scalar(tag):
                        n = ffi.lean_unbox(tag)
                    else:
                        n = ffi.lean_ptr_tag(tag)
                    ctor = next((c for c in ti.ctors if c.tag == n), None)
                    if ctor is None:
                        raise RuntimeError(f"unknown {ti.name} tag {n}")
                    return LeanInductiveValue(ti.name, ctor.name, n, ())
                def to_lean(v):
                    if isinstance(v, LeanInductiveValue):
                        return ffi.lean_box(v.tag)
                    if type(v) is _CtorMeta:
                        return ffi.lean_box(v._tag)
                    if isinstance(v, int):
                        return ffi.lean_box(v)
                    raise TypeError(f"cannot encode {v!r} as enum {ti.name}")
                return TypeWrapper(t, from_lean, to_lean, c_uint8)
            def from_lean(p):
                v = self._decode_inductive(ti, p)
                ffi.lean_dec(p)
                return v
            def to_lean(v):
                return self._encode_inductive(ti, v)
            return TypeWrapper(t, from_lean, to_lean, ObjPtr)

        if k == "pyobject":
            return self._py_object_wrapper(t)

        # Fall-through: opaque
        return self._opaque_wrapper(t)

    def _py_object_wrapper(self, t: TypeRepr) -> TypeWrapper:
        """Wrapper for the `pyobject` TypeRepr (Lean's `LeanPy.Python.Py`).

        When Lean returns a `Py`, the Lean side hands us a `lean_object*`
        wrapping a CPython `PyObject*`. We extract the `PyObject*` via
        `leanpy_unwrap_pyobject` (which bumps Py's refcount), turn it
        into a live Python object via `ctypes.cast(..., py_object).value`,
        then drop the Lean handle. The caller sees an honest-to-goodness
        Python value, not an opaque LeanObj.

        If the wrapped ``PyObject*`` is actually a ``LeanObjHandle``
        (created via ``Py.ofLeanObj`` on the Lean side), we return a
        ``LeanObj`` wrapping the inner ``lean_object*`` instead.

        For passing Python values back to Lean as `Py`, a Python-side
        `LeanObj` (i.e. round-tripping a previously-received handle) is
        accepted; arbitrary Python values are not (use `Py.ofString`
        etc. on the Lean side instead, or call into a Lean function
        that takes the appropriate primitive type).
        """
        ObjPtr = self._lean_object_ptr
        ffi = self.ffi
        # `leanpy_unwrap_pyobject` is exported from the C bridge.
        unwrap = ffi._find_leanpy_helper("leanpy_unwrap_pyobject")
        if unwrap is not None:
            unwrap.argtypes = [ObjPtr]
            unwrap.restype = ctypes.py_object

        # `leanpy_is_lean_obj_handle` returns the inner lean_object* pointer
        # value (as uintptr_t) if the Py wraps a LeanObjHandle, or 0.
        is_handle = ffi._find_leanpy_helper("leanpy_is_lean_obj_handle")
        if is_handle is not None:
            is_handle.argtypes = [ObjPtr]
            is_handle.restype = c_size_t

        def from_lean(p):
            if not p:
                return LeanObj(p, owned=True)
            # Check if this Py wraps a LeanObjHandle (transport unification).
            if is_handle is not None:
                inner_ptr = is_handle(p)
                if inner_ptr:
                    # It's a LeanObjHandle — return a LeanObj wrapping the
                    # inner lean_object*. We borrow (inc ref) since the
                    # LeanObjHandle owns its own reference.
                    inner = ctypes.cast(inner_ptr, ObjPtr)
                    ffi.lean_inc(inner)
                    ffi.lean_dec(p)
                    return LeanObj(inner, owned=True)
            if unwrap is None:
                return LeanObj(p, owned=True)
            try:
                py_val = unwrap(p)
            except Exception:
                ffi.lean_dec(p)
                return None
            ffi.lean_dec(p)
            return py_val

        def to_lean(v):
            if isinstance(v, LeanObj):
                ptr = v.ptr
                if ptr:
                    ffi.lean_inc(ptr)
                return ptr
            raise TypeError(
                "passing arbitrary Python values back to Lean as Py is not "
                "supported; convert via LeanPy.Python.Py.ofString / etc. on "
                "the Lean side, or pass through a LeanObj handle"
            )
        return TypeWrapper(t, from_lean, to_lean, ObjPtr)

    def _opaque_wrapper(self, t: TypeRepr) -> TypeWrapper:
        """A wrapper for any Lean type that we can't introspect (Py,
        kernel `GoalState`, anything not in the `derive_python` registry).

        Python sees these as `LeanObj` handles.

        Passing semantics: `to_lean` increments the refcount and keeps
        the `LeanObj` alive on the Python side. The Lean function
        receives an owned reference (matching `lean_obj_arg` calling
        convention). The +1 we add covers that ownership; the LeanObj's
        own ref is preserved so the same handle can be threaded through
        multiple ops.
        """
        ObjPtr = self._lean_object_ptr
        ffi = self.ffi
        def from_lean(p):
            return LeanObj(p, owned=True)
        def to_lean(v):
            if isinstance(v, LeanObj):
                p = v.ptr
                if p:
                    ffi.lean_inc(p)
                return p
            return v
        return TypeWrapper(t, from_lean, to_lean, ObjPtr)

    # Lean's `IO.Error` inductive (Init/System/IOError.lean), Lean 4.25.x:
    # the ctor order is the basis for the runtime tag. Anything we don't
    # recognise falls through to `f"tag{n}"`.
    #
    # Most ctors carry `(filename : Option String) (osCode : UInt32)
    # (details : String)`; `userError` carries `(msg : String)`;
    # `unexpectedEof` is nullary. We only look at field 0 here — for
    # non-userError variants that's typically the filename, so
    # `_format` shows it via `context["raw_field0"]`.
    _IO_ERROR_TAGS = {
        0:  "alreadyExists",
        1:  "otherError",
        2:  "resourceBusy",
        3:  "resourceVanished",
        4:  "unsupportedOperation",
        5:  "hardwareFault",
        6:  "unsatisfiedConstraints",
        7:  "illegalOperation",
        8:  "protocolError",
        9:  "timeExpired",
        10: "interrupted",
        11: "noFileOrDirectory",
        12: "invalidArgument",
        13: "permissionDenied",
        14: "resourceExhausted",
        15: "inappropriateType",
        16: "noSuchThing",
        17: "unexpectedEof",
        18: "userError",
    }

    def _string_field(self, ptr: Any, idx: int) -> str:
        """Decode field `idx` of `ptr` as a Lean string (best effort)."""
        try:
            s_ptr = _ctor_get(self.ffi, ptr, idx)
            self.ffi.lean_inc(s_ptr)
            s = self._lean_string_to_py(s_ptr)
            self.ffi.lean_dec(s_ptr)
            return s
        except Exception:
            return ""

    def _build_io_exception(self, ptr: Any) -> "Exception":
        """Decode an `IO.Error` ctor pointer into a typed exception.

        For `userError` — the most common, used by every `LeanPy.Python.*`
        bridge function on Python failure — the message has the form
        `"<TypeName>: <message>"` (built in `python_bridge.c::raise_py_error`).
        We reconstruct that as a `LeanPyCallbackError` so the original
        Python exception type is visible. Other ctors map to `LeanError`
        with the appropriate `kind`.
        """
        from lean_py.exceptions import (
            LeanError, LeanPyCallbackError, parse_io_error_message,
        )

        try:
            tag = _ctor_tag(self.ffi, ptr)
        except Exception:
            return LeanError("unknown", "<unprintable IO.Error>")

        kind = self._IO_ERROR_TAGS.get(tag, f"tag{tag}")

        # The first ctor field of every IO.Error variant is either a
        # String (filename / message) or a Nat — read it as best we can.
        field0 = self._string_field(ptr, 0)

        # `userError s` is the boundary case: payload is the user-supplied
        # string. The bridge encodes Python errors here.
        if kind == "userError":
            ptype, pmsg = parse_io_error_message(field0)
            if ptype:
                return LeanPyCallbackError(ptype, pmsg)
            return LeanError("userError", field0 or "<no message>")

        # Other ctors carry varying field shapes. Capture field0 as the
        # primary descriptor and leave a structured `context` so callers
        # can still access it.
        return LeanError(kind, field0 or f"<{kind} (no message)>",
                         context={"raw_field0": field0} if field0 else None)

    def _format_io_error(self, ptr: Any) -> str:
        """Legacy stringification — preserved for callers that just want
        a printable error message. Use `_build_io_exception` for typed
        exceptions."""
        try:
            return str(self._build_io_exception(ptr))
        except Exception:
            return "<unprintable IO.Error>"
