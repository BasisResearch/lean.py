"""Drive the SymPy oracle from Python.

The Python-callable surface (`sympy_simplify`, `sympy_accept`,
`sympy_eq_accept`) is the same one that the in-Lean `sympy` tactic
uses under the hood. The tactic itself runs inside Lean (see
`lean/Demo.lean`); this script is for the cases where you want the
oracle as a function, not as a proof step.
"""

from pathlib import Path

from lean_py import LeanLibrary


def main() -> None:
    lake_dir = Path(__file__).resolve().parent.parent / "lean"
    lib = LeanLibrary.from_lake(lake_dir, "SymPyTactic", build=True)

    print("== sympy_simplify ==")
    print("  (x**2 - 1)/(x - 1)              ->", lib.sympy_simplify("(x**2 - 1)/(x - 1)"))
    print("  sin(x)**2 + cos(x)**2           ->", lib.sympy_simplify("sin(x)**2 + cos(x)**2"))
    print("  factorial(5)                    ->", lib.sympy_simplify("factorial(5)"))

    print("\n== sympy_eq_accept ==")
    cases = [
        ("(x + 1)**2",        "x**2 + 2*x + 1"),
        ("sin(x)**2 + cos(x)**2", "1"),
        ("(x**3 - 1)/(x - 1)", "x**2 + x + 1"),
        ("x*(x + 2)",         "x**2 + 2*x"),
        # an intentionally-wrong one
        ("(x + 1)**2",        "x**2 + 2*x + 2"),
    ]
    for lhs, rhs in cases:
        ok = lib.sympy_eq_accept(lhs, rhs)
        print(f"  {lhs}  ==  {rhs}  ->  {'accept' if ok else 'reject'}")

    print("\n== sympy_accept ==")
    for prop in [
        "Eq((x + y)**2 - x**2 - 2*x*y - y**2, 0)",
        "Eq(sin(2*x), 2*sin(x)*cos(x))",
        "Eq(integrate(x**2, x), x**3/3)",
    ]:
        ok = lib.sympy_accept(prop)
        print(f"  {prop}  ->  {'accepted' if ok else 'rejected'}")


if __name__ == "__main__":
    main()
