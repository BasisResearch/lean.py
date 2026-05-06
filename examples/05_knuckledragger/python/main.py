"""Drive the Knuckledragger / Z3 oracle from Python."""

from pathlib import Path
import sys

# Make our local `knuckle_bridge` module importable inside the in-Lean
# Python interpreter. The Lean side does `import knuckle_bridge`, which
# resolves through `sys.path`; since both Python and Lean share the
# same interpreter via lean-py, putting our directory on `sys.path` is
# enough.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lean_py import LeanLibrary


def main() -> None:
    lake_dir = Path(__file__).resolve().parent.parent / "lean"
    lib = LeanLibrary.from_lake(lake_dir, "KnuckleTactic", build=True)

    print("== knuckle_eq_accept ==")
    cases = [
        ("(x + 1)*(x + 1)",       "x*x + 2*x + 1"),
        ("(x + y)*(x - y)",       "x*x - y*y"),
        ("x*(y + z)",             "x*y + x*z"),
        # an intentionally-wrong one
        ("(x + 1)*(x + 1)",       "x*x + 2*x + 2"),
    ]
    for lhs, rhs in cases:
        ok = lib.knuckle_eq_accept(lhs, rhs)
        print(f"  {lhs}  ==  {rhs}  ->  {'accept' if ok else 'reject'}")

    print("\n== knuckle_accept ==")
    for prop in [
        "Eq((x + 1)*(x - 1), x*x - 1)",
        "Eq(x*0, 0)",
        "Eq(x + (-x), 0)",
    ]:
        ok = lib.knuckle_accept(prop)
        print(f"  {prop}  ->  {'accepted' if ok else 'rejected'}")


if __name__ == "__main__":
    main()
