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

### Lean closures as Python callables (Phase 3c)

`LeanPy.Python.Py.fromLeanCallable` and `fromLeanCallableKw` wrap a Lean closure of type `Array Py → IO Py` (or `… → Array (String × Py) → IO Py`) as a Python callable. The implementation builds a CPython heap type via `PyType_FromSpec` rather than a static `PyTypeObject` so we don't need Python headers at Lean compile time — the slot constants and `Py_TPFLAGS_*` values are inlined. The instance struct is a standard `PyObject` header followed by an owned `lean_object *closure` pointer and a `has_kw` flag; allocation goes through `PyType_GenericAlloc` (which handles the type's refcount automatically) and deallocation calls `PyObject_Free` followed by an explicit `Py_DecRef` on the type pointer. Each `tp_call` invocation `lean_inc`s the closure (because `lean_apply_*` consumes one ref), wraps each Python arg as a `Py` external object (with a CPython `IncRef` to give the wrapper its own reference), packs them into a Lean `Array Py`, and calls `lean_apply_2`/`lean_apply_3`. On `IO.Error` the trampoline raises a Python `RuntimeError` carrying the Lean message — we use `RuntimeError` rather than `LeanError` to keep C-side dependencies minimal (no need to dlsym Python-side classes).

### Initialization-flag handoff

Lean's runtime keeps a `g_initializing` flag (the C side of `IO.initializing`) that starts true and is normally set to false by `lean_io_mark_end_initialization` inside `main`. Since we drive Lean from Python and never go through `main`, we have to flip this flag ourselves — but only *after* the user library's `initialize_<Name>(1, world)` has run, because the `initialize` declarations themselves require the flag to be true. The handoff lives in `lean_py/library.py::_initialize_lean_module`: load the library, run its init, then call `lean_io_mark_end_initialization`. Without this, `Frontend.createContextStateFromFile`'s call to `parseHeader` fails with `"environment objects cannot be created during initialization"` because `parseHeader` builds a dummy env via `mkEmptyEnvironment`, which guards on the flag.

## Kernel facade

`LeanPy/Kernel.lean` and `LeanPy/Kernel/*.lean` are the Pantograph-equivalent layer. The implementation files (`Goal.lean`, `Tactic.lean`, `Tactic/{Assign,Fragment,Prograde}.lean`, `Frontend.lean`, `Frontend/{Basic,Distil,InfoTree,MetaTranslate,Refactor}.lean`, `Environment.lean`, `Elab.lean`, `Serial.lean`, `Delab.lean`, `Protocol.lean`) are lifted with attribution from [Pantograph](https://github.com/lenianiva/Pantograph) (GPL-3.0+) — pantograph's namespaces are renamed `Pantograph` → `LeanPy.Kernel` and exports `pantograph_*` → `leanpy_kernel_*`. The top-level `LeanPy/Kernel.lean` adds `@[python]`-tagged wrappers around the most-used operations: env lifecycle (`init_search`, `load_env`, `is_loaded`, `clear_env`), env introspection (`catalog`, `search`, `decl_type`, `decl_value`, `decl_axioms`, `module_of_name_str`, `inspect`), elaboration (`infer_type`, `pretty_print`, `whnf`, `expr_echo`, `parse_type`, `decide`), goal state (`goal_create`, `goal_is_solved`, `goal_n_goals`, `goal_main_goal_name`, `goal_root_expr`, `goal_pretty`, `goal_try_tactic`, `goal_try_assign`, `goal_conv_enter`, `goal_calc_enter`, `goal_fragment_exit`, `goal_resume`, `goal_continue`), prograde tactics (`goal_try_have`, `goal_try_let`, `goal_try_define`, `goal_try_draft`), pickling (`env_pickle`/`env_unpickle`, `goal_pickle`/`goal_unpickle`), frontend operations (`frontend_process`, `frontend_find_source_path`, `frontend_collect_sorrys`), and delab utilities (`delab_unfold_aux_lemmas`, `delab_unfold_matchers`, `delab_instantiate_all`, `delab_expr_proj_to_app`, `goal_state_diag`).

A higher-level Python wrapper lives in `lean_py/kernel.py` (`Kernel`, `GoalState`, `TacticResult`); it wraps the raw `leanpy_kernel_*` calls in idiomatic Python.

### Where prograde tactics live

Pantograph keeps `tryHave`/`tryLet`/`tryDefine`/`tryDraft` in `Pantograph/Library.lean`, which is otherwise REPL-specific. We don't port the rest of `Library.lean` (it's the JSON REPL) so the prograde tactics live directly in `LeanPy/Kernel/Goal.lean` next to the other `GoalState` methods. They reuse `parseTermM` from `Elab.lean` and the existing `Tactic.evalHave`/`evalLet`/`evalDefine`/`evalDraft` implementations under `LeanPy/Kernel/Tactic/`.

### GoalState lifecycle (caveat)

`GoalState` is exposed to Python as an opaque `LeanObj` handle backed by Lean's standard refcounting. The `_opaque_wrapper` marshaller bumps the refcount on each pass-to-Lean call so a single handle can be threaded through many ops.

**Known issue**: cheap field-projecting operations (`goal_is_solved`, `goal_n_goals`, `goal_main_goal_name`) are reusable on the same handle without limit. But `goal_pretty`, `goal_root_expr`, `goal_try_tactic`, and any other op that runs `Meta.MetaM.run' (s := state.metaState)` corrupts the underlying Meta state on its second invocation against the same handle. After such a second call, even unrelated kernel ops can segfault (e.g. `leanpy_kernel_search` reading `env.constants`). Standalone usage from a single Python process is unaffected if you don't repeat the heavy ops on a single state.

The test suite reorders kernel-state tests to run last and skips two tests that exercise the exact failure: `test_goal_state_pretty_is_reusable` and `test_goal_search` (after a kernel-test sequence). All 24 other kernel-full tests now pass.

Diagnostic notes: each Lean-facing wrapper (e.g. `goalPretty`) reads `state.metaState` (a structure projection that bumps the projected field's refcount) then passes it to `Meta.MetaM.run'`, which consumes one ref. The arithmetic balances on paper, but in practice the second call sees a dec-after-free on one of the persistent maps inside `Meta.State`. The mismatch is most likely between the `MonadBacktrack.saveState` snapshot taken by `GoalState.create` (which captures references into the elaboration context that produced the goal) and `MetaM.run'`'s state-discarding semantics. Pinning the exact site requires building a debug Lean and instrumenting `lean_dec_ref`; this is left as future work.

## Bidirectional introspection

`LeanPy/Reflect.lean` registers Lean's kernel-level inductives (`Lean.Name`, `Lean.Level`, `Lean.BinderInfo`, `Lean.Literal`, `Lean.MVarId`, `Lean.FVarId`, `Lean.LevelMVarId`, `Lean.Expr`, `Lean.Syntax`, `Lean.SourceInfo`) with `derive_python`, exposing them to the Python side as fully-typed ADT mirrors. So `lib.Expr.app(f, x)` builds a `Lean.Expr` that round-trips correctly through any `@[python]` function whose Lean signature mentions `Lean.Expr`. To support recursive types, `derive_python` first registers a name-only placeholder `TypeInfo`, then runs `buildTypeInfo` against the now-extended environment, and registers the real entry on top; the Python registry dedupes by keeping the entry with more constructors.

In the other direction, `LeanPy.Python.Py` is recognised by `typeToRepr` as the `.pyobject` `TypeRepr` (via a special case in `Attr.lean`). The Python marshaller's `_py_object_wrapper` calls `leanpy_unwrap_pyobject` (a C export in `python_bridge.c`) to extract the underlying `PyObject*` and bumps Python's refcount; the result is a *live* Python value, not an opaque handle. Round-tripping handles back to Lean still works (via the `LeanObj` path).

### What's not (yet) symmetric

`derive_python` types and `Py` use different transports: a `derive_python` type round-trips at the `@[python]` function boundary (decoded as a `LeanInductiveValue` on the Python side), while `Py` is a live wrapper. There's currently no way to wrap a `Lean.Expr` *as* a `Py` so it can be passed to `Py.call` from inside Lean — this is what the Phase 3d sympy demo would need to be a true Lean→Python Expr pipeline, and is left as future work. Today the Phase 3d path either pattern-matches on the Expr in Lean and ships strings (the example does this) or accepts a `Lean.Expr` argument from Python and relies on the marshaller's automatic `LeanInductiveValue` conversion.

## Exception model

See [`docs/EXCEPTIONS.md`](EXCEPTIONS.md). The short version: Lean errors surface as `lean_py.LeanError(kind, message)`; CPython errors raised inside a Lean→Python callback surface as `lean_py.LeanPyCallbackError(python_type, python_message)` (which is a `LeanError` subclass). Lean code can catch the latter via `LeanPy.Python.tryCatchPy` and dispatch on the parsed `PyException`.

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

examples/                       self-contained demos (basic, kernel, numpy, sympy, knuckledragger)
tests/                          37 tests + leaks_check.sh + python.supp
tests/lean/                     TestLib: Lake project bundling every fixture used by the test suite
```
