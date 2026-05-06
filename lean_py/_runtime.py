"""Runtime dynamic binding of lean.h types and functions.

Creates ctypes Structure classes and FFI bindings dynamically at import time.
No generated files — everything is built from parsing lean.h.
"""

from __future__ import annotations

import ctypes
import functools
from ctypes import (
    POINTER, Structure, c_bool, c_char, c_char_p, c_double, c_float,
    c_int, c_int8, c_int16, c_int32, c_int64, c_long, c_size_t,
    c_ssize_t, c_uint, c_uint8, c_uint16, c_uint32, c_uint64, c_void_p,
)
from typing import Any

from lean_py._parse import HeaderModel, StructDef, FuncDecl, get_header_model
from lean_py.utils import all_lean_runtime_libs, find_lean_dynlib


def _ptr_as_int(p) -> int:
    """Convert any ctypes pointer-like value to a raw integer.

    macOS ctypes has a long-standing quirk: passing a `POINTER(struct)`
    instance directly to a `c_void_p`-typed parameter sometimes yields
    a corrupted value at the C boundary (the bug is reproducible with
    `restype = POINTER(...)` chained into another call). Using the raw
    integer pointer value side-steps the issue entirely.
    """
    if p is None:
        return 0
    if isinstance(p, int):
        return p
    return ctypes.cast(p, c_void_p).value or 0


# ============================================================================
# Type mapping
# ============================================================================

_TYPE_MAP: dict[str, Any] = {
    "void": None,
    "int": c_int,
    "unsigned": c_uint,
    "unsigned int": c_uint,
    "unsigned long": c_size_t,
    "unsigned long long": c_uint64,
    "long": c_long,
    "long long": c_int64,
    "char": c_char,
    "unsigned char": c_uint8,
    "unsigned short": c_uint16,
    "signed char": c_int8,
    "short": c_int16,
    "float": c_float,
    "double": c_double,
    "bool": c_bool,
    "size_t": c_size_t,
    "ptrdiff_t": c_ssize_t,
    "uint8_t": c_uint8,
    "uint16_t": c_uint16,
    "uint32_t": c_uint32,
    "uint64_t": c_uint64,
    "int8_t": c_int8,
    "int16_t": c_int16,
    "int32_t": c_int32,
    "int64_t": c_int64,
    "char *": c_char_p,
    "char const *": c_char_p,
    "void *": c_void_p,
    "void * *": POINTER(c_void_p),
}


def _resolve_type(c_type: str, structs: dict[str, type]) -> Any:
    """Resolve a C type string to a ctypes type, given known struct types."""
    c_type = " ".join(c_type.split())

    # Direct lookup (with lean_object* aliases)
    if c_type in _TYPE_MAP:
        return _TYPE_MAP[c_type]

    # lean_object pointer types
    if c_type in ("lean_object *", "lean_obj_arg", "b_lean_obj_arg",
                  "u_lean_obj_arg", "lean_obj_res", "b_lean_obj_res"):
        return structs.get("_LeanObjectPtr", c_void_p)

    if c_type == "lean_object * *":
        obj_ptr = structs.get("_LeanObjectPtr", c_void_p)
        return POINTER(obj_ptr)

    # Known opaque pointer types
    if c_type in ("lean_external_class *", "lean_external_finalize_proc",
                  "lean_external_foreach_proc", "lean_task_imp *"):
        return c_void_p

    # Pointer types
    if c_type.endswith("*"):
        base = c_type[:-1].strip()
        if base.endswith("*"):
            inner = _resolve_type(base, structs)
            return POINTER(inner) if inner is not None else c_void_p
        base_ct = _resolve_type(base, structs)
        if base_ct is None:
            return c_void_p
        return POINTER(base_ct)

    # Const qualifier
    if "const" in c_type:
        return _resolve_type(c_type.replace("const", "").strip(), structs)

    # Known struct name
    if c_type in structs:
        return structs[c_type]

    return c_void_p


# ============================================================================
# Dynamic struct creation
# ============================================================================

def _build_structs(model: HeaderModel) -> dict[str, type]:
    """Dynamically create ctypes Structure classes from the model."""
    structs: dict[str, type] = {}

    # Build lean_object first (others depend on it)
    lean_obj_def = next((s for s in model.structs if s.name == "lean_object"), None)
    if lean_obj_def:
        lean_object = _make_struct(lean_obj_def, structs)
        structs["lean_object"] = lean_object
        structs["_LeanObjectPtr"] = POINTER(lean_object)
        # Register pointer aliases in type map
        _TYPE_MAP["lean_object *"] = structs["_LeanObjectPtr"]
        _TYPE_MAP["lean_obj_arg"] = structs["_LeanObjectPtr"]
        _TYPE_MAP["b_lean_obj_arg"] = structs["_LeanObjectPtr"]
        _TYPE_MAP["u_lean_obj_arg"] = structs["_LeanObjectPtr"]
        _TYPE_MAP["lean_obj_res"] = structs["_LeanObjectPtr"]
        _TYPE_MAP["b_lean_obj_res"] = structs["_LeanObjectPtr"]

    # Build remaining structs
    for sdef in model.structs:
        if sdef.name == "lean_object":
            continue
        structs[sdef.name] = _make_struct(sdef, structs)

    return structs


def _make_struct(sdef: StructDef, known: dict[str, type]) -> type:
    """Create a ctypes Structure subclass dynamically."""
    fields = []
    for f in sdef.fields:
        ct = _resolve_type(f.c_type, known)
        if ct is None:
            ct = c_void_p
        if f.bitfield is not None:
            fields.append((f.name, ct, f.bitfield))
        else:
            fields.append((f.name, ct))

    cls = type(sdef.name, (Structure,), {"_fields_": fields})
    return cls


# ============================================================================
# Dynamic FFI class creation
# ============================================================================

def _build_ffi_class(model: HeaderModel, structs: dict[str, type]) -> type:
    """Dynamically create the LeanFFI class with all bindings."""
    LeanObjectPtr = structs["_LeanObjectPtr"]
    constants = model.constants

    def __init__(self):
        # Preload all Lean runtime shared libraries with RTLD_GLOBAL so
        # that downstream user libraries can resolve their @rpath references
        # to libleanshared / libLake_shared / libleanshared_1 / etc.
        self._preloaded_libs: list[ctypes.CDLL] = []
        for lib in all_lean_runtime_libs():
            try:
                self._preloaded_libs.append(
                    ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
                )
            except OSError:
                pass
        # The "main" libleanshared is the source of all the symbols we
        # care about for the FFI; prefer the canonical handle from the
        # toolchain.
        lib_path = find_lean_dynlib()
        self.lib = ctypes.CDLL(str(lib_path), mode=ctypes.RTLD_GLOBAL)
        # Additional handles to search for `leanpy_*` helpers. User
        # libraries loaded via `LeanLibrary` will register their handle
        # here so the FFI's inc/dec/alloc helpers can find the C
        # bridge symbols statically linked into the user library.
        self._extra_handles: list[ctypes.CDLL] = []
        self._missing_symbols: list[str] = []
        self._bind_exported(self.lib)
        self._bind_inline_impls()

        # lean_initialize is not in lean.h but exists in libleanshared
        if not hasattr(self, "lean_initialize"):
            self.lean_initialize = self.lib.lean_initialize
        global _ffi_initialized
        if not _ffi_initialized:
            _ffi_initialized = True
            self.lean_initialize()

    def register_handle(self, lib):
        """Register an additional dlopen handle as a source of symbols
        when looking up `leanpy_*` helpers. Called by `LeanLibrary` after
        loading a user dylib."""
        if lib not in self._extra_handles:
            self._extra_handles.append(lib)
        if hasattr(self, "_helper_cache"):
            self._helper_cache.clear()

    def _find_leanpy_helper(self, name):
        """Find a `leanpy_*` helper symbol in any registered library.
        Caches the result to avoid repeated dlsym calls."""
        if not hasattr(self, "_helper_cache"):
            self._helper_cache = {}
        if name in self._helper_cache:
            return self._helper_cache[name]
        for h in self._extra_handles:
            try:
                fn = getattr(h, name)
                self._helper_cache[name] = fn
                return fn
            except AttributeError:
                continue
        try:
            fn = getattr(self.lib, name)
            self._helper_cache[name] = fn
            return fn
        except AttributeError:
            self._helper_cache[name] = None
            return None

    def _bind_exported(self, lib):
        for func in model.exported_functions:
            if func.is_variadic or not func.name:
                continue
            try:
                cfunc = getattr(lib, func.name)
                if func.params:
                    cfunc.argtypes = [_resolve_type(p.c_type, structs) for p in func.params]
                restype = _resolve_type(func.return_type, structs)
                if restype is not None:
                    cfunc.restype = restype
                setattr(self, func.name, cfunc)
            except AttributeError:
                self._missing_symbols.append(func.name)

    def _bind_inline_impls(self):
        """No-op; inline methods are defined directly on the class."""
        pass

    # Build the class dict with __init__ and exported binding setup
    class_dict = {
        "__init__": __init__,
        "_bind_exported": _bind_exported,
        "_bind_inline_impls": _bind_inline_impls,
        "register_handle": register_handle,
        "_find_leanpy_helper": _find_leanpy_helper,
    }

    # Add inline method implementations
    _add_inline_methods(class_dict, structs, constants)

    # Add helper methods
    _add_helper_methods(class_dict, structs)

    return type("LeanFFI", (), class_dict)


def _add_inline_methods(class_dict: dict, structs: dict, constants: dict):
    """Add Python implementations of key static inline functions."""
    LeanObjectPtr = structs["_LeanObjectPtr"]
    _SCALAR_BIT = 1

    def _ptr_int(o):
        if o is None:
            return 0
        return ctypes.cast(o, c_void_p).value or 0

    def lean_is_scalar(self, o):
        return _ptr_int(o) & _SCALAR_BIT == 1

    def lean_box(self, n):
        if isinstance(n, int):
            ptr_val = (n << 1) | 1
        else:
            ptr_val = (_ptr_int(n) << 1) | 1
        return ctypes.cast(c_void_p(ptr_val), LeanObjectPtr)

    def lean_unbox(self, o):
        return _ptr_int(o) >> 1

    def lean_ptr_tag(self, o):
        return o.contents.m_tag

    def lean_ptr_other(self, o):
        return o.contents.m_other

    def lean_is_mt(self, o):
        return o.contents.m_rc < 0

    def lean_is_st(self, o):
        return o.contents.m_rc > 0

    def lean_is_persistent(self, o):
        return o.contents.m_rc == 0

    def lean_has_rc(self, o):
        return o.contents.m_rc != 0

    def lean_inc_ref(self, o):
        if o is None:
            return
        helper = self._find_leanpy_helper("leanpy_inc_ref")
        if helper is not None:
            helper.argtypes = [c_void_p]
            helper.restype = None
            helper(_ptr_as_int(o))
            return
        if o.contents.m_rc > 0:
            o.contents.m_rc += 1

    def lean_inc_ref_n(self, o, n):
        if o is None:
            return
        helper = self._find_leanpy_helper("leanpy_inc_ref_n")
        if helper is not None:
            helper.argtypes = [c_void_p, c_size_t]
            helper.restype = None
            helper(_ptr_as_int(o), n)
            return
        if o.contents.m_rc > 0:
            o.contents.m_rc += n

    def lean_dec_ref(self, o):
        # Delegate to the C-side helper that correctly handles MT objects
        # and properly invokes the runtime's deallocation chain.
        if o is None:
            return
        helper = self._find_leanpy_helper("leanpy_dec_ref")
        if helper is not None:
            helper.argtypes = [c_void_p]
            helper.restype = None
            helper(_ptr_as_int(o))
            return
        # Fallback — best-effort (may not handle MT correctly).
        if o.contents.m_rc > 1:
            o.contents.m_rc -= 1
        elif o.contents.m_rc != 0:
            self.lean_dec_ref_cold(o)

    def lean_inc(self, o):
        if not self.lean_is_scalar(o):
            self.lean_inc_ref(o)

    def lean_inc_n(self, o, n):
        if not self.lean_is_scalar(o):
            self.lean_inc_ref_n(o, n)

    def lean_dec(self, o):
        if not self.lean_is_scalar(o):
            self.lean_dec_ref(o)

    def lean_is_ctor(self, o):
        return self.lean_ptr_tag(o) <= constants.get("LeanMaxCtorTag", 243)

    def lean_is_closure(self, o):
        return self.lean_ptr_tag(o) == constants.get("LeanClosure", 245)

    def lean_is_array(self, o):
        return self.lean_ptr_tag(o) == constants.get("LeanArray", 246)

    def lean_is_sarray(self, o):
        return self.lean_ptr_tag(o) == constants.get("LeanScalarArray", 248)

    def lean_is_string(self, o):
        return self.lean_ptr_tag(o) == constants.get("LeanString", 249)

    def lean_is_mpz(self, o):
        return self.lean_ptr_tag(o) == constants.get("LeanMPZ", 250)

    def lean_is_thunk(self, o):
        return self.lean_ptr_tag(o) == constants.get("LeanThunk", 251)

    def lean_is_task(self, o):
        return self.lean_ptr_tag(o) == constants.get("LeanTask", 252)

    def lean_is_promise(self, o):
        return self.lean_ptr_tag(o) == constants.get("LeanPromise", 244)

    def lean_is_external(self, o):
        return self.lean_ptr_tag(o) == constants.get("LeanExternal", 254)

    def lean_is_ref(self, o):
        return self.lean_ptr_tag(o) == constants.get("LeanRef", 253)

    def lean_obj_tag(self, o):
        if self.lean_is_scalar(o):
            return self.lean_unbox(o)
        return self.lean_ptr_tag(o)

    def lean_is_exclusive(self, o):
        return o.contents.m_rc == 1 if o.contents.m_rc > 0 else False

    def lean_is_shared(self, o):
        return o.contents.m_rc > 1 if o.contents.m_rc > 0 else False

    def lean_set_st_header(self, o, tag, other):
        o.contents.m_rc = 1
        o.contents.m_tag = tag
        o.contents.m_other = other
        o.contents.m_cs_sz = 0

    def lean_ctor_num_objs(self, o):
        return self.lean_ptr_other(o)

    def lean_ctor_get(self, o, i):
        ctor_cls = structs.get("lean_ctor_object")
        ctor = ctypes.cast(o, POINTER(ctor_cls))
        offset = ctor_cls.m_objs.offset
        addr = ctypes.addressof(ctor.contents) + offset
        arr = ctypes.cast(addr, POINTER(LeanObjectPtr * (i + 1)))
        return arr.contents[i]

    def lean_ctor_set(self, o, i, v):
        ctor_cls = structs.get("lean_ctor_object")
        ctor = ctypes.cast(o, POINTER(ctor_cls))
        offset = ctor_cls.m_objs.offset
        addr = ctypes.addressof(ctor.contents) + offset
        arr = ctypes.cast(addr, POINTER(LeanObjectPtr * (i + 1)))
        arr.contents[i] = v

    def lean_array_size(self, o):
        arr_cls = structs.get("lean_array_object")
        arr = ctypes.cast(o, POINTER(arr_cls))
        return arr.contents.m_size

    def lean_array_get_core(self, o, i):
        arr_cls = structs.get("lean_array_object")
        arr = ctypes.cast(o, POINTER(arr_cls))
        offset = arr_cls.m_data.offset
        addr = ctypes.addressof(arr.contents) + offset
        ptr_array = ctypes.cast(addr, POINTER(LeanObjectPtr * (i + 1)))
        return ptr_array.contents[i]

    def lean_string_size(self, o):
        str_cls = structs.get("lean_string_object")
        s = ctypes.cast(o, POINTER(str_cls))
        return s.contents.m_size

    def lean_string_len(self, o):
        str_cls = structs.get("lean_string_object")
        s = ctypes.cast(o, POINTER(str_cls))
        return s.contents.m_length

    def lean_string_cstr(self, o):
        str_cls = structs.get("lean_string_object")
        s = ctypes.cast(o, POINTER(str_cls))
        offset = str_cls.m_data.offset
        addr = ctypes.addressof(s.contents) + offset
        return ctypes.cast(addr, c_char_p)

    # ----- Allocation primitives (delegated to leanpy_native helpers) -----
    def lean_alloc_ctor(self, tag, num_objs, scalar_sz):
        fn = self._find_leanpy_helper("leanpy_alloc_ctor")
        if fn is None:
            raise RuntimeError("leanpy_alloc_ctor not found — leanpy_native not linked")
        fn.argtypes = [c_uint, c_uint, c_uint]
        fn.restype = LeanObjectPtr
        return fn(tag, num_objs, scalar_sz)

    def lean_alloc_array(self, size, capacity):
        fn = self._find_leanpy_helper("leanpy_alloc_array")
        if fn is None:
            raise RuntimeError("leanpy_alloc_array not found — leanpy_native not linked")
        fn.argtypes = [c_size_t, c_size_t]
        fn.restype = LeanObjectPtr
        return fn(size, capacity)

    def lean_array_set_core(self, o, i, v):
        arr_cls = structs.get("lean_array_object")
        arr = ctypes.cast(o, POINTER(arr_cls))
        offset = arr_cls.m_data.offset
        addr = ctypes.addressof(arr.contents) + offset
        ptr_array = ctypes.cast(addr, POINTER(LeanObjectPtr * (i + 1)))
        ptr_array.contents[i] = v

    # ----- Numeric conversions (inline in lean.h) -----
    def lean_box_uint64(self, v):
        # Boxed uint64: small object holding the 64-bit value.
        # Use the exported lean_box_uint64 if present.
        fn = getattr(self.lib, "lean_box_uint64", None)
        if fn is not None:
            fn.argtypes = [c_uint64]; fn.restype = LeanObjectPtr
            return fn(v)
        # Fallback: scalar tagged pointer (only valid for small values).
        return self.lean_box(v)

    def lean_unbox_uint64(self, o):
        fn = getattr(self.lib, "lean_unbox_uint64", None)
        if fn is not None:
            fn.argtypes = [LeanObjectPtr]; fn.restype = c_uint64
            return fn(o)
        return self.lean_unbox(o)

    def lean_box_float(self, v):
        # `lean_box_float` is `static inline` in lean.h, so it's not a
        # linkable symbol — inline it: alloc a ctor with one double of
        # scalar payload and store the value at offset 0 of the
        # post-m_objs region.
        ctor = self.lean_alloc_ctor(0, 0, ctypes.sizeof(c_double))
        ctor_cls = structs.get("lean_ctor_object")
        c = ctypes.cast(ctor, POINTER(ctor_cls))
        addr = ctypes.addressof(c.contents) + ctor_cls.m_objs.offset
        ctypes.cast(addr, POINTER(c_double))[0] = v
        return ctor

    def lean_unbox_float(self, o):
        ctor_cls = structs.get("lean_ctor_object")
        c = ctypes.cast(o, POINTER(ctor_cls))
        addr = ctypes.addressof(c.contents) + ctor_cls.m_objs.offset
        return ctypes.cast(addr, POINTER(c_double))[0]

    def lean_unsigned_to_nat(self, n):
        fn = getattr(self.lib, "lean_unsigned_to_nat", None)
        if fn is None:
            return self.lean_box(n)
        fn.argtypes = [c_uint]; fn.restype = LeanObjectPtr
        return fn(n)

    def lean_uint64_to_nat(self, n):
        fn = getattr(self.lib, "lean_uint64_to_nat", None)
        if fn is None:
            return self.lean_box(n)
        fn.argtypes = [c_uint64]; fn.restype = LeanObjectPtr
        return fn(n)

    def lean_uint64_of_nat(self, p):
        # Inline: small scalar fast-path; large path via lean_uint64_of_big_nat.
        if self.lean_is_scalar(p):
            return int(self.lean_unbox(p))
        fn = getattr(self.lib, "lean_uint64_of_big_nat", None)
        if fn is None:
            raise RuntimeError("lean_uint64_of_big_nat not found and Nat is not scalar")
        fn.argtypes = [LeanObjectPtr]; fn.restype = c_uint64
        return int(fn(p))

    def lean_int64_to_int(self, n):
        # Prefer the C-side helper from leanpy_native, which delegates
        # to the static-inline `lean_int64_to_int` exactly.
        fn = self._find_leanpy_helper("leanpy_int64_to_int")
        if fn is not None:
            fn.argtypes = [c_int64]; fn.restype = LeanObjectPtr
            return fn(n)
        # Fallback (mirrors `lean.h`): encode int32-range as a scalar.
        if -(1 << 31) <= n <= (1 << 31) - 1:
            return self.lean_box(n & 0xFFFFFFFF)
        big = getattr(self.lib, "lean_big_int64_to_int", None)
        if big is None:
            return self.lean_box(n & ((1 << 63) - 1))
        big.argtypes = [c_int64]; big.restype = LeanObjectPtr
        return big(n)

    def lean_int64_of_int(self, p):
        fn = self._find_leanpy_helper("leanpy_int64_of_int")
        if fn is not None:
            fn.argtypes = [LeanObjectPtr]; fn.restype = c_int64
            return int(fn(p))
        if self.lean_is_scalar(p):
            return int(self.lean_scalar_to_int(p))
        raise RuntimeError("leanpy_int64_of_int not found")

    def lean_scalar_to_int(self, p):
        # The C runtime encodes Int as `lean_box((unsigned)(int)n)`, so
        # only the low 32 bits of the unboxed value are meaningful.
        # Sign-extend back to a Python int.
        v = self.lean_unbox(p) & 0xFFFFFFFF
        if v & 0x80000000:
            v -= 1 << 32
        return v

    # Register all methods
    for name, func in list(locals().items()):
        if callable(func) and name.startswith("lean_"):
            class_dict[name] = func


def _add_helper_methods(class_dict: dict, structs: dict):
    """Add convenience helper methods."""
    LeanObjectPtr = structs["_LeanObjectPtr"]

    def mk_string(self, s):
        """Create a Lean string from a Python string."""
        if isinstance(s, str):
            s = s.encode("utf-8")
        return self.lean_mk_string(s)

    def inc_ref(self, obj):
        """Increment reference counter."""
        if self.lean_is_st(obj):
            obj.contents.m_rc += 1

    def dec_ref(self, obj):
        """Decrement reference counter."""
        if self.lean_is_st(obj):
            obj.contents.m_rc -= 1
            if obj.contents.m_rc == 0:
                self.lean_free_object(obj)
        elif obj.contents.m_rc != 0:
            self.lean_dec_ref_cold(obj)

    def io_result_is_ok(self, res) -> bool:
        """Check if an IO result is Ok (tag == 0)."""
        return res.contents.m_tag == 0

    def io_result_show_error(self, res):
        """Display an IO error result."""
        self.lean_io_result_show_error(res)

    class_dict["mk_string"] = mk_string
    class_dict["inc_ref"] = inc_ref
    class_dict["dec_ref"] = dec_ref
    class_dict["io_result_is_ok"] = io_result_is_ok
    class_dict["io_result_show_error"] = io_result_show_error


# ============================================================================
# Module-level singleton
# ============================================================================

_ffi_initialized = False
_cached_model: HeaderModel | None = None
_cached_structs: dict[str, type] | None = None
_LeanFFI: type | None = None


def _ensure_built():
    """Ensure the runtime types are built (lazy init)."""
    global _cached_model, _cached_structs, _LeanFFI
    if _LeanFFI is not None:
        return
    _cached_model = get_header_model()
    _cached_structs = _build_structs(_cached_model)
    _LeanFFI = _build_ffi_class(_cached_model, _cached_structs)


def get_structs() -> dict[str, type]:
    """Get the dynamically created struct types."""
    _ensure_built()
    return _cached_structs


def get_ffi_class() -> type:
    """Get the dynamically created LeanFFI class."""
    _ensure_built()
    return _LeanFFI


def get_constants() -> dict[str, int]:
    """Get the extracted constants."""
    _ensure_built()
    return _cached_model.constants


@functools.lru_cache(maxsize=1)
def get_lean_ffi():
    """Get a singleton LeanFFI instance."""
    cls = get_ffi_class()
    return cls()
