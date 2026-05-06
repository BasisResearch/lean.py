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

from lean_py._runtime import get_lean_ffi, get_structs
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

class LeanInductiveValue:
    """A Python representation of a Lean inductive constructor.

    Attributes:
        ctor:   the constructor name (unqualified).
        tag:    integer tag.
        fields: tuple of decoded Python field values in declaration order.
    """

    __slots__ = ("ctor", "tag", "fields", "_type_name")

    def __init__(self, type_name: str, ctor: str, tag: int, fields: tuple) -> None:
        self._type_name = type_name
        self.ctor = ctor
        self.tag = tag
        self.fields = fields

    def __repr__(self) -> str:
        if not self.fields:
            return f"{self._type_name}.{self.ctor}"
        return f"{self._type_name}.{self.ctor}({', '.join(repr(f) for f in self.fields)})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LeanInductiveValue):
            return NotImplemented
        return (self._type_name, self.tag, self.fields) == (
            other._type_name, other.tag, other.fields,
        )

    def __hash__(self) -> int:
        return hash((self._type_name, self.tag, self.fields))


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
        # Accept either LeanInductiveValue or a (ctor_name, *args) tuple.
        if isinstance(value, LeanInductiveValue):
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
            return self.ffi.lean_box(ctor.tag)
        # Allocate a ctor object with tag and num_objs.
        obj = self.ffi.lean_alloc_ctor(ctor.tag, len(ctor.fields), 0)
        for i, (ftype, fv) in enumerate(zip(ctor.fields, field_values)):
            fwrap = self.wrapper_for(ftype)
            child = fwrap.to_lean(fv)
            self.ffi.lean_ctor_set(obj, i, child)
        return obj

    # -- public --------------------------------------------------------------

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
                # error case: stringify and raise
                err_ptr = _ctor_get(ffi, p, 0)
                ffi.lean_inc(err_ptr)
                msg = self._format_io_error(err_ptr)
                ffi.lean_dec(p)
                raise RuntimeError(f"Lean IO error: {msg}")
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
            # Opaque pointer; just hand it back.
            return self._opaque_wrapper(t)

        # Fall-through: opaque
        return self._opaque_wrapper(t)

    def _opaque_wrapper(self, t: TypeRepr) -> TypeWrapper:
        ObjPtr = self._lean_object_ptr
        def from_lean(p):
            return LeanObj(p, owned=True)
        def to_lean(v):
            if isinstance(v, LeanObj):
                p = v.release()
                return p
            return v
        return TypeWrapper(t, from_lean, to_lean, ObjPtr)

    def _format_io_error(self, ptr: Any) -> str:
        """Best-effort stringification of an `IO.Error` constructor."""
        try:
            tag = _ctor_tag(self.ffi, ptr)
            # `IO.Error.userError s` is ctor with one String field;
            # other ctors have varying shapes — just fall back to repr.
            if tag == 0 or tag == 11:
                # Try field 0 as a string.
                try:
                    s_ptr = _ctor_get(self.ffi, ptr, 0)
                    self.ffi.lean_inc(s_ptr)
                    s = self._lean_string_to_py(s_ptr)
                    self.ffi.lean_dec(s_ptr)
                    return s
                except Exception:
                    pass
            return f"<IO.Error tag={tag}>"
        except Exception:
            return "<unprintable IO.Error>"
