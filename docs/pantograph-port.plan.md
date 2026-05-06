# Plan: replace the in-tree Pantograph fork with a Lake dependency

## TL;DR

The current `LeanPy/Kernel/` tree is a copy of Pantograph's `Pantograph/`
tree with namespaces renamed. This was unnecessary — Pantograph
publishes a `lean_lib Pantograph` target and is licensed Apache-2.0,
so we could have done

```lean
require Pantograph from git
  "https://github.com/leanprover/Pantograph.git" @ "v0.3.15"
```

and written our `@[python]` wrappers against the upstream symbols. This
document is what that migration looks like.

## Why we currently vendor

Three reasons we ended up with the fork:

1. **Misread license**. The original commit message and module headers
   claimed Pantograph was GPL-3.0+; it is in fact Apache-2.0. There was
   no copyleft pressure to keep our wrapping at arm's length.
2. **Naming**. The lifted files prefix exports `leanpy_kernel_*` instead
   of `pantograph_*`. That's a deliberate choice for our `@[python]`
   surface but does not require a fork — we can write thin Lean wrappers
   that re-export under our preferred names.
3. **Drift insurance**. A vendored copy doesn't break when upstream
   rewrites their tactic plumbing. In practice Pantograph cuts releases
   tagged `v0.3.x` and pins a Lean toolchain per release, so a SemVer
   pin is just as stable.

## What the port looks like

### 1. `lakefile.lean`

```lean
require Pantograph from git
  "https://github.com/leanprover/Pantograph.git" @ "v0.3.15"
```

Pantograph's lakefile already declares `lean_lib Pantograph`, so the
import surface is exactly its `Pantograph/*.lean` files.

### 2. Replace `LeanPy/Kernel/` with re-exports

Delete `LeanPy/Kernel/{Goal,Frontend,Frontend/*,Serial,Delab,Tactic,
Tactic/*,Environment,Elab,Protocol}.lean` — about 1.5K lines. In their
place, `LeanPy/Kernel.lean` becomes:

```lean
import Pantograph
import Pantograph.Goal
import Pantograph.Frontend
import Pantograph.Serial
import Pantograph.Delab
import Pantograph.Tactic.Assign
import Pantograph.Tactic.Prograde
-- (one import per pantograph module we want to surface)

import LeanPy.Attr

namespace LeanPy.Kernel
  -- Re-export pantograph types under our namespace so existing user
  -- code keeps building.
  abbrev GoalState     := Pantograph.GoalState
  abbrev TacticResult  := Pantograph.TacticResult
  abbrev Site          := Pantograph.Site
  -- … etc.
end LeanPy.Kernel
```

### 3. The `@[python]` wrappers

Today these live at the bottom of `LeanPy/Kernel.lean` (`goalCreate`,
`goalIsSolved`, `goalTryTactic`, `goalTryHave`, `frontendProcess`, …).
The bodies stay almost the same — they just reference `Pantograph.*`
where they currently reference `LeanPy.Kernel.*`. Example:

```lean
-- before
@[python "leanpy_kernel_goal_try_have"]
def goalTryHave (state : GoalState) (binderName typeStr : String) :
    IO (String × Option GoalState) := do
  match state.mainGoal? with
  | none => return ("invalidAction\nno goals", none)
  | some g =>
    runGoalTactic state (state.tryHave (.focus g) binderName.toName typeStr)

-- after
@[python "leanpy_kernel_goal_try_have"]
def goalTryHave (state : Pantograph.GoalState) (binderName typeStr : String) :
    IO (String × Option Pantograph.GoalState) := do
  match state.mainGoal? with
  | none => return ("invalidAction\nno goals", none)
  | some g =>
    runGoalTactic state
      (state.tryHave (.focus g) binderName.toName typeStr)
```

The `try_have`/`try_let`/`try_define`/`try_draft` we added to
`Goal.lean` move into our wrapper layer (they're 4-line pass-throughs
to `Pantograph.Tactic.evalHave` etc., which is what we duplicated from
`Pantograph/Library.lean`).

### 4. Toolchain alignment

Pantograph pins to `leanprover/lean4:v4.29.1` per release. Our
`lean-toolchain` would track that pin. Our existing CI already tests
`v4.29.1` so the CI matrix collapses to "default == 4.29.1" plus
nightly.

## Trade-offs

| | Vendor (current) | Lake dep |
|---|---|---|
| Code we own | ~1500 lines copied | ~250 lines of @[python] wrappers |
| Update cadence | manual rebase | bump pin in lakefile |
| Pinning | per-file edits possible | granular only via fork |
| Build cleanliness | one Lean target | extra git fetch + dep resolution |
| Breakage on upstream churn | quarantined | bisect via Lake `pkg-config` |
| Toolchain coupling | follows ours | follows pantograph's |

The asymmetry that matters is the last row: pantograph dictates the
Lean toolchain. A new Lean release is integrated by Pantograph first,
then us. Today that's fine — Pantograph is actively maintained — but
in a window where pantograph is between releases we'd be stuck. The
vendored copy gives us a knob to fix small things (e.g. unused
variable warnings, or a 4.30-only API patch) without round-tripping
through upstream.

If you want both, a two-target lakefile works: `LeanPy.Kernel` as a
re-export of upstream by default, with a build flag to swap in a
local fork when needed.

## Migration steps

Roughly two days of work end-to-end:

1. Bump `lean-toolchain` to whatever Pantograph's current release pins.
2. Add the `require Pantograph` line, run `lake update`.
3. Delete the `LeanPy/Kernel/` subtree.
4. Rewrite `LeanPy/Kernel.lean` as re-exports + `@[python]` wrappers,
   referencing `Pantograph.GoalState` / `Pantograph.tryTactic` / etc.
5. Move the prograde wrappers (try_have/try_let/try_define/try_draft)
   from our extension of `Goal.lean` into the wrapper file — they're
   now 1:1 forwards to `Pantograph.Tactic.evalHave` etc.
6. Update `docs/ARCHITECTURE.md` to drop the "lifted with attribution"
   language and say "depends on Pantograph".
7. Update `_examples/Pantograph/` — keep it as a reference checkout
   for browsing, or remove it entirely; it's no longer the source of
   truth.
8. Run the test suite.

## Open questions

- **Pantograph's `Library.lean` REPL machinery**: pantograph keeps
  REPL-specific helpers (`tryHave`, `parseElabType`, `goalSerialize`,
  `tryDraft`) in `Library.lean` rather than the importable
  `Pantograph.*` modules. Some of those we want; we'd either reach
  inside their `Library.lean` (slightly bad form) or upstream a PR
  that promotes the prograde tactics into `Pantograph.Tactic.Prograde`.

- **GoalState lifecycle bug**: the second-invocation segfault we
  documented in `ARCHITECTURE.md` would still apply — it's a refcount
  discipline mismatch, not a pantograph bug. But it'd surface as a
  Pantograph issue we'd file upstream rather than something we'd own.

- **Pinning**: pantograph's git tags are `v0.3.x`. We'd need to
  decide on update policy: track main, pin to release, etc.

## Recommendation

Worth doing on the next major release. The current vendored layout
is fine for now (everything works, attribution is correct) but each
Lean toolchain bump means re-running our local fork against
pantograph's diff to make sure we haven't drifted. A Lake dep makes
that a `lake update` + test-run.
