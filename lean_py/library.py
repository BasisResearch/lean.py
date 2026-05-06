"""
Wrapper around a compiled Lean library that exposes `@[python]`-annotated
declarations.

Usage:
    >>> lib = LeanLibrary("path/to/MyLib.dylib", "MyLib")
    >>> lib.bar(7)             # exported as `py_bar`
    >>> lib.Color.red          # generated wrapper for inductive Color
    >>> lib.Point(3, 4)        # generated wrapper for structure Point

The library:
  1. Loads the dylib via ctypes (with RTLD_GLOBAL so subsequent libs see
     its symbols).
  2. Calls `initialize_<libname>` once to run static initialisers.
  3. Calls the JSON registry exports `<libname>_funcs_json` and
     `<libname>_types_json` to discover what's exposed.
  4. Builds a `Marshaller` and a Python wrapper for each registered
     function and type.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from ctypes import POINTER, c_uint8, c_void_p
from pathlib import Path
from typing import Any, Callable

from lean_py.base_types import LeanObject
from lean_py.lean_ffi import get_lean_ffi
from lean_py.marshal import LeanInductiveValue, Marshaller, TypeWrapper
from lean_py.registry import FuncInfo, LibraryRegistry, TypeInfo
from lean_py.utils import lean_lib_dir, run_command, shared_lib_extension


def _list_init_symbols(dylib: Path) -> list[str]:
    """Return all globally-exported `initialize_*` symbols in `dylib`.

    Used as a fallback when the canonical `initialize_<lib>` symbol
    isn't where we expect — Lake's symbol naming has shifted across
    toolchains. We invoke `nm`/`llvm-nm` rather than ctypes because
    ctypes has no portable symbol-listing API.
    """
    try:
        out = subprocess.run(
            ["nm", "-gj", str(dylib)],
            capture_output=True, text=True, check=True,
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    candidates = []
    for line in out.splitlines():
        sym = line.strip()
        # macOS prefixes exported symbols with `_`; strip that.
        if sym.startswith("_"):
            sym = sym[1:]
        if sym.startswith("initialize_") and "Lean_" not in sym \
                and "LeanPy_" not in sym:
            candidates.append(sym)
    return candidates


def _ensure_rpath(dylib: Path) -> None:
    """On macOS, rewrite any `@rpath/libFoo.dylib` references to absolute
    paths under Lean's `lib/lean`. This lets `dlopen` succeed without a
    pre-set `DYLD_LIBRARY_PATH` even when the library was linked without
    a runtime path.

    On other platforms this is a no-op (Linux uses RUNPATH baked in by
    the linker plus our preloaded `RTLD_GLOBAL` libs).
    """
    if sys.platform != "darwin":
        return
    libdir = lean_lib_dir()
    try:
        out = subprocess.run(
            ["otool", "-L", str(dylib)],
            capture_output=True, text=True, check=True,
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return

    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("@rpath/"):
            continue
        # Form: "@rpath/libFoo.dylib (compatibility version ...)"
        ref = line.split(" ", 1)[0]
        leaf = ref[len("@rpath/"):]
        candidate = libdir / leaf
        if not candidate.exists():
            continue
        try:
            subprocess.run(
                ["install_name_tool", "-change", ref, str(candidate), str(dylib)],
                check=True, capture_output=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass


# ============================================================================
# Generated type wrappers
# ============================================================================


class _InductiveType:
    """Generated namespace for a Lean inductive's constructors.

    For each constructor, exposes a callable that produces a
    `LeanInductiveValue`. For enum-like (no-arg) ctors, exposes them
    as class attributes that are pre-built `LeanInductiveValue`s.
    """

    def __init__(self, ti: TypeInfo, marshaller: Marshaller):
        self._ti = ti
        self._marshaller = marshaller
        for ctor in ti.ctors:
            if not ctor.fields:
                v = LeanInductiveValue(ti.name, ctor.name, ctor.tag, ())
                setattr(self, ctor.name, v)
            else:
                def _make(*args, _c=ctor):
                    if len(args) != len(_c.fields):
                        raise TypeError(
                            f"{ti.name}.{_c.name} expects {len(_c.fields)} args, got {len(args)}"
                        )
                    return LeanInductiveValue(ti.name, _c.name, _c.tag, tuple(args))
                setattr(self, ctor.name, _make)

    def __repr__(self) -> str:
        ctor_names = ", ".join(c.name for c in self._ti.ctors)
        return f"<LeanType {self._ti.name} ({ctor_names})>"


class _StructureType(_InductiveType):
    """Specialised wrapper for single-ctor types (structures / records).

    Calling the type as `Point(1, 2)` builds an inductive value with the
    sole constructor.
    """

    def __init__(self, ti: TypeInfo, marshaller: Marshaller):
        super().__init__(ti, marshaller)
        self._ctor = ti.ctors[0]

    def __call__(self, *args, **kwargs) -> LeanInductiveValue:
        if kwargs:
            raise TypeError(
                f"{self._ti.name}: keyword fields not supported yet "
                f"(use positional args)"
            )
        if len(args) != len(self._ctor.fields):
            raise TypeError(
                f"{self._ti.name} expects {len(self._ctor.fields)} args, got {len(args)}"
            )
        return LeanInductiveValue(
            self._ti.name, self._ctor.name, self._ctor.tag, tuple(args)
        )


# ============================================================================
# Generated function wrappers
# ============================================================================


def _build_callable(
    lib: ctypes.CDLL, finfo: FuncInfo, marshaller: Marshaller
) -> Callable:
    """Build a Python wrapper around an `@[export]`'d Lean function.

    Conventions for the C ABI of Lean-exported functions:
      * Most parameter types are `lean_object*`. Exceptions: scalar value
        types (Bool, UInt8/16/32/64, USize, Float) are passed as their
        natural C types, but inductive parameters are pointer-shaped.
      * IO-returning functions take a trailing `lean_io.RealWorld` arg
        (just `lean_box(0)`); the result is a tagged Result object.
    """
    try:
        cfn = getattr(lib, finfo.exportName)
    except AttributeError as e:
        raise RuntimeError(
            f"Symbol {finfo.exportName} not found in library "
            f"(declared in registry but missing from dylib)"
        ) from e

    ret = finfo.returnType
    is_io = ret.kind == "io"

    pwraps: list[TypeWrapper] = [marshaller.wrapper_for(p) for p in finfo.params]
    rwrap: TypeWrapper = marshaller.wrapper_for(ret)

    # We use `c_void_p` for any pointer-shaped argument or return value
    # to sidestep a ctypes oddity on macOS where storing a returned
    # `POINTER(struct)` and then passing it to another C function
    # corrupts the pointer in some configurations.
    def _ctype_for_call(ct):
        # Pointer-shaped: collapse to c_void_p.
        if isinstance(ct, type) and issubclass(ct, ctypes._Pointer):
            return c_void_p
        return ct

    # Build the argtypes list ONCE then assign — ctypes does not pick up
    # in-place mutation of `cfn.argtypes`, so `.append(...)` after
    # assignment would silently leave the FFI thinking the function only
    # has one parameter.
    argtypes = [_ctype_for_call(w.ctype) for w in pwraps]
    if is_io:
        argtypes.append(c_void_p)
    cfn.argtypes = argtypes
    cfn.restype = _ctype_for_call(rwrap.ctype)

    # If the return is a pointer, we need to cast it back to LeanObjectPtr
    # before handing it to the unmarshaller.
    from lean_py._runtime import get_structs
    LObjPtr = get_structs()["_LeanObjectPtr"]
    return_is_pointer = (
        isinstance(rwrap.ctype, type)
        and issubclass(rwrap.ctype, ctypes._Pointer)
    )

    from lean_py.lean_ffi import get_lean_ffi
    _ffi = get_lean_ffi()

    def _wrapper(*args):
        if len(args) != len(pwraps):
            raise TypeError(
                f"{finfo.exportName}: expected {len(pwraps)} args, got {len(args)}"
            )
        cargs = []
        for w, a in zip(pwraps, args):
            v = w.to_lean(a)
            if isinstance(w.ctype, type) and issubclass(w.ctype, ctypes._Pointer):
                # Convert pointer args to raw pointer values to match cfn.argtypes.
                v = ctypes.cast(v, c_void_p).value if v is not None else 0
            elif w.ctype in (c_uint8, ctypes.c_uint16) and not isinstance(v, int):
                # Enum/Bool: `to_lean` produces a boxed scalar pointer so it
                # round-trips through nested struct fields, but a top-level
                # uint8/uint16 parameter expects the raw tag. Unbox here.
                v = _ffi.lean_unbox(v)
            cargs.append(v)
        if is_io:
            cargs.append(c_void_p(1))
        result_raw = cfn(*cargs)
        if return_is_pointer:
            result_ptr = ctypes.cast(c_void_p(result_raw), LObjPtr)
            return rwrap.from_lean(result_ptr)
        return rwrap.from_lean(result_raw)

    _wrapper.__name__ = finfo.exportName
    _wrapper.__qualname__ = f"LeanLibrary.{finfo.exportName}"
    _wrapper.__doc__ = (
        f"Lean function `{finfo.declName}` exposed as `{finfo.exportName}`.\n"
        f"Signature: ({', '.join(p.short() for p in finfo.params)}) -> {ret.short()}"
    )
    return _wrapper


# ============================================================================
# LeanLibrary
# ============================================================================


class LeanLibrary:
    """A loaded Lean library with `@[python]` bindings."""

    @classmethod
    def from_lake(
        cls,
        lake_dir: str | os.PathLike,
        library_name: str | None = None,
        *,
        build: bool = False,
    ) -> "LeanLibrary":
        """Load a Lean library from a Lake project directory.

        Looks for `<lake_dir>/.lake/build/lib/lib<library_name>.<ext>`
        (or, when `library_name` is omitted, the single shared library
        produced by the project). Pass `build=True` to run `lake build`
        in `lake_dir` first.
        """
        lake_path = Path(lake_dir).resolve()
        if not lake_path.is_dir():
            raise FileNotFoundError(f"not a Lake project directory: {lake_path}")
        if build:
            run_command(["lake", "build"], cwd=lake_path)

        ext = shared_lib_extension()
        build_root = lake_path / ".lake" / "build"
        lib_dir = build_root / "lib"

        def _find(name: str) -> Path | None:
            """Locate `lib<name>.<ext>` produced by `lake build`.

            Naming has shifted across Lake versions:
              * old: `lib<name>.<ext>`
              * newer (>= late 2025): `lib<package>_<name>.<ext>`,
                so a same-name package + lib produces e.g.
                `libTestLib_TestLib.dylib`.

            Try the canonical path first, then any matching file under
            `.lake/build/`, accepting both spellings."""
            if not build_root.is_dir():
                return None
            patterns = [
                f"lib{name}{ext}",         # old layout
                f"lib*_{name}{ext}",       # new: lib<pkg>_<name>.<ext>
                f"lib{name}_*{ext}",       # mirror
            ]
            # Quick path: standard lib_dir, exact name.
            primary = lib_dir / f"lib{name}{ext}"
            if primary.exists():
                return primary
            for pat in patterns:
                for p in build_root.rglob(pat):
                    if p.name.endswith((".hash", ".trace", ".rsp")):
                        continue
                    if p.suffix == ext:
                        return p
            return None

        def _diagnostic() -> str:
            if not build_root.is_dir():
                return f"{build_root} does not exist (lake build did not run or failed)"
            entries = sorted(
                str(p.relative_to(build_root))
                for p in build_root.rglob("*")
                if p.is_file()
            )
            return f"contents of {build_root}: {entries[:50]}"

        if library_name is not None:
            found = _find(library_name)
            if found is None and build:
                # Some Lake versions don't honour `defaultFacets = ["shared"]`
                # in lakefile.toml; ask for the shared facet explicitly.
                try:
                    run_command(["lake", "build", f"{library_name}:shared"],
                                cwd=lake_path)
                except Exception:
                    pass
                found = _find(library_name)
            if found is None:
                raise FileNotFoundError(
                    f"lib{library_name}{ext} not found under {build_root}; "
                    f"check the library name or run `lake build`. {_diagnostic()}"
                )
            return cls(found, library_name)

        # Auto-detect: pick the unique shared lib (excluding .hash/.trace/.rsp).
        shared = []
        if build_root.is_dir():
            shared = [
                p for p in build_root.rglob(f"lib*{ext}")
                if p.suffix == ext
                and not p.name.endswith((".hash", ".trace", ".rsp"))
            ]
        if not shared:
            raise FileNotFoundError(
                f"no shared library found under {build_root}; run `lake build`. "
                f"{_diagnostic()}"
            )
        if len(shared) > 1:
            names = ", ".join(p.stem.removeprefix("lib") for p in shared)
            raise RuntimeError(
                f"multiple shared libraries under {build_root} ({names}); pass "
                f"library_name to disambiguate"
            )
        # The library_name we report should be the second half of
        # `lib<pkg>_<name>` if that pattern is in play; otherwise the
        # whole post-`lib` stem.
        stem = shared[0].stem.removeprefix("lib")
        name = stem.split("_", 1)[1] if "_" in stem else stem
        return cls(shared[0], name)

    def __init__(self, dylib_path: str | os.PathLike, library_name: str):
        self.path = Path(dylib_path)
        self.name = library_name
        self.ffi = get_lean_ffi()
        # Ensure the dylib can resolve its @rpath references to Lean's runtime.
        _ensure_rpath(self.path)
        # Use `PyDLL` so that ctypes does NOT release the GIL when calling
        # into Lean. This matters for `LeanPy.Python.*` functions which
        # call back into the Python C API: those calls require the GIL
        # to be held by the calling thread.
        self.lib = ctypes.PyDLL(str(self.path), mode=ctypes.RTLD_GLOBAL)

        # Make this dylib's `leanpy_*` C-bridge symbols visible to the
        # FFI helper-lookup chain (used by ref-count and allocation ops).
        self.ffi.register_handle(self.lib)

        self._ensure_task_manager()
        self._initialize_lean_module()

        self.registry = self._load_registry()

        self.marshaller = Marshaller(self.registry)
        self._funcs: dict[str, Callable] = {}
        self._types: dict[str, _InductiveType] = {}

        for ti in self.registry.types:
            wrapper = _StructureType(ti, self.marshaller) \
                if len(ti.ctors) == 1 \
                else _InductiveType(ti, self.marshaller)
            short = ti.name.split(".")[-1]
            self._types[short] = wrapper
            setattr(self, short, wrapper)

        for fi in self.registry.funcs:
            wrap = _build_callable(self.lib, fi, self.marshaller)
            short = fi.declName.split(".")[-1]
            self._funcs[short] = wrap
            self._funcs[fi.exportName] = wrap
            if not hasattr(self, short):
                setattr(self, short, wrap)
            if not hasattr(self, fi.exportName):
                setattr(self, fi.exportName, wrap)

    # -- internal ---------------------------------------------------------

    _task_manager_initialized: bool = False

    def _ensure_task_manager(self) -> None:
        """Initialise Lean's task manager once per process.

        `Lean.importModules` (and any kernel operation that allocates a
        `Task`) asserts on `g_task_manager` being non-null. The Lean
        executable runtime does this for you in `lean_main`; when we host
        Lean inside Python we need to call it ourselves. Idempotent.
        """
        if LeanLibrary._task_manager_initialized:
            return
        # The symbol lives in libleanshared, not the user dylib.
        # Try the user dylib first (works on macOS with RTLD_GLOBAL),
        # then fall back to the FFI's lean shared lib handle.
        init = None
        for handle in (self.lib, self.ffi.lib):
            try:
                init = handle.lean_init_task_manager
                break
            except AttributeError:
                continue
        if init is None:
            return
        init.argtypes = []
        init.restype = None
        init()
        LeanLibrary._task_manager_initialized = True

    def _resolve_init_symbol(self) -> str:
        """Resolve the module-initializer symbol, allowing for the
        Lake-naming variations Lean has gone through.

        The canonical name is `initialize_<lib>`, but newer toolchains
        sometimes prefix the package or use double underscores. As a
        last resort we ask `nm` for any `initialize_*` symbol exported
        by the dylib and pick the best fit."""
        candidates = [
            f"initialize_{self.name}",
            f"initialize_{self.name}_{self.name}",  # lib<pkg>_<lib>
        ]
        for c in candidates:
            try:
                getattr(self.lib, c)
                return c
            except AttributeError:
                continue

        symbols = _list_init_symbols(self.path)
        # Prefer one that ends in `_<self.name>`.
        for s in symbols:
            if s.endswith(f"_{self.name}"):
                return s
        if len(symbols) == 1:
            return symbols[0]
        if symbols:
            raise RuntimeError(
                f"library has multiple `initialize_*` symbols and none "
                f"matches `_{self.name}`: {symbols}"
            )
        raise RuntimeError(
            f"library does not export an `initialize_*` symbol for "
            f"`{self.name}`; was it compiled with `@[python]` attributes "
            f"and `precompileModules`/`shared`?"
        )

    def _initialize_lean_module(self) -> None:
        init_name = self._resolve_init_symbol()
        init_fn = getattr(self.lib, init_name)
        init_fn.argtypes = [c_uint8, POINTER(LeanObject)]
        init_fn.restype = POINTER(LeanObject)

        result = init_fn(1, ctypes.cast(c_void_p(1), POINTER(LeanObject)))
        if result.contents.m_tag != 0:
            self.ffi.io_result_show_error(result)
            self.ffi.dec_ref(result)
            raise RuntimeError(f"{init_name} failed")
        self.ffi.dec_ref(result)
        # The user library's `initialize_*` block has now run all its
        # `initialize` declarations. Flip the runtime's global init
        # flag so subsequent calls (e.g. frontend operations that
        # invoke `mkEmptyEnvironment` via `parseHeader`) succeed.
        # See `lean_py/_runtime.py` for more on why.
        if getattr(self.ffi, "lean_io_mark_end_initialization", None) is not None:
            self.ffi.lean_io_mark_end_initialization()

    def _load_registry(self) -> LibraryRegistry:
        funcs_sym = f"{self.name}_funcs_json"
        types_sym = f"{self.name}_types_json"
        funcs_json = self._call_string_export(funcs_sym)
        types_json = self._call_string_export(types_sym)
        return LibraryRegistry.from_json_strings(funcs_json, types_json)

    def _call_string_export(self, name: str) -> str:
        try:
            fn = getattr(self.lib, name)
        except AttributeError:
            return ""
        fn.argtypes = [POINTER(LeanObject)]
        fn.restype = POINTER(LeanObject)
        unit = ctypes.cast(c_void_p(1), POINTER(LeanObject))
        result_ptr = fn(unit)
        try:
            size = self.ffi.lean_string_size(result_ptr)
            if size <= 1:
                return ""
            cstr = self.ffi.lean_string_cstr(result_ptr)
            raw = cstr.value if isinstance(cstr, ctypes.c_char_p) else cstr
            return (raw or b"").decode("utf-8")
        finally:
            self.ffi.dec_ref(result_ptr)

    # -- public -----------------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        if key in self._funcs:
            return self._funcs[key]
        if key in self._types:
            return self._types[key]
        raise KeyError(key)

    def __repr__(self) -> str:
        return (
            f"<LeanLibrary {self.name!r} "
            f"funcs={len(self._funcs)} types={len(self._types)}>"
        )


# Re-export under both names for compatibility.
Library = LeanLibrary
