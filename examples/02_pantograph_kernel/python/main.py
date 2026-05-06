"""Drive the PantographDemo Lean library: load Init, infer types, list
declarations, inspect axioms, and decide propositions."""

from pathlib import Path

from lean_py import LeanLibrary


def main() -> None:
    lake_dir = Path(__file__).resolve().parent.parent / "lean"
    lib = LeanLibrary.from_lake(lake_dir, "PantographDemo", build=True)

    # An empty search path is enough to reach the modules already in
    # the toolchain sysroot (Init, Lean, …). Pass a colon-separated
    # list of paths if you've built additional packages.
    lib.demo_init_search("")
    lib.demo_load_env(["Init"])

    print("== infer_type ==")
    print("  Nat.succ Nat.zero    :", lib.demo_infer_type("Nat.succ Nat.zero"))
    print("  fun x : Nat => x + 1 :", lib.demo_infer_type("fun x : Nat => x + 1"))

    print("\n== whnf ==")
    print("  (fun x => x + 1) 4   :", lib.demo_whnf("(fun x => x + 1) 4"))

    print("\n== search_decls ==")
    matches = lib.demo_search_decls("Nat.succ_lt").splitlines()
    for m in matches[:5]:
        print(" ", m)
    print(f"  ({len(matches)} matches in Init)")

    print("\n== decl_type Nat.succ ==")
    print(" ", lib.demo_decl_type("Nat.succ"))

    print("\n== decide ==")
    print("  1 + 1 = 2          :", lib.demo_decide("1 + 1 = 2"))
    print("  3 < 2              :", lib.demo_decide("3 < 2"))


if __name__ == "__main__":
    main()
