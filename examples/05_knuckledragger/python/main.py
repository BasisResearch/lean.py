"""
Drive the Knuckledragger / Z3 oracle from Python.

Loads the KnuckleTactic library, wires up the marshaller for
``decode_and_check_prop``, then builds ``Lean.Expr`` ADT trees
in Python and converts them to Z3 via ``expr_to_z3()``.
"""

from pathlib import Path

from lean_py import LeanLibrary


def main() -> None:
    lake_dir = Path(__file__).resolve().parent.parent / "lean"
    lib = LeanLibrary.from_lake(lake_dir, "KnuckleTactic", build=True)

    import lean_to_z3
    from lean_to_z3 import expr_to_z3

    # Wire up the marshaller for Path B (tactic decode).
    lean_to_z3.setup(lib)

    Name = lib.Name
    Expr = lib.Expr
    Literal = lib.Literal

    def mk_name(s: str):
        parts = s.split(".")
        n = Name.anonymous
        for p in parts:
            n = Name.str(n, p)
        return n

    def mk_const(s: str):
        return Expr.const(mk_name(s), [])

    def mk_nat(n: int):
        return Expr.app(
            Expr.app(
                Expr.app(mk_const("OfNat.ofNat"), mk_const("Nat")),
                Expr.lit(Literal.natVal(n)),
            ),
            mk_const("inst"),
        )

    def mk_binop(op_name: str, a, b):
        op = mk_const(op_name)
        for _ in range(4):
            op = Expr.app(op, mk_const("inst"))
        return Expr.app(Expr.app(op, a), b)

    def mk_eq(lhs, rhs):
        return Expr.app(
            Expr.app(
                Expr.app(mk_const("Eq"), mk_const("Nat")),
                lhs,
            ),
            rhs,
        )


    print("== expr_to_z3 ==")

    one = mk_nat(1)
    two = mk_nat(2)
    expr_add = mk_binop("HAdd.hAdd", one, one)
    z3_add = expr_to_z3(expr_add)
    print(f"  1 + 1 -> {z3_add}")

    z3_eq = expr_to_z3(mk_eq(expr_add, two))
    print(f"  Eq(1 + 1, 2) -> {z3_eq}")

    three = mk_nat(3)
    four = mk_nat(4)
    twelve = mk_nat(12)
    mul_expr = mk_binop("HMul.hMul", three, four)
    z3_mul = expr_to_z3(mk_eq(mul_expr, twelve))
    print(f"  Eq(3 * 4, 12) -> {z3_mul}")

    z3_wrong = expr_to_z3(mk_eq(expr_add, mk_nat(3)))
    print(f"  Eq(1 + 1, 3) -> {z3_wrong}")


if __name__ == "__main__":
    main()
