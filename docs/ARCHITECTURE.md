# Architecture

This document is for someone who wants to extend lean-py or debug it. For a usage tour, see the README. The audience here is "I'm staring at a segfault three calls deep into the C bridge and I want to understand why".

## What it does

lean-py is a bidirectional FFI bridge between Lean 4 and Python. Annotate a Lean function with `@[python "name"]`, recompile, and it shows up in Python with the right argument and return types. From the other direction, `Python.import_ "sympy"` inside a Lean program calls sympy's simplifier on a Lean expression and gives you back a `String`. Both directions are designed to feel like calling a normal function, but getting there means navigating refcounted heaps, scalar tagging, the GIL, and a handful of macOS dynamic-loader quirks.

## Why it's tricky

None of these are showstoppers on their own. Lean tags small ints by setting the low bit of a pointer; heap objects carry a 32-bit refcount in their header; a few inductive types get unboxed by the compiler into a `uint8_t` and most don't. On the host side, ctypes silently mangles `POINTER(struct)` arguments in a way that's only visible after the next call, the macOS dynamic loader won't satisfy `@rpath/libLake_shared.dylib` from a library you `dlopen`'d earlier with `RTLD_GLOBAL`, and CPython expects the GIL to be held the instant a Lean function calls back into `PyObject_*`. The symptom for any of these is a segfault three calls downstream of the actual cause, which is what makes the library worth documenting.

## At a glance

The library splits cleanly into two halves. The Lean→Python half is a compile-time registry: every `@[python]`-annotated function and every `derive_python`-derived type writes structural metadata (parameter types, return type, constructors, fields) into a `SimplePersistentEnvExtension`, and one command (`#export_python_registry`) reads that metadata at compile time, JSON-encodes it, and emits two `@[export]`'d functions whose bodies are the JSON literals. The Python→Lean half is a C file (`LeanPy/native/python_bridge.c`) that wraps `PyObject*` as a `lean_external_class`, plus a Lean module (`LeanPy/Python.lean`) of `@[extern]` declarations that point at it. Both halves share the same dlopen handle and refcount conventions, but they don't otherwise know about each other.

## Lean → Python pipeline

The Lean→Python pipeline runs in three stages, each in a different process. At Lean compile time, `@[python "py_foo"]` runs the attribute body in `LeanPy/Attr.lean`: it walks the declaration's type, converts each `forallE` binder and the result into a structural `TypeRepr`, sets the equivalent `@[export "py_foo"]`, and pushes a `FuncInfo` record into the persistent env extension. `derive_python TypeName` does the analogous thing for an inductive: it walks the constructors, captures the field types, and pushes a `TypeInfo`. At the bottom of the user's library, `#export_python_registry "MyLib"` reads both registries, serialises them with `Lean.Json.compress`, and elaborates two `def`s that return those JSON strings, marked `@[export "MyLib_funcs_json"]` and `@[export "MyLib_types_json"]`. At Python load time, `LeanLibrary("path.dylib", "MyLib")` calls those two C symbols, parses the JSON back into `FuncInfo`/`TypeInfo` Python dataclasses, and walks them to build a `ctypes` wrapper per function and a Python class per type.

## Marshalling

Marshalling is where the actual type translation happens. For each `TypeRepr` kind, the `Marshaller` in `lean_py/marshal.py` builds a `(from_lean, to_lean, ctype)` triple lazily and caches it. Most kinds are mechanical (`Bool` ↔ `lean_box(0/1)`, `String` ↔ `lean_mk_string`/`lean_string_cstr`), but a few have non-obvious ABIs that took reading `lean.h` to get right. Lean's small `Int` is encoded as `lean_box((unsigned)(int)(n))`, so only the low 32 bits are meaningful and the decode path masks then sign-extends through `(int)(unsigned)x`. `Nat` goes through `lean_uint64_of_nat` and `lean_unsigned_to_nat` (or the big-int helpers when out of range). `IO α` is `EStateM.Result.ok value world`, a 2-field ctor where the first field is the value and the second is a boxed unit. User inductives whose constructors all have zero fields (e.g. `Color = .red | .green | .blue`) get unboxed by the Lean compiler to a bare `uint8_t` argument in the generated C signature, so the marshaller detects this case via `all (·.fields.isEmpty)` and passes an integer instead of a `lean_object*`.

## The Python-in-Lean bridge

The Python-in-Lean direction is simpler in shape but trickier in detail. `LeanPy/Python.lean` declares an opaque `Py` type and a few dozen `@[extern]` operations (`init`, `eval`, `import_`, `getAttr`, `call`, `add`/`mul`/`pow`, ...). Each one corresponds to a `LEAN_EXPORT lean_obj_res lean_py_*(...)` function in `LeanPy/native/python_bridge.c`. `Py` itself is a `lean_external_class` whose finaliser is `Py_DecRef`, so when the Lean refcount on a wrapped `PyObject*` hits zero its CPython refcount drops by one and the object is collected when CPython itself decides to. CPython is not loaded until the first call to `LeanPy.Python.init`: the bridge `dlopen(NULL)`s the host process to find `Py_Initialize`, falls back to a list of candidate `libpython3.X.dylib` sonames if that fails, and then `dlsym`s every `Py*` entry it needs through an X-macro list. We deliberately prefer the already-loaded libpython over a fresh `dlopen` because loading a second copy of CPython into the same process produces two independent interpreter states and immediate crashes.

## Kernel facade

`LeanPy/Kernel.lean` is the Pantograph-equivalent layer. The model is that the host Python process owns a single Lean `Environment`, stored in an `IO.Ref (Option Environment)`, and every operation runs `CoreM` over that environment. `loadEnv #["Init", "Mathlib"]` calls `Lean.importModules` and stashes the result; `inferType "Nat.succ Nat.zero"` parses the string with `Parser.runParserCategory`, elaborates with `Term.elabTerm`, infers the type with `Meta.inferType`, and returns the pretty-printed result. The surface is intentionally small (around a dozen functions) and is meant as a starting point: real users will want their own kernel module exposing whatever combinations of `Meta`/`Elab`/`Tactic` operations they need. Pantograph itself does this with a couple of hundred `@[export]`'d functions; the same approach works here, you just write them in `LeanPy.Kernel`-style with `@[python "name"]` instead of `@[export]`.

## Things that bit us

Most of the design pressure came from things that didn't work the first time. Five worth recording for posterity:

1. **`cfn.argtypes.append(...)` is a no-op as far as ctypes' internal trampoline is concerned.** The `argtypes` property setter rebuilds an internal table on assignment, but in-place mutation doesn't trigger it. A function set up as `cfn.argtypes = [c_void_p]` followed by `cfn.argtypes.append(c_void_p)` is invoked with one parameter and the second is left as garbage on the stack. Build the list once and assign it.

2. **`ctypes.CDLL` releases the GIL around every call.** That's correct for libraries that don't touch the Python C API but lethal for ours: any Lean function that goes on to call `PyObject_*` does so without the GIL and crashes immediately. `LeanLibrary` uses `ctypes.PyDLL` instead, which keeps the GIL held across the call.

3. **macOS's dynamic loader doesn't satisfy `@rpath/libLake_shared.dylib` from libraries already loaded with `RTLD_GLOBAL`.** It walks the *loading* image's `LC_RPATH` list, full stop. `LeanLibrary._ensure_rpath` runs `install_name_tool -change` on each `@rpath/...` reference, rewriting it to an absolute path under `lean --print-prefix`/`lib/lean` before the first `dlopen`. The user dylib must be built with `-Wl,-headerpad_max_install_names` for the rewrite to fit in the load-command region.

4. **Static linking + persistent env extensions = single-library-per-process.** `initialize_LeanPy_Registry` registers the env extension `LeanPy.funcRegistry`, and gets statically linked into every user library that depends on LeanPy. Loading two such libraries into one Python process throws `invalid environment extension, 'LeanPy.funcRegistry' has already been used`, because each copy of the static archive runs its own initializer and the registry is process-global. The current workaround is one library per process (the test suite consolidates kernel + example bindings into a single dylib for this reason). The proper fix is to switch LeanPy to a shared-library dependency, which I haven't done yet because Lake's shared facet has its own quirks.

5. **`leanpy_*` helpers must be looked up in the user dylib, not the global namespace.** `ctypes.CDLL(None)` (the macOS `RTLD_DEFAULT` pseudo-handle) finds the symbols, but calls through it get inconsistent state for some operations. `LeanFFI` instead exposes a `register_handle` method, called from `LeanLibrary.__init__`, that adds the user dylib's CDLL to a search list. Helper lookups (`leanpy_dec_ref`, `leanpy_alloc_ctor`, `leanpy_int64_to_int`, ...) iterate that list explicitly.

## Memory and CI

Memory correctness is verified two ways. `tests/test_memory.py` runs each marshalled type through 2,000-10,000 iterations and asserts that Python's `gc` reports no growth and that CPython's refcount on a sentinel tuple is unchanged after a stress loop through `pythonEvalInt`. `tests/leaks_check.sh` runs the same suite under macOS `leaks(1)` (with `MallocStackLogging=1`) or Linux `valgrind` (with a `python.supp` to filter CPython's own steady-state allocations). The CI workflow at `.github/workflows/ci.yml` runs the full suite on Linux and macOS against three Lean toolchains (the pinned default, the previous stable, and nightly), and runs the `leaks` and `valgrind` jobs on top of that. Both heap-check jobs are marked `continue-on-error: true` because CPython's interpreter holds enough long-lived allocations that distinguishing "leak in our code" from "noise from libpython" is a judgement call rather than a binary, and a noisy framework allocation shouldn't red-X every PR.

## File map

```
LeanPy.lean                     entry point; imports the rest
LeanPy/
  Registry.lean                 funcRegistry, typeRegistry (persistent ext)
  TypeRepr.lean                 structural type model + JSON encoding
  Attr.lean                     @[python] attribute, derive_python command,
                                typeToRepr, collectFunSig, buildTypeInfo
  Export.lean                   #export_python_registry command
  Python.lean                   opaque Py, @[extern] declarations
  Kernel.lean                   Pantograph-equivalent kernel facade
  native/python_bridge.c        C side: PyObject* external class,
                                lean_py_* externs, leanpy_* helpers

lean_py/
  __init__.py                   public Python API
  _parse.py                     pycparser frontend over lean.h
  _runtime.py                   dynamic ctypes FFI built from lean.h,
                                inline reimplementations of static-inline
                                helpers, register_handle / _find_leanpy_helper
  registry.py                   Python mirror of TypeRepr / FuncInfo / TypeInfo
  marshal.py                    Marshaller: TypeRepr → (from_lean, to_lean, ctype)
  library.py                    LeanLibrary loader, _build_callable,
                                _ensure_rpath, _InductiveType / _StructureType
  utils.py                      lean_lib_dir, find_lean_dynlib, etc.

examples/lean/                  PyleanExample: end-to-end demo Lean library
tests/                          37 tests + leaks_check.sh + python.supp
```
