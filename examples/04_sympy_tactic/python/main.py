"""Drive the SymPy oracle from Python.

Builds ``Lean.Expr`` ADT trees in Python via ``lib.Expr.app(...)`` /
``lib.Name.str(...)`` and converts them directly to SymPy via
``lean_to_sympy.expr_to_sympy()``.
"""

from pathlib import Path

from lean_py import LeanLibrary


def main() -> None:
    lake_dir = Path(__file__).resolve().parent.parent / "lean"
    lib = LeanLibrary.from_lake(lake_dir, "SymPyTactic", build=True)

    import lean_to_sympy
    from lean_to_sympy import expr_to_sympy, sympy_eq_check, sympy_prop_check

    # Wire up the marshaller for Path B (tactic decode).
    lean_to_sympy.setup(lib)

    Name = lib.Name
    Expr = lib.Expr
    Literal = lib.Literal

    # Helper: build a Lean.Name from a dotted string
    def mk_name(s: str):
        parts = s.split(".")
        n = Name.anonymous
        for p in parts:
            n = Name.str(n, p)
        return n

    # Helper: build an elaborated const
    def mk_const(s: str):
        return Expr.const(mk_name(s), [])

    # Helper: build OfNat.ofNat applied to a nat literal
    def mk_nat(n: int):
        """Build the elaborated form: OfNat.ofNat Nat n (instOfNatNat n)"""
        return Expr.app(
            Expr.app(
                Expr.app(mk_const("OfNat.ofNat"), mk_const("Nat")),
                Expr.lit(Literal.natVal(n)),
            ),
            mk_const("inst"),  # instance arg (opaque, ignored by converter)
        )

    # Helper: build a binary op applied to Nat arguments
    def mk_binop(op_name: str, a, b):
        """Build: op Nat Nat Nat instA instB a b (4 type/inst args + 2 values)"""
        op = mk_const(op_name)
        for _ in range(4):
            op = Expr.app(op, mk_const("inst"))
        return Expr.app(Expr.app(op, a), b)

    # Helper: build Eq(type, lhs, rhs)
    def mk_eq(lhs, rhs):
        return Expr.app(
            Expr.app(
                Expr.app(mk_const("Eq"), mk_const("Nat")),
                lhs,
            ),
            rhs,
        )

    print("== expr_to_sympy ==")

    # 1 + 1
    one = mk_nat(1)
    two = mk_nat(2)
    expr_add = mk_binop("HAdd.hAdd", one, one)
    sy_add = expr_to_sympy(expr_add)
    print(f"  1 + 1 -> {sy_add}")

    # (1 + 1) = 2
    sy_eq = expr_to_sympy(mk_eq(expr_add, two))
    print(f"  Eq(1 + 1, 2) -> {sy_eq}")
    print(f"  sympy_prop_check => {sympy_prop_check(sy_eq)}")

    # 3 * 4 = 12
    three = mk_nat(3)
    four = mk_nat(4)
    twelve = mk_nat(12)
    mul_expr = mk_binop("HMul.hMul", three, four)
    sy_mul = expr_to_sympy(mk_eq(mul_expr, twelve))
    print(f"  Eq(3 * 4, 12) -> {sy_mul}")
    print(f"  sympy_prop_check => {sympy_prop_check(sy_mul)}")

    # Intentionally wrong: 1 + 1 = 3
    sy_wrong = expr_to_sympy(mk_eq(expr_add, mk_nat(3)))
    print(f"  Eq(1 + 1, 3) -> {sy_wrong}")
    print(f"  sympy_prop_check => {sympy_prop_check(sy_wrong)}")

    print("\n== sympy_eq_check ==")
    a = mk_nat(5)
    b = mk_binop("HAdd.hAdd", mk_nat(2), mk_nat(3))
    print(f"  5 == 2 + 3 => {sympy_eq_check(expr_to_sympy(a), expr_to_sympy(b))}")

    c = mk_binop("HMul.hMul", mk_nat(6), mk_nat(7))
    d = mk_nat(42)
    print(f"  6 * 7 == 42 => {sympy_eq_check(expr_to_sympy(c), expr_to_sympy(d))}")

    e = mk_binop("HMul.hMul", mk_nat(6), mk_nat(7))
    f = mk_nat(43)
    print(f"  6 * 7 == 43 => {sympy_eq_check(expr_to_sympy(e), expr_to_sympy(f))}")


if __name__ == "__main__":
    main()
