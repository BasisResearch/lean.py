# Plan: pin the GoalState refcount bug

## Goal

Get a definitive answer to "which `lean_dec_ref` call frees an object
that the next operation reads". The current diagnosis ("refcount
discipline mismatch around `Meta.MetaM.run' (s := state.metaState)`")
is plausible but unconfirmed — three of the four candidate sites are
equally consistent with what we observe. This plan is the smallest set
of mechanical steps that produces a single, citeable stack trace.

## What we know

- 7 tests skip because `goal_pretty` (and any other op that runs
  `Meta.MetaM.run'`) corrupts the `GoalState` on its second invocation
  against the same handle. After such a call, even unrelated kernel
  ops (`leanpy_kernel_search` reading `env.constants`) eventually
  segfault.
- Cheap field-projecting ops (`goal_is_solved`, `goal_n_goals`,
  `goal_main_goal_name`) are reusable on a single handle indefinitely.
- The `freshCoreContext` we build per call uses a new `Core.State`,
  so the corruption isn't via shared global state in CoreM.
- The Python wrapper does `lean_inc(p)` before each call and the Lean
  function consumes one ref at exit; the arithmetic balances.
- A standalone process reproducer exists (see "Reproducer" below).
- Pantograph's own test suite doesn't hit this, presumably because
  it drives the kernel from Lean (in-process MetaM) rather than via
  C-FFI from a separate Python interpreter.

## Hypotheses, ranked by prior

1. **`PersistentHashMap` aliasing inside `Meta.State`.** `state.savedState.term.meta.meta`
   contains `mctx`, `zetaDeltaFVarIds`, `postponed` — all persistent
   maps sharing structure. `Meta.SavedState.restore` does
   `modify fun s => { s with mctx := b.meta.mctx, ... }`, transferring
   ownership to the live MetaM state. If MetaM modifies one of those
   maps and then exits via `run'`, the modified version's interior
   nodes are dropped, and the `GoalState`'s view (which still names
   the original root) walks a now-freed node on the next access.
2. **Python GC running mid-Lean.** Python's cyclic GC can fire on any
   allocation, including from inside a Lean callback. If a `LeanObj`
   becomes unreachable while MetaM is partway through a transformation
   on the wrapped object, `LeanObj.__del__` → `lean_dec_ref` lands on
   something the Lean runtime is still reading. Symptoms would match.
3. **`MonadBacktrack.saveState` capturing closures.** The synthetic
   metavar table inside `Term.State` carries `MessageData` values that
   are sometimes thunked closures. Pickling clears those (see
   `goalStatePickle`); we don't, so closures with stale env captures
   may be evaluated on restore.
4. **Heartbeat-related teardown.** Each `freshCoreContext` resets
   `initHeartbeats`, which interacts with Lean's `IO.checkCanceled`
   path. Less likely but worth ruling out.

## Reproducer

`/tmp/repro_goalstate.py` (committed under `tests/lean/repro_goalstate.py`):

```python
"""Standalone segfault reproducer for the GoalState lifecycle bug.
Exits 0 if the bug is fixed, 139 (SIGSEGV) otherwise."""
from pathlib import Path
from lean_py import LeanLibrary
from lean_py.utils import add_lean_lib_to_dyld_path

add_lean_lib_to_dyld_path()
lib = LeanLibrary.from_lake(Path(__file__).parent, "TestLib", build=False)
lib.leanpy_kernel_init_search("")
lib.leanpy_kernel_load_env(["Init"])
state = lib.leanpy_kernel_goal_create("∀ n : Nat, n + 0 = n")
lib.leanpy_kernel_goal_pretty(state)   # 1st: works
lib.leanpy_kernel_goal_pretty(state)   # 2nd: SIGSEGV
print("ok")
```

Around 50 lines, no test framework, no Python GC pressure beyond
what `goal_pretty` triggers. Run with `python repro_goalstate.py`
or under any debugger.

## Step 1 — Build a debug Lean runtime with ASAN

Lean's normal release build strips frame pointers and inlines
heavily. To track refcount discipline we need:

```bash
# In a checkout of leanprover/lean4 at the toolchain we use (4.29.1)
mkdir build-asan && cd build-asan
cmake -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug \
  -DLEAN_EXTRA_CXX_FLAGS="-fsanitize=address -fno-omit-frame-pointer -g3" \
  -DLEAN_EXTRA_LINKER_FLAGS="-fsanitize=address" \
  ../src
ninja
```

Output: `build-asan/release/stage1/lib/lean/libleanshared.so` (Linux)
or `.dylib` (macOS). This replaces the runtime that `lean_py`'s ctypes
loader picks up.

Wire it in via `LEANPY_LIBPYTHON`-style override; we don't currently
have one for `libleanshared`. Add:

```python
# lean_py/utils.py
def find_lean_dynlib() -> Path:
    if env := os.environ.get("LEANPY_LIBLEAN"):
        return Path(env)
    ...
```

so the reproducer can run with `LEANPY_LIBLEAN=$LEAN4/build-asan/.../libleanshared.so`.

Effort: ~2h to set up cmake, ~30min builds.

## Step 2 — Instrument `lean_dec_ref`

ASAN catches use-after-free on read but not the *origin* of the dec.
Add lightweight tracing inside `lean_dec_ref`:

```cpp
// src/runtime/object.cpp
extern "C" LEAN_EXPORT void lean_dec_ref_cold(lean_object * o) {
    if (getenv("LEANPY_TRACE_DEC")) {
        // Print address + tag + caller
        void *caller = __builtin_return_address(0);
        fprintf(stderr, "DEC %p tag=%d caller=%p\n",
                (void*)o, lean_ptr_tag(o), caller);
    }
    // ... existing body
}
```

Same for `lean_inc_ref_cold`. Run the reproducer with
`LEANPY_TRACE_DEC=1` and `MallocStackLogging=1`, capture both streams,
diff against the address that ASAN flags.

For deterministic replay use `rr`:

```bash
rr record python repro_goalstate.py
rr replay
# (gdb) watch -l *0xADDRESS_FROM_ASAN
# (gdb) reverse-continue
```

`rr` records the entire process and lets you set a watchpoint on the
freed address and reverse-step to the dec that freed it. This is the
single most productive tool for this kind of bug.

## Step 3 — Discriminate between hypotheses

Once we have the dec site, the hypothesis it confirms tells us the
fix:

- If the freeing dec is inside a `PersistentHashMap` traversal (e.g.
  `lean_persistent_hashmap_dec` or one of `Lean.PHashMap`'s methods)
  during `Meta.SavedState.restore`'s `modify` callback —
  **hypothesis 1**. Fix: `lean_inc_ref` the borrowed map fields
  before the modify, or change `restore` to copy rather than move.
  This may require a Pantograph upstream patch (their `Goal.lean`
  builds the `SavedState` we then read).

- If the dec runs from a Python frame (caller_address resolves to
  `LeanObj.__del__` via `_runtime.LeanFFI.dec_ref`) —
  **hypothesis 2**. Fix: GIL-aware `lean_dec_ref` wrapper, or move
  all `LeanObj` decrefs onto a single dispatch thread.

- If the freed object is a `MessageData` or closure under a
  `Term.State.syntheticMVars[_].kind` —
  **hypothesis 3**. Fix: replicate `goalStatePickle`'s
  closure-stripping eagerly inside `goal_create`, so we never
  hand a closure-bearing GoalState back to Python.

- If neither — write up what we found and re-rank.

## Step 4 — Land the fix

Whatever hypothesis wins, the fix is one of:

- A patch in our own `LeanPy/Kernel.lean` wrappers (low effort,
  contained).
- A patch in our marshaller (`lean_py/marshal.py::_opaque_wrapper`)
  to inc/dec borrow-correctly (medium effort, affects all opaque
  types).
- A patch upstream in Pantograph or Lean (high effort, longest
  release lag).

Each is testable against the reproducer: success means `python
repro_goalstate.py` exits 0 and the 7 skipped tests in
`tests/test_kernel_full.py` and `tests/test_kernel_extra.py`
unskip cleanly.

## Step 5 — CI guard

Once unskipped, add a CI job that runs the test suite under
the ASAN-built runtime on every PR, marking it `continue-on-error:
true` initially (libpython itself flags some benign things). This
catches regressions without blocking the main matrix.

## Checklist

- [ ] Build ASAN-instrumented `libleanshared` against 4.29.1
- [ ] Add `LEANPY_LIBLEAN` env override to `lean_py/utils.py`
- [ ] Commit `tests/lean/repro_goalstate.py`
- [ ] Run reproducer under ASAN, capture stack trace
- [ ] Run reproducer under `rr`, set a watchpoint on the freed address,
      identify the dec
- [ ] Match against hypotheses 1–4; document the winner in
      `docs/ARCHITECTURE.md`
- [ ] Implement the fix (Lean wrapper / marshaller / upstream PR)
- [ ] Unskip the 7 tests; verify they pass under both regular and
      ASAN runtimes
- [ ] Add ASAN CI job (allow-failure)

## Expected timeline

| Step | Time | Blocker risk |
|------|------|--------------|
| 1 (debug build) | half a day | Lean's cmake on macOS is finicky; Linux is faster |
| 2 (instrumentation) | half a day | none, mostly mechanical |
| 3 (root cause) | half a day–two days | depends on how cleanly `rr` captures it; `rr` doesn't run on Apple Silicon, so requires Linux or x86 macOS |
| 4 (fix) | half a day–two days | upstream PR if hypothesis 1 wins |
| 5 (CI) | half a day | none |

Total: 2–5 days, with the high end being the hypothesis-1-needs-upstream-patch path.

## What we won't do

- Re-derive `GoalState` to avoid the issue (that's option C(i) in the
  parent comment thread). Cheaper but doesn't tell us anything.
- Switch to a "snapshot every time" wrapper (option B). Hides the bug;
  if there's an actual upstream issue we want it found and reported.
- Build our own Lean runtime. We're using ASAN-instrumentation of the
  upstream runtime; no fork.

## Notes

- `rr` requires Linux (or x86 macOS via Rosetta on intel; not Apple
  Silicon as of late 2025). For macOS development the practical setup
  is "ssh into a Linux dev box for the debug session, fold the fix
  back into a normal PR". This is annoying but not blocking.
- The Pantograph test suite doesn't trigger this issue, which is
  consistent with the bug being in our wrappers rather than in
  Pantograph itself. But: if the freeing dec is inside Pantograph's
  `GoalState.create` (hypothesis 1's strongest variant), we'd have
  found a latent upstream bug whose only observer was lean-py.
