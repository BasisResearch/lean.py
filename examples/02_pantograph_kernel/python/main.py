"""Drive the full LeanPy.Kernel surface from Python.

Walks the major operations of the pantograph-equivalent kernel facade:
env loading, declaration introspection, elaboration, goal-state
construction, prograde tactics (try_have / try_let / try_define /
try_draft), and frontend processing of source strings.
"""

from pathlib import Path

from lean_py import LeanLibrary
from lean_py.kernel import Kernel


def main() -> None:
    lake_dir = Path(__file__).resolve().parent.parent / "lean"
    lib = LeanLibrary.from_lake(lake_dir, "PantographDemo", build=True)

    # ---- Init env -------------------------------------------------------
    k = Kernel(lib)
    k.init_search("")
    k.load(["Init"])
    print(f"environment loaded: {k.is_loaded()}, {k.decl_count()} decls")

    # ---- Goal state (do this first, before MetaM-heavy ops, to dodge
    # the cumulative state churn issue documented in
    # docs/ARCHITECTURE.md "GoalState lifecycle") ------------------------
    print("\n== Goal state — basic queries ==")
    s = k.goal_create("∀ n : Nat, n + 0 = n")
    print(f"  n_goals:        {s.n_goals()}")
    print(f"  main goal mvar: {s.main_goal_name()}")
    print(f"  is_solved:      {s.is_solved()}")

    print("\n== Goal state — pretty (one shot) ==")
    s = k.goal_create("∀ n : Nat, n + 0 = n")
    pretty = s.pretty()
    print(textwrap_indent(pretty, "  "))

    print("\n== Goal state — tactic (one shot) ==")
    s = k.goal_create("∀ n : Nat, n + 0 = n")
    res = s.try_tactic("intro n")
    print(f"  intro n -> status={res.status}")
    if res.ok and res.state is not None:
        # NB: querying res.state's heavy ops after try_tactic re-triggers
        # the lifecycle issue, so we just print the new main-goal mvar
        # name (a cheap field access).
        print(f"    new main goal mvar: {res.state.main_goal_name()}")

    # ---- Declaration introspection -------------------------------------
    print("\n== Decl introspection ==")
    print(f"  Nat.succ exists: {k.decl_exists('Nat.succ')}")
    print(f"  Nat.succ module: {k.module_of('Nat.succ')}")
    print(f"  Nat.succ type:   {k.decl_type('Nat.succ')}")

    # ---- Elaboration ---------------------------------------------------
    print("\n== Elaboration ==")
    print(f"  infer_type 'Nat.succ Nat.zero' = {k.infer_type('Nat.succ Nat.zero')}")
    print(f"  whnf '(fun x => x + 1) 4'      = {k.whnf('(fun x => x + 1) 4')}")
    print(f"  parse_type 'Nat → Nat'         = {k.parse_type('Nat → Nat')}")
    print(f"  decide '1 + 1 = 2'             = {k.decide('1 + 1 = 2')}")
    print(f"  decide '3 < 2'                 = {k.decide('3 < 2')}")

    # ---- Frontend processing -------------------------------------------
    print("\n== Frontend processing ==")
    process_out = k.process("def myExampleFn : Nat := 42\n")
    new_consts = process_out.split("\n---\n")[0].split("\n")
    print(f"  process(def myExampleFn …): defined {new_consts}")
    src_path = k.find_source_path("Init.Prelude")
    print(f"  find_source_path Init.Prelude: {src_path}")
    state, msg = k.collect_sorrys("def f : Nat := 42\n")
    print(f"  collect_sorrys (no sorries): state={state}, msg={msg!r}")

    # ---- Delab utilities ------------------------------------------------
    print("\n== Delab ==")
    print(f"  unfold_aux_lemmas 'Nat.succ Nat.zero' -> {k.unfold_aux_lemmas('Nat.succ Nat.zero')}")
    print(f"  instantiate_all   'Nat.succ Nat.zero' -> {k.instantiate_all('Nat.succ Nat.zero')}")
    print(f"  unfold_matchers   'Nat.succ Nat.zero' -> {k.unfold_matchers('Nat.succ Nat.zero')}")


def textwrap_indent(s: str, prefix: str) -> str:
    return "".join(prefix + line + "\n" for line in s.splitlines())


if __name__ == "__main__":
    main()
